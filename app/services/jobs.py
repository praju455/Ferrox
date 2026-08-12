from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PipelineJob
from app.services.pipeline import ProductPipeline


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
