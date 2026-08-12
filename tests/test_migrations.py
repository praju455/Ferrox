from pathlib import Path

from app.db import Base


def test_initial_migration_tracks_current_model_tables():
    migration = Path("migrations/versions/20260812_0001_initial_schema.py").read_text()

    for table_name in Base.metadata.tables:
        assert f'"{table_name}"' in migration


def test_alembic_environment_uses_app_database_url():
    env = Path("migrations/env.py").read_text()

    assert "get_settings().database_url" in env
    assert "target_metadata = Base.metadata" in env
