import logging
import time

from app.core.config import get_settings
from app.db import SessionLocal
from app.services.jobs import process_next_batch_job, process_next_pipeline_job


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ferrox.worker")


def run_worker() -> None:
    poll_seconds = get_settings().worker_poll_seconds
    logger.info("Ferrox job worker started")
    while True:
        with SessionLocal() as db:
            pipeline_job = process_next_pipeline_job(db)
            batch_job = process_next_batch_job(db)
        if pipeline_job is None and batch_job is None:
            time.sleep(poll_seconds)
        if pipeline_job is not None:
            logger.info("Pipeline job %s finished with status %s", pipeline_job.id, pipeline_job.status)
        if batch_job is not None:
            logger.info("Batch job %s finished with status %s", batch_job.id, batch_job.status)


if __name__ == "__main__":
    run_worker()
