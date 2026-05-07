from __future__ import annotations

from fastapi.testclient import TestClient


def test_current_job_is_null_when_idle(client: TestClient) -> None:
    response = client.get("/api/jobs/current")

    assert response.status_code == 200
    assert response.json() == {"job": None}


def test_interrupt_when_no_job_returns_409(client: TestClient) -> None:
    response = client.post("/api/jobs/current/interrupt")

    assert response.status_code == 409


def test_clear_when_no_job_succeeds(client: TestClient) -> None:
    response = client.post("/api/jobs/current/clear")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
