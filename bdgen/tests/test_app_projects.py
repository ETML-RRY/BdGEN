from __future__ import annotations

import json
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import make_project_payload
from bdgen.service import lifecycle
from bdgen.service.constants import PROJECT_CONFIG_NAME


def test_projects_list_is_empty_initially(client: TestClient) -> None:
    response = client.get("/api/projects")

    assert response.status_code == 200
    assert response.json() == {"projects": []}


def test_seed_example_project_imports_archive_once_on_empty_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_root = tmp_path / "output"
    config_root = tmp_path / "config"
    archive = tmp_path / "exemple.bdgen"
    _write_example_archive(archive)
    monkeypatch.setenv("BDGEN_CONFIG_ROOT", str(config_root))
    monkeypatch.setenv("BDGEN_EXAMPLE_ARCHIVE", str(archive))

    assert lifecycle.seed_example_project(output_root) == "exemple"
    assert (output_root / "exemple" / PROJECT_CONFIG_NAME).exists()
    assert (config_root / lifecycle.EXAMPLE_SEED_MARKER).exists()

    lifecycle.delete_project("exemple", output_root)

    assert lifecycle.seed_example_project(output_root) is None
    assert not (output_root / "exemple").exists()


def test_seed_example_project_skips_existing_user_projects(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_root = tmp_path / "output"
    config_root = tmp_path / "config"
    archive = tmp_path / "exemple.bdgen"
    _write_example_archive(archive)
    user_project = output_root / "demo"
    user_project.mkdir(parents=True)
    (user_project / PROJECT_CONFIG_NAME).write_text(json.dumps(make_project_payload("demo")), encoding="utf-8")
    monkeypatch.setenv("BDGEN_CONFIG_ROOT", str(config_root))
    monkeypatch.setenv("BDGEN_EXAMPLE_ARCHIVE", str(archive))

    assert lifecycle.seed_example_project(output_root) is None
    assert not (output_root / "exemple").exists()
    assert (config_root / lifecycle.EXAMPLE_SEED_MARKER).read_text(encoding="utf-8") == "skipped_existing_projects\n"


def test_create_project_then_appears_in_list(client: TestClient) -> None:
    created = client.post("/api/projects", json=make_project_payload("demo"))
    assert created.status_code == 200
    assert created.json() == {"name": "demo"}

    listed = client.get("/api/projects").json()
    assert len(listed["projects"]) == 1
    assert listed["projects"][0]["name"] == "demo"


def _write_example_archive(path: Path) -> None:
    payload = make_project_payload("exemple")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"exemple/{PROJECT_CONFIG_NAME}", json.dumps(payload))


def test_create_project_with_invalid_payload_returns_400(client: TestClient) -> None:
    response = client.post("/api/projects", json={"project": "demo"})

    assert response.status_code == 400


def test_create_project_without_project_field_returns_400(client: TestClient) -> None:
    payload = make_project_payload("demo")
    payload.pop("project")

    response = client.post("/api/projects", json=payload)

    assert response.status_code == 400


def test_create_duplicate_project_returns_409(client: TestClient) -> None:
    client.post("/api/projects", json=make_project_payload("demo"))

    response = client.post("/api/projects", json=make_project_payload("demo"))

    assert response.status_code == 409


def test_get_unknown_project_returns_404(client: TestClient) -> None:
    response = client.get("/api/projects/nope")

    assert response.status_code == 404


def test_get_existing_project_exposes_config_and_state(client: TestClient) -> None:
    client.post("/api/projects", json=make_project_payload("demo"))

    response = client.get("/api/projects/demo")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "demo"
    assert body["config"] is not None
    assert body["script"] is None  # no script generated yet
    assert "state" in body
    assert "references" in body


def test_update_project_rename_is_rejected(client: TestClient) -> None:
    client.post("/api/projects", json=make_project_payload("demo"))

    response = client.put("/api/projects/demo", json=make_project_payload("renamed"))

    assert response.status_code == 400


def test_update_unknown_project_returns_404(client: TestClient) -> None:
    response = client.put("/api/projects/nope", json=make_project_payload("nope"))

    assert response.status_code == 404


def test_delete_unknown_project_returns_404(client: TestClient) -> None:
    response = client.delete("/api/projects/nope")

    assert response.status_code == 404


def test_delete_existing_project_then_get_returns_404(client: TestClient) -> None:
    client.post("/api/projects", json=make_project_payload("demo"))

    deleted = client.delete("/api/projects/demo")
    assert deleted.status_code == 200

    response = client.get("/api/projects/demo")
    assert response.status_code == 404


def test_duplicate_unknown_project_returns_404(client: TestClient) -> None:
    response = client.post("/api/projects/nope/duplicate", json={})

    assert response.status_code == 404


def test_feedback_returns_empty_for_fresh_project(client: TestClient) -> None:
    client.post("/api/projects", json=make_project_payload("demo"))

    response = client.get("/api/projects/demo/feedback")

    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_serve_missing_project_file_returns_404(client: TestClient) -> None:
    client.post("/api/projects", json=make_project_payload("demo"))

    response = client.get("/api/projects/demo/files/nonexistent.png")

    assert response.status_code == 404
