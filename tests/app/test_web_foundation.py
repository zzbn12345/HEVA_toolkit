"""Acceptance tests for the first researcher-facing web interface slice."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from heva.app.main import create_app
from heva.workflow.project_registry import sync_registry
from heva.workflow.review_state import initialize_sentence_reviews


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


def test_review_queue_opens_only_one_document_at_a_time(tmp_path: Path) -> None:
    sources = tmp_path / "documents"
    sources.mkdir()
    (sources / "one.pdf").write_bytes(b"one")
    (sources / "two.pdf").write_bytes(b"two")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / "data/project-registry.json").read_text())
    canonical = {
        "sentence_id": 1,
        "page": 1,
        "sentence": "Historic harbour.",
        "tokens": ["Historic", "harbour", "."],
        "values": ["historic"],
        "entities": [
            {
                "start": 0,
                "end": 17,
                "text": "Historic harbour",
                "label": "historic",
                "color": "#FF40FF",
            }
        ],
        "ner_tags": ["B-historic", "I-historic", "O"],
        "schema_version": "1.0",
    }
    for entry in registry["documents"]:
        package = tmp_path / entry["package_path"]
        (package / "annotations.json").write_text(json.dumps([canonical]), encoding="utf-8")
        initialize_sentence_reviews(tmp_path, entry["document_id"])
    client = TestClient(create_app(tmp_path))

    queue = client.get("/api/review-queue")
    selected = client.get(f"/api/review/{registry['documents'][0]['document_id']}")

    assert len(queue.json()["documents"]) == 2
    assert selected.json()["document_id"] == registry["documents"][0]["document_id"]
    assert len(selected.json()["sentences"]) == 1


def test_review_queue_page_exposes_list_columns(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))

    response = client.get("/review")

    assert response.status_code == 200
    assert "Document" in response.text
    assert "Status" in response.text
    assert "Completion" in response.text
    assert "Action" in response.text
    assert 'href="/create">＋ Add document</a>' in response.text


def test_review_queue_asset_always_offers_edit_annotation_action() -> None:
    script = (
        Path(__file__).parents[2]
        / "src"
        / "heva"
        / "app"
        / "static"
        / "review_queue.js"
    ).read_text(encoding="utf-8")

    assert 'link.textContent = "Edit this annotation"' in script
    assert "/create?document_id=" in script
    assert "/review/" in script


def test_registered_pdf_can_be_loaded_for_immediate_edit_preview(tmp_path: Path) -> None:
    sources = tmp_path / "documents"
    sources.mkdir()
    pdf = sources / "source.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / "data/project-registry.json").read_text())
    document_id = registry["documents"][0]["document_id"]
    client = TestClient(create_app(tmp_path))

    descriptor = client.get(f"/api/documents/{document_id}")
    source = client.get(f"/api/documents/{document_id}/source")

    assert descriptor.status_code == 200
    assert descriptor.json()["preview_available"] is True
    assert descriptor.json()["filename"] == "source.pdf"
    assert source.status_code == 200
    assert source.headers["content-type"] == "application/pdf"
    assert source.headers["content-disposition"].startswith("inline;")


def test_create_asset_loads_document_from_edit_query() -> None:
    script = (
        Path(__file__).parents[2] / "src" / "heva" / "app" / "static" / "create.js"
    ).read_text(encoding="utf-8")

    assert 'get("document_id")' in script
    assert "/api/documents/" in script
    assert "openPreview(" in script
    assert 'getElementById("new-document-source").hidden = true' in script


def test_add_document_mode_has_file_choice(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))

    response = client.get("/create")

    assert response.status_code == 200
    assert "Choose document file" in response.text
    assert ".pdf" in response.text
    assert ".docx" in response.text
