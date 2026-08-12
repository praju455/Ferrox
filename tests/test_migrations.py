from pathlib import Path

from alembic import command
from alembic.config import Config

from app.db import Base


def test_initial_migration_tracks_current_model_tables():
    migration = Path("migrations/versions/20260812_0001_initial_schema.py").read_text()

    for table_name in Base.metadata.tables:
        assert f'"{table_name}"' in migration


def test_alembic_environment_uses_app_database_url():
    env = Path("migrations/env.py").read_text()

    assert "get_settings().database_url" in env
    assert "target_metadata = Base.metadata" in env


def test_initial_migration_upgrades_and_downgrades_sqlite(tmp_path, monkeypatch):
    database_path = tmp_path / "migration.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{database_path}")
    from app.core.config import get_settings

    get_settings.cache_clear()
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    get_settings.cache_clear()
