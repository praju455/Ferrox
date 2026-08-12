import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests
from fastapi import APIRouter, Depends, FastAPI, File, HTTPException, Query, Response, UploadFile, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    Principal,
    create_access_token,
    current_principal,
    hash_password,
    require_admin,
    require_internal_api_key,
    require_reviewer,
    verify_password,
)
from app.db import get_db
from app.models import BatchItem, BatchJob, ExtractedField, FieldStatus, LLMRun, PipelineJob, Product, ReviewItem, ReviewStatus, Source, User, UserRole
from app.schemas import (
    BatchCreateRequest,
    BatchDetail,
    BatchProcessRequest,
    BatchRead,
    ExtractedFieldRead,
    FieldCorrectionRequest,
    LLMRunRead,
    PipelineRunRequest,
    PipelineJobRead,
    ProductCreateRequest,
    ProductDetail,
    ProductRead,
    ReviewItemRead,
    ReviewItemUpdate,
    SourceRead,
    TextSourceCreate,
    TextIngestionRequest,
    TokenResponse,
    UrlSourceCreate,
    UrlIngestionRequest,
    UserCreateRequest,
    UserRead,
    UserUpdateRequest,
)
from app.services.ingestion import IngestionService
from app.services.jobs import PROCESSABLE_JOB_STATUSES, process_batch_job, process_pipeline_job
from app.services.pipeline import ProductPipeline
from app.services.observability import HTTP_LATENCY, HTTP_REQUESTS, METRICS_CONTENT_TYPE, metrics_payload
from app.services.storage import build_object_storage


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
        route = request.scope.get("route")
        route_path = getattr(route, "path", request.url.path)
        duration_seconds = time.perf_counter() - started
        HTTP_REQUESTS.labels(request.method, route_path, str(response.status_code)).inc()
        HTTP_LATENCY.labels(request.method, route_path).observe(duration_seconds)
        logger.info(
            "Request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(duration_seconds * 1000, 2),
            },
        )
        return response


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok"}


