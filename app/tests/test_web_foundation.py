"""Acceptance tests for the first researcher-facing web interface slice."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.heva_app.app import create_app
from src.project_registry import sync_registry


def test_home_offers_create_and_validate_without_inline_assets(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))

    response = client.get("/")

    assert response.status_code == 200
    assert "Welcome to HEVA" in response.text
    assert "Create a data package" in response.text
    assert "Validate this project" in response.text
    assert 'href="/static/app.css"' in response.text
    assert "<style>" not in response.text
    assert 'href="/"' in response.text


def test_project_status_restores_registry_summary(tmp_path: Path) -> None:
    sources = tmp_path / "documents"
    sources.mkdir()
    (sources / "source.pdf").write_bytes(b"source")
    sync_registry(tmp_path, source_dir="documents")
    client = TestClient(create_app(tmp_path))

    response = client.get("/api/project")

    assert response.status_code == 200
    assert response.json()["summary"]["total"] == 1
    assert response.json()["documents"][0]["status"] == "backlog"


def test_create_page_reuses_guided_pdf_review_patterns(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))

    response = client.get("/create")

    assert response.status_code == 200
    assert "Annotator identity" in response.text
    assert "Submission information" in response.text
    assert "Individual" in response.text
    assert "Batch" in response.text
    assert 'id="pdf-preview"' in response.text
    assert 'id="toggle-pdf"' in response.text
    assert 'href="/">← HEVA home</a>' in response.text
    assert "<script>" not in response.text


def test_annotator_is_persisted_in_project_json(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))

    saved = client.put(
        "/api/annotator",
        json={"name": "Research Annotator", "orcid": "0000-0002-1825-0097"},
    )
    restored = client.get("/api/annotator")

    assert saved.status_code == 200
    assert restored.json()["annotator"]["name"] == "Research Annotator"
    assert json.loads((tmp_path / "data/annotator.json").read_text()) == {
        "name": "Research Annotator",
        "orcid": "0000-0002-1825-0097",
    }


def test_missing_project_has_plain_language_corrective_action(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))

    response = client.get("/api/project")

    assert response.status_code == 404
    assert response.json()["code"] == "project_not_initialized"
    assert response.json()["action"]


def test_validation_endpoint_uses_package_validator(tmp_path: Path) -> None:
    sources = tmp_path / "documents"
    sources.mkdir()
    (sources / "source.pdf").write_bytes(b"source")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / "data/project-registry.json").read_text())
    document_id = registry["documents"][0]["document_id"]
    client = TestClient(create_app(tmp_path))

    response = client.post("/api/validate")

    assert response.status_code == 422
    report = response.json()
    assert report["documents"][0]["document_id"] == document_id
    assert report["documents"][0]["valid"] is False
    assert all(issue["action"] for issue in report["documents"][0]["issues"])
