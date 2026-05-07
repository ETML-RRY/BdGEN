from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_secrets_status_responds_with_json(client: TestClient) -> None:
    response = client.get("/api/secrets/status")

    assert response.status_code == 200
    assert isinstance(response.json(), dict)


def test_secrets_create_lock_unlock_round_trip(client: TestClient) -> None:
    create = client.post(
        "/api/secrets/create",
        json={"password": "good-pass", "secrets": {"OPENAI_API_KEY": "sk-test"}},
    )
    assert create.status_code == 200

    locked = client.post("/api/secrets/lock")
    assert locked.status_code == 200

    unlocked = client.post("/api/secrets/unlock", json={"password": "good-pass"})
    assert unlocked.status_code == 200


def test_secrets_unlock_with_wrong_password_returns_401(client: TestClient) -> None:
    client.post(
        "/api/secrets/create",
        json={"password": "right", "secrets": {}},
    )
    client.post("/api/secrets/lock")

    response = client.post("/api/secrets/unlock", json={"password": "wrong"})

    assert response.status_code == 401


def test_secrets_update_unknown_provider_returns_404(client: TestClient) -> None:
    response = client.put(
        "/api/secrets/providers/not-a-real-provider",
        json={"value": "v"},
    )

    assert response.status_code == 404


def test_secrets_delete_unknown_provider_returns_404(client: TestClient) -> None:
    response = client.request(
        "DELETE",
        "/api/secrets/providers/not-a-real-provider",
        json={},
    )

    assert response.status_code == 404
