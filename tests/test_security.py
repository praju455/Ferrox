from fastapi.testclient import TestClient

from app.api import create_app
from app.core.config import get_settings
from app.db import get_db


def make_secured_client(db_session, monkeypatch, api_key: str | None):
    if api_key is None:
        monkeypatch.delenv("INTERNAL_API_KEY", raising=False)
    else:
        monkeypatch.setenv("INTERNAL_API_KEY", api_key)
    get_settings.cache_clear()
    app = create_app()

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


def test_mutating_routes_remain_open_when_internal_api_key_is_unset(client):
    response = client.post(
        "/api/v1/products/ingest/text",
        json={"product_name": "Open local dev", "text": "Manufacturer: TestCo. Model: T-1.", "source_identifier": "manual"},
    )

    assert response.status_code == 200


def test_mutating_routes_require_internal_api_key_when_configured(db_session, monkeypatch):
    client = make_secured_client(db_session, monkeypatch, "secret-key")

    response = client.post(
        "/api/v1/products/ingest/text",
        json={"product_name": "Secured dev", "text": "Manufacturer: TestCo. Model: T-2.", "source_identifier": "manual"},
    )

    assert response.status_code == 401


def test_mutating_routes_accept_x_api_key_header(db_session, monkeypatch):
    client = make_secured_client(db_session, monkeypatch, "secret-key")

    response = client.post(
        "/api/v1/products/ingest/text",
        headers={"X-API-Key": "secret-key"},
        json={"product_name": "Secured dev", "text": "Manufacturer: TestCo. Model: T-3.", "source_identifier": "manual"},
    )

    assert response.status_code == 200


def test_mutating_routes_accept_bearer_token(db_session, monkeypatch):
    client = make_secured_client(db_session, monkeypatch, "secret-key")

    response = client.post(
        "/api/v1/products/ingest/text",
        headers={"Authorization": "Bearer secret-key"},
        json={"product_name": "Secured dev", "text": "Manufacturer: TestCo. Model: T-4.", "source_identifier": "manual"},
    )

    assert response.status_code == 200
