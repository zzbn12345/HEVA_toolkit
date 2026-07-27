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
    assert "Project annotator" in response.text
    assert 'href="/annotator">Manage annotator profile</a>' in response.text
    assert 'id="annotator-name"' not in response.text
    assert "Submission information" in response.text
    assert "Individual" in response.text
    assert "Batch" in response.text
    assert 'id="pdf-preview"' in response.text
    assert 'id="toggle-pdf"' in response.text
    assert 'href="/">← HEVA home</a>' in response.text
    assert "<script>" not in response.text


def test_annotator_is_persisted_in_project_collection(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))

    saved = client.put(
        "/api/annotator",
        json={"name": "Research Annotator", "orcid": "0000-0002-1825-0097"},
    )
    restored = client.get("/api/annotator")

    assert saved.status_code == 200
    assert restored.json()["annotator"]["name"] == "Research Annotator"
    collection = json.loads((tmp_path / "data/annotators.json").read_text())
    assert collection["active_annotator_id"]
    assert collection["annotators"][0]["name"] == "Research Annotator"
    assert collection["annotators"][0]["orcid"] == "0000-0002-1825-0097"


def test_annotator_profile_has_a_separate_project_view(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))

    response = client.get("/annotator")

    assert response.status_code == 200
    assert "Project annotators" in response.text
    assert 'id="schema-form"' in response.text
    assert 'id="generated-fields"' in response.text
    assert 'id="annotator-list"' in response.text
    assert 'id="schema-json"' in response.text
    assert 'id="data-json"' in response.text
    assert 'textarea id="data-json"' not in response.text
    assert "Apply JSON to form" not in response.text
    assert "cannot be edited here" in response.text
    assert "Add annotator" in response.text
    assert "Source authors, citation details" in response.text
    assert 'href="/">← HEVA home</a>' in response.text


def test_extended_annotator_profile_is_restored_across_documents(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))

    saved = client.put(
        "/api/annotator",
        json={
            "name": "  Research Annotator  ",
            "affiliation": "  Heritage Lab  ",
            "email": "  annotator@example.org  ",
            "orcid": "  0000-0002-1825-0097  ",
        },
    )
    restored = client.get("/api/annotator")

    assert saved.status_code == 200
    assert restored.json()["configured"] is True
    assert restored.json()["annotator"]["annotator_id"].startswith("ANN-")
    assert restored.json()["annotator"]["name"] == "Research Annotator"
    assert restored.json()["annotator"]["affiliation"] == "Heritage Lab"
    assert restored.json()["annotator"]["email"] == "annotator@example.org"
    assert restored.json()["annotator"]["orcid"] == "0000-0002-1825-0097"
    collection = json.loads((tmp_path / "data/annotators.json").read_text())
    assert collection["annotators"][0]["name"] == restored.json()["annotator"]["name"]


def test_missing_annotator_explains_registration_and_submission_boundary(
    tmp_path: Path,
) -> None:
    client = TestClient(create_app(tmp_path))

    response = client.get("/api/annotator")

    assert response.status_code == 200
    assert response.json()["configured"] is False
    assert response.json()["message"]
    assert response.json()["action"]


def test_annotator_schema_drives_form_and_requires_name(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))

    response = client.get("/api/annotators/schema")

    assert response.status_code == 200
    result = response.json()
    assert result["schema"]["required"] == ["name"]
    assert set(result["schema"]["properties"]) == {
        "name",
        "affiliation",
        "email",
        "orcid",
    }
    assert result["ui_schema"]["elements"][0]["scope"] == "#/properties/name"


def test_invalid_annotator_fields_are_rejected_by_backend_schema(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))

    response = client.post(
        "/api/annotators",
        json={
            "name": "Researcher",
            "email": "not-an-email",
            "orcid": "1234",
        },
    )

    assert response.status_code == 422
    issue_fields = {issue["loc"][-1] for issue in response.json()["detail"]}
    assert issue_fields == {"email", "orcid"}


def test_schema_form_uses_safe_fields_and_read_only_json_preview() -> None:
    script = (
        Path(__file__).parents[2] / "src" / "heva" / "app" / "static" / "annotator.js"
    ).read_text(encoding="utf-8")

    assert "input.pattern = concrete.pattern" in script
    assert "input.validationMessage" in script
    assert "dataEditor.textContent = JSON.stringify" in script
    assert "JSON.parse(dataEditor" not in script


def test_multiple_annotators_can_be_added_filtered_and_selected(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))

    first = client.post(
        "/api/annotators",
        json={"name": "First Annotator", "affiliation": "Heritage Lab"},
    )
    second = client.post(
        "/api/annotators",
        json={"name": "Second Annotator", "email": "second@example.org"},
    )
    collection = client.get("/api/annotators")
    activated = client.post(
        f"/api/annotators/{first.json()['annotator_id']}/activate"
    )
    active = client.get("/api/annotator")

    assert first.status_code == 201
    assert second.status_code == 201
    assert len(collection.json()["annotators"]) == 2
    assert collection.json()["active_annotator_id"] == second.json()["annotator_id"]
    assert activated.status_code == 200
    assert active.json()["annotator"]["name"] == "First Annotator"


def test_annotator_can_be_removed_without_rewriting_other_profiles(
    tmp_path: Path,
) -> None:
    client = TestClient(create_app(tmp_path))
    first = client.post("/api/annotators", json={"name": "First"}).json()
    second = client.post("/api/annotators", json={"name": "Second"}).json()

    removed = client.delete(f"/api/annotators/{second['annotator_id']}")

    assert removed.status_code == 200
    assert [item["annotator_id"] for item in removed.json()["annotators"]] == [
        first["annotator_id"]
    ]
    assert removed.json()["active_annotator_id"] == first["annotator_id"]


def test_legacy_single_annotator_is_migrated_to_collection(tmp_path: Path) -> None:
    legacy = tmp_path / "data" / "annotator.json"
    legacy.parent.mkdir()
    legacy.write_text(
        json.dumps({"name": "Legacy Annotator", "orcid": None}),
        encoding="utf-8",
    )
    client = TestClient(create_app(tmp_path))

    collection = client.get("/api/annotators")

    assert collection.status_code == 200
    assert collection.json()["annotators"][0]["name"] == "Legacy Annotator"
    assert (tmp_path / "data/annotators.json").is_file()


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
    assert queue.json()["documents"][0]["annotation_complete"] is False
    assert set(queue.json()["documents"][0]["readiness_gates"]) == {
        "citation",
        "color_configuration",
        "extraction",
        "sentence_review",
    }
    assert queue.json()["documents"][0]["blocking_reasons"]
    assert selected.json()["document_id"] == registry["documents"][0]["document_id"]
    assert len(selected.json()["sentences"]) == 1


def test_review_queue_page_exposes_list_columns(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))

    response = client.get("/review")

    assert response.status_code == 200
    assert "Document" in response.text
    assert "Workflow" in response.text
    assert "Sentence review" in response.text
    assert "Readiness" in response.text
    assert 'data-readiness="incomplete"' in response.text
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
    assert 'badge.textContent = item.annotation_complete ? "Complete" : "Incomplete"' in script
    assert "readiness_gates" in script


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