@router.get("/health/live")
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
def readiness(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ready", "database": "ok"}


@router.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(metrics_payload(), media_type=METRICS_CONTENT_TYPE)


@router.post("/auth/token", response_model=TokenResponse)
def issue_token(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> TokenResponse:
    email = form.username.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if not user or not user.is_active or not verify_password(form.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token, expires_in = create_access_token(user)
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.get("/auth/me", response_model=UserRead)
def auth_me(
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> User:
    if principal.user_id is None:
        raise HTTPException(status_code=400, detail="Service credentials do not represent a user")
    user = db.get(User, principal.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post(
    "/users",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_user(payload: UserCreateRequest, db: Session = Depends(get_db)) -> User:
    email = payload.email.strip().lower()
    if "@" not in email:
        raise HTTPException(status_code=422, detail="A valid email address is required")
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name.strip(),
        role=UserRole(payload.role),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A user with this email already exists") from exc
    db.refresh(user)
    return user


@router.get("/users", response_model=list[UserRead], dependencies=[Depends(require_admin)])
def list_users(db: Session = Depends(get_db)) -> list[User]:
    return list(db.scalars(select(User).order_by(User.created_at.desc())))


@router.patch("/users/{user_id}", response_model=UserRead, dependencies=[Depends(require_admin)])
def update_user(user_id: str, payload: UserUpdateRequest, db: Session = Depends(get_db)) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    updates = payload.model_dump(exclude_unset=True)
    if "password" in updates:
        user.password_hash = hash_password(updates.pop("password"))
    if "role" in updates:
        user.role = UserRole(updates.pop("role"))
    for key, value in updates.items():
        setattr(user, key, value.strip() if key == "full_name" else value)
    db.commit()
    db.refresh(user)
    return user


def product_or_404(product_id: str, db: Session) -> Product:
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


def fetch_url_source(product_id: str, url: str) -> Source:
    try:
        return IngestionService(get_settings()).from_url(product_id, url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail="Source URL could not be fetched") from exc


def extract_pdf_source(product_id: str, file: UploadFile) -> Source:
    if Path(file.filename or "").suffix.lower() != ".pdf":
        raise HTTPException(status_code=415, detail="Only PDF files are supported")
    settings = get_settings()
    try:
        content = file.file.read(settings.max_pdf_upload_bytes + 1)
        if len(content) > settings.max_pdf_upload_bytes:
            raise HTTPException(status_code=413, detail="PDF upload is too large")
        return IngestionService(settings, build_object_storage(settings)).from_pdf_bytes(
            product_id,
            content,
            file.filename or "uploaded-datasheet.pdf",
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/products", response_model=ProductRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_internal_api_key)])
def create_product(payload: ProductCreateRequest, db: Session = Depends(get_db)) -> Product:
    product = Product(name=payload.name)
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.get("/products", response_model=list[ProductRead], dependencies=[Depends(require_reviewer)])
def list_products(
    search: str | None = Query(default=None, min_length=1, max_length=255),
    category: str | None = Query(default=None, max_length=120),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[Product]:
    query = select(Product)
    if search:
        query = query.where(Product.name.ilike(f"%{search}%"))
    if category:
        query = query.where(Product.category == category)
    return list(db.scalars(query.order_by(Product.created_at.desc()).offset(offset).limit(limit)))


@router.post("/products/{product_id}/sources/text", response_model=SourceRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_internal_api_key)])
def add_text_source(product_id: str, payload: TextSourceCreate, db: Session = Depends(get_db)) -> Source:
    product_or_404(product_id, db)
    source = IngestionService(get_settings()).from_text(product_id, payload.text, payload.source_identifier)
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


@router.post("/products/{product_id}/sources/url", response_model=SourceRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_internal_api_key)])
def add_url_source(product_id: str, payload: UrlSourceCreate, db: Session = Depends(get_db)) -> Source:
    product_or_404(product_id, db)
    source = fetch_url_source(product_id, str(payload.url))
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


@router.post("/products/{product_id}/sources/pdf", response_model=SourceRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_internal_api_key)])
def add_pdf_source(product_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)) -> Source:
    product_or_404(product_id, db)
    source = extract_pdf_source(product_id, file)
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


@router.get("/products/{product_id}/sources", response_model=list[SourceRead], dependencies=[Depends(require_reviewer)])
def list_product_sources(product_id: str, db: Session = Depends(get_db)) -> list[Source]:
    product_or_404(product_id, db)
    query = select(Source).where(Source.product_id == product_id).order_by(Source.created_at.desc())
    return list(db.scalars(query))


@router.get("/products/{product_id}/sources/{source_id}", response_model=SourceRead, dependencies=[Depends(require_reviewer)])
def get_product_source(product_id: str, source_id: str, db: Session = Depends(get_db)) -> Source:
    source = db.scalar(select(Source).where(Source.id == source_id, Source.product_id == product_id))
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


@router.get("/products/{product_id}/sources/{source_id}/content", dependencies=[Depends(require_reviewer)])
def download_product_source(product_id: str, source_id: str, db: Session = Depends(get_db)) -> StreamingResponse:
    source = db.scalar(select(Source).where(Source.id == source_id, Source.product_id == product_id))
    if not source or not source.storage_key:
        raise HTTPException(status_code=404, detail="Stored source content not found")
    stream = build_object_storage(get_settings()).open(source.storage_key)
    filename = Path(source.source_identifier).name.replace('"', "")
    return StreamingResponse(
        stream,
        media_type=source.content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_internal_api_key)])
def delete_product(product_id: str, db: Session = Depends(get_db)) -> Response:
    product = product_or_404(product_id, db)
    storage_keys = [source.storage_key for source in product.sources if source.storage_key]
    db.delete(product)
    db.commit()
    storage = build_object_storage(get_settings())
    for storage_key in storage_keys:
        try:
            storage.delete(storage_key)
        except Exception:
            logger.exception("Failed to remove source object", extra={"storage_key": storage_key})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    source = fetch_url_source(product.id, str(payload.url))
    db.add(source)
    db.commit()
    db.refresh(product)
    return product


@router.post("/products/{product_id}/ingest/pdf", response_model=ProductRead, dependencies=[Depends(require_internal_api_key)])
def ingest_pdf(product_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)) -> Product:
    product = product_or_404(product_id, db)
    db.add(extract_pdf_source(product.id, file))
    db.commit()
    db.refresh(product)
    return product


@router.post("/products/{product_id}/pipeline", response_model=ProductDetail, dependencies=[Depends(require_internal_api_key)])
def run_pipeline(product_id: str, payload: PipelineRunRequest | None = None, db: Session = Depends(get_db)) -> Product:
    product = product_or_404(product_id, db)
    return ProductPipeline(db).run(
        product,
        source_ids=payload.source_ids if payload else None,
        stages=payload.stages if payload else None,
    )


