from datetime import datetime, timezone
from pathlib import Path

from app.backup import run_backup
from app.core.config import Settings
from app.services.storage import LocalObjectStorage


def test_backup_uses_pg_dump_and_prunes_old_objects(tmp_path):
    storage = LocalObjectStorage(str(tmp_path / "objects"))
    settings = Settings(
        database_url="postgresql+psycopg://ferrox:secret@db:5432/ferrox",
        backup_retention_count=2,
    )
    storage.put_bytes("backups/postgres/ferrox-20260101T000000Z.dump", b"old", "application/octet-stream")
    storage.put_bytes("backups/postgres/ferrox-20260102T000000Z.dump", b"newer", "application/octet-stream")
    captured = {}

    def fake_runner(command, **kwargs):
        captured["command"] = command
        captured["env"] = kwargs["env"]
        output_path = command[command.index("--file") + 1]
        Path(output_path).write_bytes(b"postgres-backup")

    key = run_backup(
        settings,
        storage,
        runner=fake_runner,
        now=datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc),
    )

    assert key == "backups/postgres/ferrox-20260812T120000Z.dump"
    assert captured["command"][0] == "pg_dump"
    assert "secret" not in " ".join(captured["command"])
    assert captured["env"]["PGPASSWORD"] == "secret"
    assert storage.open(key).read() == b"postgres-backup"
    assert storage.list_keys("backups/postgres") == [
        "backups/postgres/ferrox-20260102T000000Z.dump",
        key,
    ]
