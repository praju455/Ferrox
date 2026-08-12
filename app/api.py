import logging
import tempfile
import time
import uuid
from pathlib import Path

import requests
from fastapi import APIRouter, Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import require_internal_api_key
from app.db import get_db
from app.models import BatchItem, BatchJob, ExtractedField, FieldStatus, Product, ReviewItem, ReviewStatus
from app.schemas import (
    BatchCreateRequest,
    BatchDetail,
    BatchProcessRequest,
    BatchRead,
    ExtractedFieldRead,
    FieldCorrectionRequest,
    PipelineRunRequest,
    ProductDetail,
    ProductRead,
    ReviewItemRead,
    ReviewItemUpdate,
    TextIngestionRequest,
    UrlIngestionRequest,
)
from app.services.ingestion import IngestionService
from app.services.pipeline import ProductPipeline


router = APIRouter()
logger = logging.getLogger("ferrox.api")


class RequestSafetyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: FastAPI, max_request_bytes: int):
        super().__init__(app)
        self.max_request_bytes = max_request_bytes

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        content_length = request.headers.get("content-length")
        try:
            request_size = int(content_length) if content_length else 0
        except ValueError:
            request_size = self.max_request_bytes + 1
        if request_size > self.max_request_bytes:
            return JSONResponse(
                status_code=413,
                content={"detail": "Request body is too large", "request_id": request_id},
                headers={"X-Request-ID": request_id},
            )
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("Unhandled request error", extra={"request_id": request_id, "path": request.url.path})
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error", "request_id": request_id},
                headers={"X-Request-ID": request_id},
            )
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        logger.info(
            "Request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        return response


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok"}


@router.post("/products/ingest/text", response_model=ProductRead, dependencies=[Depends(require_internal_api_key)])
def ingest_text(payload: TextIngestionRequest, db: Session = Depends(get_db)) -> Product:
    product = Product(name=payload.product_name)
    db.add(product)
    db.flush()
    source = IngestionService(get_settings()).from_text(product.id, payload.text, payload.source_identifier)
    db.add(source)
    db.commit()
    db.refresh(product)
    return product


@router.post("/products/ingest/url", response_model=ProductRead, dependencies=[Depends(require_internal_api_key)])
def ingest_url(payload: UrlIngestionRequest, db: Session = Depends(get_db)) -> Product:
    product = Product(name=payload.product_name)
    db.add(product)
    db.flush()
    try:
        source = IngestionService(get_settings()).from_url(product.id, str(payload.url))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail="Source URL could not be fetched") from exc
    db.add(source)
    db.commit()
    db.refresh(product)
    return product


@router.post("/products/{product_id}/ingest/pdf", response_model=ProductRead, dependencies=[Depends(require_internal_api_key)])
def ingest_pdf(product_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)) -> Product:
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if Path(file.filename or "").suffix.lower() != ".pdf":
        raise HTTPException(status_code=415, detail="Only PDF files are supported")
    settings = get_settings()
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as handle:
            temp_path = Path(handle.name)
            total = 0
            while chunk := file.file.read(1024 * 1024):
                total += len(chunk)
                if total > settings.max_pdf_upload_bytes:
                    raise HTTPException(status_code=413, detail="PDF upload is too large")
                handle.write(chunk)
        source = IngestionService(settings).from_pdf(product.id, str(temp_path))
        source.source_identifier = file.filename or "uploaded-datasheet.pdf"
        db.add(source)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    db.commit()
    db.refresh(product)
    return product


@router.post("/products/{product_id}/pipeline", response_model=ProductDetail, dependencies=[Depends(require_internal_api_key)])
def run_pipeline(product_id: str, payload: PipelineRunRequest | None = None, db: Session = Depends(get_db)) -> Product:
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return ProductPipeline(db).run(product, payload.source_ids if payload else None)