@router.post(
    "/products/{product_id}/pipeline/jobs",
    response_model=PipelineJobRead,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_internal_api_key)],
)
def create_pipeline_job(
    product_id: str,
    payload: PipelineRunRequest | None = None,
    db: Session = Depends(get_db),
) -> PipelineJob:
    product_or_404(product_id, db)
    job = PipelineJob(
        product_id=product_id,
        source_ids=payload.source_ids if payload else None,
        stages=payload.stages if payload else None,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@router.get("/pipeline/jobs", response_model=list[PipelineJobRead], dependencies=[Depends(require_reviewer)])
def list_pipeline_jobs(
    product_id: str | None = Query(default=None),
    job_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[PipelineJob]:
    query = select(PipelineJob)
    if product_id:
        query = query.where(PipelineJob.product_id == product_id)
    if job_status:
        query = query.where(PipelineJob.status == job_status)
    return list(db.scalars(query.order_by(PipelineJob.created_at.desc()).limit(limit)))


@router.get("/pipeline/jobs/{job_id}", response_model=PipelineJobRead, dependencies=[Depends(require_reviewer)])
def get_pipeline_job(job_id: str, db: Session = Depends(get_db)) -> PipelineJob:
    job = db.get(PipelineJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Pipeline job not found")
    return job


@router.get(
    "/observability/llm-runs",
    response_model=list[LLMRunRead],
    dependencies=[Depends(require_admin)],
)
def list_llm_runs(
    product_id: str | None = Query(default=None),
    provider: str | None = Query(default=None),
    task: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[LLMRun]:
    query = select(LLMRun)
    if product_id:
        query = query.where(LLMRun.product_id == product_id)
    if provider:
        query = query.where(LLMRun.provider == provider)
    if task:
        query = query.where(LLMRun.task == task)
    return list(db.scalars(query.order_by(LLMRun.created_at.desc()).limit(limit)))


@router.post(
    "/pipeline/jobs/{job_id}/process",
    response_model=PipelineJobRead,
    dependencies=[Depends(require_internal_api_key)],
)
def process_queued_pipeline_job(job_id: str, db: Session = Depends(get_db)) -> PipelineJob:
    job = db.get(PipelineJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Pipeline job not found")
    if job.status not in PROCESSABLE_JOB_STATUSES:
        raise HTTPException(status_code=409, detail=f"Pipeline job is already {job.status}")
    return process_pipeline_job(db, job)


@router.get("/products/{product_id}", response_model=ProductDetail, dependencies=[Depends(require_reviewer)])
def get_product(product_id: str, db: Session = Depends(get_db)) -> Product:
    return product_or_404(product_id, db)


@router.get("/reviews", response_model=list[ReviewItemRead], dependencies=[Depends(require_reviewer)])
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


@router.get("/reviews/{review_id}", response_model=ReviewItemRead, dependencies=[Depends(require_reviewer)])
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


@router.post(
    "/batches",
    response_model=BatchRead,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_internal_api_key)],
)
def create_batch(payload: BatchCreateRequest, db: Session = Depends(get_db)) -> BatchJob:
    batch = BatchJob(total_items=len(payload.items), status="queued")
    db.add(batch)
    db.flush()
    for item in payload.items:
        product = Product(name=item.name)
        db.add(product)
        db.flush()
        db.add(BatchItem(batch_id=batch.id, product_id=product.id, status="queued", payload=item.model_dump(mode="json")))
    db.commit()
    db.refresh(batch)
    return batch


@router.get("/batches", response_model=list[BatchRead], dependencies=[Depends(require_reviewer)])
def list_batches(
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[BatchJob]:
    query = select(BatchJob)
    if status is not None:
        query = query.where(BatchJob.status == status)
    return list(db.scalars(query.order_by(BatchJob.created_at.desc()).limit(limit)))


@router.get("/batches/{batch_id}", response_model=BatchDetail, dependencies=[Depends(require_reviewer)])
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
    return process_batch_job(db, batch, include_failed=payload.include_failed if payload else True)


def create_app() -> FastAPI:
    settings = get_settings()
    if settings.is_production and not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET must be configured in production")
    if settings.is_production and len(settings.jwt_secret or "") < 32:
        raise RuntimeError("JWT_SECRET must contain at least 32 characters in production")
    app = FastAPI(title="Industrial Product Intelligence Platform API", version="0.2.0")
    app.add_middleware(RequestSafetyMiddleware, max_request_bytes=settings.max_request_bytes)
    if settings.allowed_hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    if settings.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.allowed_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Request-ID"],
            expose_headers=["X-Request-ID"],
        )
    app.include_router(router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
