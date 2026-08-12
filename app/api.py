from fastapi import APIRouter, Depends, FastAPI, File, HTTPException, Query, UploadFile
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
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


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok"}


@router.post("/products/ingest/text", response_model=ProductRead)
def ingest_text(payload: TextIngestionRequest, db: Session = Depends(get_db)) -> Product:
    product = Product(name=payload.product_name)
    db.add(product)
    db.flush()
    source = IngestionService(get_settings()).from_text(product.id, payload.text, payload.source_identifier)
    db.add(source)
    db.commit()
    db.refresh(product)
    return product


@router.post("/products/ingest/url", response_model=ProductRead)
def ingest_url(payload: UrlIngestionRequest, db: Session = Depends(get_db)) -> Product:
    product = Product(name=payload.product_name)
    db.add(product)
    db.flush()
    source = IngestionService(get_settings()).from_url(product.id, str(payload.url))
    db.add(source)
    db.commit()
    db.refresh(product)
    return product


@router.post("/products/{product_id}/ingest/pdf", response_model=ProductRead)
def ingest_pdf(product_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)) -> Product:
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    path = f"/tmp/{product_id}-{file.filename}"
    with open(path, "wb") as handle:
        handle.write(file.file.read())
    db.add(IngestionService(get_settings()).from_pdf(product.id, path))
    db.commit()
    db.refresh(product)
    return product


@router.post("/products/{product_id}/pipeline", response_model=ProductDetail)
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


@router.patch("/reviews/{review_id}", response_model=ReviewItemRead)
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


@router.patch("/products/{product_id}/fields/{field_name}", response_model=ExtractedFieldRead)
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


@router.post("/batches", response_model=BatchRead)
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


@router.post("/batches/{batch_id}/process", response_model=BatchDetail)
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
    app = FastAPI(title="Industrial Product Intelligence Platform API", version="0.1.0")
    app.include_router(router, prefix=get_settings().api_v1_prefix)

    return app


app = create_app()
