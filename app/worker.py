import logging
import time

from app.core.config import get_settings
from app.db import SessionLocal
from app.services.jobs import process_next_pipeline_job


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ferrox.worker")


def run_worker() -> None:
    poll_seconds = get_settings().worker_poll_seconds
    logger.info("Ferrox pipeline worker started")
    while True:
        with SessionLocal() as db:
            job = process_next_pipeline_job(db)
        if job is None:
            time.sleep(poll_seconds)
        else:
            logger.info("Pipeline job %s finished with status %s", job.id, job.status)


if __name__ == "__main__":
    run_worker()
