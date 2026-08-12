from fastapi import APIRouter, Depends, FastAPI, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import get_db, init_db
from app.models import BatchItem, BatchJob, Product
from app.schemas import BatchCreateRequest, BatchRead, PipelineRunRequest, ProductDetail, ProductRead, TextIngestionRequest, UrlIngestionRequest
from app.services.ingestion import IngestionService
from app.services.pipeline import ProductPipeline


router = APIRouter()


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
    for item in batch.items:
        try:
            ProductPipeline(db).run(item.product)
            item.status = "processed"
            batch.processed_items += 1
        except Exception as exc:
            item.status = "failed"
            item.error = str(exc)
            batch.failed_items += 1
    batch.status = "completed" if batch.failed_items == 0 else "completed_with_errors"
    db.commit()
    db.refresh(batch)
    return batch


def create_app() -> FastAPI:
    app = FastAPI(title="Industrial Product Intelligence Platform API", version="0.1.0")
    app.include_router(router, prefix=get_settings().api_v1_prefix)

    @app.on_event("startup")
    def startup() -> None:
        init_db()

    return app


app = create_app()