@router.get("/products/{product_id}", response_model=ProductDetail)
def get_product(product_id: str, db: Session = Depends(get_db)) -> Product:
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.get("/reviews", response_model=list[ReviewItemRead])
def list_reviews(
    status: ReviewStatus | None = Query(default=None),
    severity: str | None = Query(default=None),
    product_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[ReviewItem]:
    query = select(ReviewItem)
    if status is not None:
        query = query.where(ReviewItem.status == status)
    if severity is not None:
        query = query.where(ReviewItem.severity == severity)
    if product_id is not None:
        query = query.where(ReviewItem.product_id == product_id)
    return list(db.scalars(query.order_by(ReviewItem.created_at.desc()).limit(limit)))


@router.get("/reviews/{review_id}", response_model=ReviewItemRead)
def get_review(review_id: str, db: Session = Depends(get_db)) -> ReviewItem:
    review = db.get(ReviewItem, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review item not found")
    return review


@router.patch("/reviews/{review_id}", response_model=ReviewItemRead, dependencies=[Depends(require_internal_api_key)])
def update_review(review_id: str, payload: ReviewItemUpdate, db: Session = Depends(get_db)) -> ReviewItem:
    review = db.get(ReviewItem, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review item not found")
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        if key == "status" and value is not None:
            value = ReviewStatus(value)
        setattr(review, key, value)
    db.commit()
    db.refresh(review)
    return review


@router.patch("/products/{product_id}/fields/{field_name}", response_model=ExtractedFieldRead, dependencies=[Depends(require_internal_api_key)])
def correct_field(product_id: str, field_name: str, payload: FieldCorrectionRequest, db: Session = Depends(get_db)) -> ExtractedField:
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    field = db.scalar(select(ExtractedField).where(ExtractedField.product_id == product_id, ExtractedField.field_name == field_name))
    if not field:
        field = ExtractedField(
            product_id=product_id,
            source_id=None,
            field_name=field_name,
            value=payload.value,
            unit=payload.unit,
            confidence=payload.confidence,
            status=FieldStatus.validated,
            evidence=payload.evidence,
            alternatives=[],
            validation={"reviewer_corrected": True},
        )
        db.add(field)
    else:
        field.value = payload.value
        field.unit = payload.unit
        field.confidence = payload.confidence
        field.status = FieldStatus.validated
        field.evidence = payload.evidence or field.evidence
        field.validation = {**(field.validation or {}), "reviewer_corrected": True}
    if payload.resolve_reviews:
        reviews = db.scalars(
            select(ReviewItem).where(
                ReviewItem.product_id == product_id,
                ReviewItem.field_name == field_name,
                ReviewItem.status == ReviewStatus.open,
            )
        )
        for review in reviews:
            review.status = ReviewStatus.resolved
    ProductPipeline(db).score_and_queue(product)
    db.commit()
    db.refresh(field)
    return field


@router.post("/batches", response_model=BatchRead, dependencies=[Depends(require_internal_api_key)])
def create_batch(payload: BatchCreateRequest, db: Session = Depends(get_db)) -> BatchJob:
    batch = BatchJob(total_items=len(payload.items), status="running")
    db.add(batch)
    db.flush()
    for item in payload.items:
        product = Product(name=item.name)
        db.add(product)
        db.flush()
        for source_in in item.sources:
            if source_in.source_type != "text" or not source_in.raw_content:
                continue
            db.add(IngestionService(get_settings()).from_text(product.id, source_in.raw_content, source_in.source_identifier))
        db.add(BatchItem(batch_id=batch.id, product_id=product.id, status="queued", payload=item.model_dump()))
    db.flush()
    process_batch_items(db, batch, include_failed=False)
    db.commit()
    db.refresh(batch)
    return batch


@router.get("/batches", response_model=list[BatchRead])
def list_batches(
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[BatchJob]:
    query = select(BatchJob)
    if status is not None:
        query = query.where(BatchJob.status == status)
    return list(db.scalars(query.order_by(BatchJob.created_at.desc()).limit(limit)))


@router.get("/batches/{batch_id}", response_model=BatchDetail)
def get_batch(batch_id: str, db: Session = Depends(get_db)) -> BatchJob:
    batch = db.get(BatchJob, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    return batch


@router.post("/batches/{batch_id}/process", response_model=BatchDetail, dependencies=[Depends(require_internal_api_key)])
def process_batch(batch_id: str, payload: BatchProcessRequest | None = None, db: Session = Depends(get_db)) -> BatchJob:
    batch = db.get(BatchJob, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    process_batch_items(db, batch, include_failed=payload.include_failed if payload else True)
    db.commit()
    db.refresh(batch)
    return batch


def process_batch_items(db: Session, batch: BatchJob, include_failed: bool) -> None:
    batch.status = "running"
    batch.processed_items = 0
    batch.failed_items = 0
    eligible_statuses = {"queued", "failed"} if include_failed else {"queued"}
    for item in batch.items:
        if item.status not in eligible_statuses:
            if item.status == "processed":
                batch.processed_items += 1
            elif item.status == "failed":
                batch.failed_items += 1
            continue
        try:
            if not item.product:
                raise ValueError("Batch item has no product")
            ProductPipeline(db).run(item.product)
            item.status = "processed"
            item.error = None
            batch.processed_items += 1
        except Exception as exc:
            item.status = "failed"
            item.error = str(exc)
            batch.failed_items += 1
    batch.status = "completed" if batch.failed_items == 0 else "completed_with_errors"


def create_app() -> FastAPI:
    settings = get_settings()
    if settings.is_production and not settings.internal_api_key:
        raise RuntimeError("INTERNAL_API_KEY must be configured in production")
    app = FastAPI(title="Industrial Product Intelligence Platform API", version="0.2.0")
    app.add_middleware(RequestSafetyMiddleware, max_request_bytes=settings.max_request_bytes)
    if settings.allowed_hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    if settings.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.allowed_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Request-ID"],
            expose_headers=["X-Request-ID"],
        )
    app.include_router(router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
