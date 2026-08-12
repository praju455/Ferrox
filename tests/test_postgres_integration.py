import os

import pytest
from sqlalchemy import create_engine, inspect, text


@pytest.mark.postgres
def test_postgres_migrations_and_constraints():
    url = os.getenv("POSTGRES_TEST_URL")
    if not url:
        pytest.skip("POSTGRES_TEST_URL is not configured")
    engine = create_engine(url)
    inspector = inspect(engine)
    expected = {
        "products",
        "sources",
        "extracted_fields",
        "review_items",
        "batch_jobs",
        "batch_items",
        "pipeline_jobs",
        "citations",
        "llm_runs",
        "users",
    }
    assert expected.issubset(set(inspector.get_table_names()))
    assert any(index["unique"] for index in inspector.get_indexes("users") if index["name"] == "ix_users_email")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT current_database()")) == "ferrox_test"
