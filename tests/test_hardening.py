import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.core.config import get_settings
from app.db import get_db


def make_client(db_session):
    app = create_app()

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


def test_responses_include_request_id_and_security_headers(client):
    response = client.get("/api/v1/health", headers={"X-Request-ID": "test-request-123"})

    assert response.headers["X-Request-ID"] == "test-request-123"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "no-referrer"


def test_cors_allows_configured_frontend_origin(client):
    response = client.options(
        "/api/v1/products/ingest/text",
        headers={
            "Origin": "http://127.0.0.1:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-api-key",
        },
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:3000"


def test_local_network_url_ingestion_is_blocked(client):
    response = client.post(
        "/api/v1/products/ingest/url",
        json={"product_name": "Unsafe source", "url": "http://127.0.0.1/private"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Private network URLs are not supported"


def test_pdf_endpoint_rejects_non_pdf_upload(client):
    product_response = client.post(
        "/api/v1/products/ingest/text",
        json={"product_name": "Pump", "text": "Model P-1", "source_identifier": "manual"},
    )

    response = client.post(
        f"/api/v1/products/{product_response.json()['id']}/ingest/pdf",
        files={"file": ("notes.txt", b"not a pdf", "text/plain")},
    )

    assert response.status_code == 415


def test_production_requires_jwt_secret(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        create_app()

    get_settings.cache_clear()
