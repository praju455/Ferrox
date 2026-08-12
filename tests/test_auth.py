import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.core.config import get_settings
from app.core.security import hash_password
from app.db import get_db
from app.models import User, UserRole


@pytest.fixture()
def auth_client(db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-that-is-long-enough-for-hs256")
    monkeypatch.delenv("INTERNAL_API_KEY", raising=False)
    get_settings.cache_clear()
    admin = User(
        email="admin@ferrox.test",
        full_name="Admin User",
        password_hash=hash_password("admin-password-123"),
        role=UserRole.admin,
    )
    db_session.add(admin)
    db_session.commit()
    app = create_app()

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    yield TestClient(app), db_session
    get_settings.cache_clear()


def login(client, email, password):
    response = client.post(
        "/api/v1/auth/token",
        data={"username": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_jwt_authentication_and_role_boundaries(auth_client):
    client, _ = auth_client
    assert client.get("/api/v1/products").status_code == 401

    admin_token = login(client, "admin@ferrox.test", "admin-password-123")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    reviewer_response = client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "email": "reviewer@ferrox.test",
            "password": "reviewer-password-123",
            "full_name": "Catalog Reviewer",
            "role": "reviewer",
        },
    )
    assert reviewer_response.status_code == 201

    reviewer_token = login(client, "reviewer@ferrox.test", "reviewer-password-123")
    reviewer_headers = {"Authorization": f"Bearer {reviewer_token}"}
    product_response = client.post(
        "/api/v1/products",
        headers=reviewer_headers,
        json={"name": "Reviewer-created pump"},
    )
    assert product_response.status_code == 201
    assert client.get("/api/v1/products", headers=reviewer_headers).status_code == 200
    assert client.get("/api/v1/observability/llm-runs", headers=reviewer_headers).status_code == 403
    assert client.post(
        "/api/v1/users",
        headers=reviewer_headers,
        json={
            "email": "blocked@ferrox.test",
            "password": "blocked-password-123",
            "full_name": "Blocked User",
        },
    ).status_code == 403

    users = client.get("/api/v1/users", headers=admin_headers)
    assert users.status_code == 200
    assert {user["role"] for user in users.json()} == {"admin", "reviewer"}


def test_inactive_user_token_is_rejected(auth_client):
    client, db_session = auth_client
    admin_token = login(client, "admin@ferrox.test", "admin-password-123")
    admin = db_session.query(User).filter_by(email="admin@ferrox.test").one()
    admin.is_active = False
    db_session.commit()

    response = client.get(
        "/api/v1/products",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 401
