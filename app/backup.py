import argparse
import logging
import os
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from sqlalchemy.engine import make_url

from app.core.config import Settings, get_settings
from app.services.storage import ObjectStorage, build_object_storage


logger = logging.getLogger("ferrox.backup")


def postgres_command(database_url: str, executable: str, output_path: str | None = None) -> tuple[list[str], dict[str, str]]:
    url = make_url(database_url)
    if not url.drivername.startswith("postgresql"):
        raise ValueError("Backups require a PostgreSQL DATABASE_URL")
    command = [executable, "--host", url.host or "localhost", "--port", str(url.port or 5432)]
    if url.username:
        command.extend(["--username", url.username])
    if executable == "pg_dump":
        command.extend(["--format=custom", "--compress=9", "--no-password"])
        if output_path:
            command.extend(["--file", output_path])
    else:
        command.extend(["--clean", "--if-exists", "--no-owner", "--no-password"])
    if executable == "pg_dump" and url.database:
        command.append(url.database)
    env = os.environ.copy()
    if url.password:
        env["PGPASSWORD"] = url.password
    return command, env


def run_backup(
    settings: Settings | None = None,
    storage: ObjectStorage | None = None,
    runner: Callable = subprocess.run,
    now: datetime | None = None,
) -> str:
    settings = settings or get_settings()
    storage = storage or build_object_storage(settings)
    timestamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    key = f"{settings.backup_prefix.rstrip('/')}/ferrox-{timestamp}.dump"
    with tempfile.TemporaryDirectory() as temp_dir:
        output_path = str(Path(temp_dir) / "ferrox.dump")
        command, env = postgres_command(settings.database_url, "pg_dump", output_path)
        runner(command, check=True, env=env, capture_output=True)
        content = Path(output_path).read_bytes()
        if not content:
            raise RuntimeError("pg_dump produced an empty backup")
        storage.put_bytes(key, content, "application/octet-stream")
    _prune_backups(storage, settings.backup_prefix, settings.backup_retention_count)
    logger.info("PostgreSQL backup stored at %s", key)
    return key


def _prune_backups(storage: ObjectStorage, prefix: str, retention_count: int) -> None:
    keys = sorted(storage.list_keys(prefix), reverse=True)
    for key in keys[retention_count:]:
        storage.delete(key)


def run_loop() -> None:
    settings = get_settings()
    while True:
        try:
            run_backup(settings)
        except Exception:
            logger.exception("Scheduled PostgreSQL backup failed")
        time.sleep(settings.backup_interval_seconds)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Back up PostgreSQL to configured object storage")
    parser.add_argument("--loop", action="store_true", help="Run continuously using BACKUP_INTERVAL_SECONDS")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    if args.loop:
        run_loop()
    else:
        print(run_backup())
