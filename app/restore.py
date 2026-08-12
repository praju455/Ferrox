import argparse
import os
import subprocess
import tempfile
from pathlib import Path

from sqlalchemy.engine import make_url

from app.backup import postgres_command
from app.core.config import get_settings
from app.services.storage import build_object_storage


def restore_backup(key: str, confirmation: str) -> None:
    if confirmation != "RESTORE_DATABASE":
        raise ValueError("Restore requires --confirm RESTORE_DATABASE")
    settings = get_settings()
    storage = build_object_storage(settings)
    with tempfile.TemporaryDirectory() as temp_dir:
        backup_path = Path(temp_dir) / "ferrox.dump"
        with storage.open(key) as stream:
            backup_path.write_bytes(stream.read())
        command, env = postgres_command(settings.database_url, "pg_restore")
        database = make_url(settings.database_url).database
        command.extend(["--dbname", database or "ferrox", str(backup_path)])
        subprocess.run(command, check=True, env={**os.environ, **env})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Restore a Ferrox PostgreSQL object-store backup")
    parser.add_argument("--key", required=True)
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    restore_backup(args.key, args.confirm)
