from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_ok() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "orchestrator-api"}


def test_health_does_not_expose_secret_like_fields() -> None:
    payload = TestClient(app).get("/health").json()

    forbidden_keys = {"api_key", "token", "password", "secret", "database_url"}
    assert forbidden_keys.isdisjoint({key.lower() for key in payload})
