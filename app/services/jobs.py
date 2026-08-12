import base64
import binascii
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import BatchItem, BatchJob, PipelineJob
from app.services.ingestion import IngestionService
from app.services.pipeline import ProductPipeline
from app.services.storage import build_object_storage


PROCESSABLE_JOB_STATUSES = {"queued", "failed"}


def process_pipeline_job(db: Session, job: PipelineJob) -> PipelineJob:
    if job.status not in PROCESSABLE_JOB_STATUSES:
        return job

    job.status = "running"
    job.error = None
    job.started_at = datetime.now(timezone.utc)
    job.completed_at = None
    db.commit()
    db.refresh(job)

    try:
        ProductPipeline(db).run(job.product, source_ids=job.source_ids, stages=job.stages)
        job.status = "completed"
    except Exception as exc:
        db.rollback()
        job = db.get(PipelineJob, job.id)
        if job is None:
            raise
        job.status = "failed"
        job.error = str(exc)[:4000]
    job.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(job)
    return job


def process_next_pipeline_job(db: Session) -> PipelineJob | None:
    job = db.scalar(
        select(PipelineJob)
        .where(PipelineJob.status == "queued")
        .order_by(PipelineJob.created_at.asc())
        .with_for_update(skip_locked=True)
    )
    if job is None:
        return None
    return process_pipeline_job(db, job)


def _ingest_batch_item_sources(db: Session, item: BatchItem) -> None:
    if item.product is None:
        raise ValueError("Batch item has no product")
    if item.product.sources:
        return
    settings = get_settings()
    service = IngestionService(settings, build_object_storage(settings))
    for source_payload in item.payload.get("sources", []):
        source_type = source_payload["source_type"]
        identifier = source_payload["source_identifier"]
        if source_type == "text":
            source = service.from_text(item.product.id, source_payload["raw_content"], identifier)
        elif source_type == "url":
            source = service.from_url(item.product.id, source_payload["url"])
        elif source_type == "pdf":
            try:
                content = base64.b64decode(source_payload["content_base64"], validate=True)
            except (ValueError, binascii.Error) as exc:
                raise ValueError(f"Invalid base64 PDF for {identifier}") from exc
            source = service.from_pdf_bytes(item.product.id, content, identifier)
        else:
            raise ValueError(f"Unsupported source type: {source_type}")
        db.add(source)
    db.commit()


def process_batch_job(db: Session, batch: BatchJob, include_failed: bool = False) -> BatchJob:
    eligible_statuses = {"queued", "failed"} if include_failed else {"queued"}
    batch.status = "running"
    db.commit()

    item_ids = [item.id for item in batch.items if item.status in eligible_statuses]
    for item_id in item_ids:
        item = db.get(BatchItem, item_id)
        if item is None:
            continue
        item.status = "running"
        item.error = None
        db.commit()
        try:
            _ingest_batch_item_sources(db, item)
            db.refresh(item)
            if item.product is None:
                raise ValueError("Batch item has no product")
            ProductPipeline(db).run(item.product)
            item.status = "processed"
            item.error = None
            db.commit()
        except Exception as exc:
            db.rollback()
            item = db.get(BatchItem, item_id)
            if item is None:
                raise
            item.status = "failed"
            item.error = str(exc)[:4000]
            db.commit()

    batch = db.get(BatchJob, batch.id)
    if batch is None:
        raise RuntimeError("Batch disappeared while processing")
    batch.processed_items = sum(item.status == "processed" for item in batch.items)
    batch.failed_items = sum(item.status == "failed" for item in batch.items)
    remaining = any(item.status in {"queued", "running"} for item in batch.items)
    if remaining:
        batch.status = "running"
    else:
        batch.status = "completed" if batch.failed_items == 0 else "completed_with_errors"
    db.commit()
    db.refresh(batch)
    return batch


def process_next_batch_job(db: Session) -> BatchJob | None:
    batch = db.scalar(
        select(BatchJob)
        .where(BatchJob.status == "queued")
        .order_by(BatchJob.created_at.asc())
        .with_for_update(skip_locked=True)
    )
    if batch is None:
        return None
    return process_batch_job(db, batch)
