"""Acceptance tests for the first researcher-facing web interface slice."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from heva.app.main import create_app
from heva.workflow.color_mapping import (
    confirm_color_configuration,
    propose_color_configuration,
    resolve_color,
    save_color_configuration,
)
from heva.workflow.project_registry import sync_registry
from heva.workflow.review_state import initialize_sentence_reviews


def test_home_offers_create_and_validate_without_inline_assets(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))

    response = client.get("/")

    assert response.status_code == 200
    assert "Welcome to HEVA" in response.text
    assert "Open existing project" in response.text
    assert "Create from source folder" in response.text
    assert "Add or prepare documents" in response.text
    assert "Validate this project" in response.text
    assert 'href="/static/app.css"' in response.text
    assert 'src="/static/home.js?v=3"' in response.text
    assert "<style>" not in response.text
    assert 'href="/"' in response.text


def test_app_starts_without_exposing_repository_documents() -> None:
    client = TestClient(create_app())

    project = client.get("/api/project")
    protected = client.get("/api/annotator", follow_redirects=False)

    assert project.status_code == 404
    assert project.json()["code"] == "no_active_project"
    assert protected.status_code == 409
    assert protected.json()["code"] == "no_active_project"


def test_existing_project_can_be_opened_and_closed(tmp_path: Path) -> None:
    project_root = tmp_path / "existing-project"
    sources = project_root / "documents"
    sources.mkdir(parents=True)
    (sources / "source.pdf").write_bytes(b"source")
    sync_registry(project_root, source_dir="documents")
    client = TestClient(create_app())

    opened = client.post(
        "/api/projects/open",
        json={"path": str(project_root)},
    )
    status = client.get("/api/project")
    closed = client.post("/api/projects/close")
    after_close = client.get("/api/project")

    assert opened.status_code == 200
    assert opened.json()["document_count"] == 1
    assert status.json()["project_root"] == str(project_root.resolve())
    assert closed.json() == {"closed": True}
    assert after_close.status_code == 404


def test_project_can_be_created_from_a_source_folder(tmp_path: Path) -> None:
    source_folder = tmp_path / "new-project"
    source_folder.mkdir()
    (source_folder / "annotated.pdf").write_bytes(b"source")
    (source_folder / "notes.txt").write_text("not a source", encoding="utf-8")
    client = TestClient(create_app())

    created = client.post(
        "/api/projects/create",
        json={"path": str(source_folder)},
    )
    status = client.get("/api/project")

    assert created.status_code == 200
    assert created.json()["document_count"] == 1
    assert (source_folder / "data/project-registry.json").is_file()
    assert status.json()["source_directory"] == "."
    assert status.json()["documents"][0]["source_path"] == "annotated.pdf"


def test_open_and_create_project_report_wrong_folder_usage(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    client = TestClient(create_app())

    opened = client.post("/api/projects/open", json={"path": str(empty)})
    created = client.post("/api/projects/create", json={"path": str(empty)})

    assert opened.status_code == 422
    assert "not a HEVA project" in opened.json()["detail"]
    assert created.status_code == 422
    assert "No PDF or DOCX" in created.json()["detail"]


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
    assert "Document citation" in response.text
    assert "<span>Citation</span>" in response.text
    assert 'src="/static/create.js?v=8"' in response.text
    assert 'href="/static/create.css?v=4"' in response.text
    assert "Individual" in response.text
    assert "Batch" in response.text
    assert 'id="pdf-preview"' in response.text
    assert 'id="toggle-pdf"' in response.text
    assert 'href="/">← HEVA home</a>' in response.text
    assert "<script>" not in response.text
    assert 'id="confirm-citation"' in response.text
    assert 'id="extraction-progress"' in response.text
    assert 'id="proposal-progress"' in response.text
    assert 'id="propose-colors"' in response.text
    assert 'id="batch-mapping"' in response.text
    assert 'id="apply-batch-mapping"' in response.text
    assert 'id="rebuild-annotations"' in response.text
    assert "#FFFF00" not in response.text
    assert "Label not decided" not in response.text


def test_color_review_api_loads_the_document_palette(tmp_path: Path) -> None:
    sources = tmp_path / "documents"
    sources.mkdir()
    (sources / "source.pdf").write_bytes(b"source")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / "data/project-registry.json").read_text())
    document_id = registry["documents"][0]["document_id"]
    save_color_configuration(
        tmp_path,
        document_id,
        propose_color_configuration(
            ["#CCCC00"],
            generic_suggestions={"#CCCC00": "political"},
        ),
    )
    client = TestClient(create_app(tmp_path))

    response = client.get(f"/api/documents/{document_id}/colors")

    assert response.status_code == 200
    result = response.json()
    assert result["configuration"]["colors"][0]["hex"] == "#CCCC00"
    assert result["configuration"]["colors"][0]["suggested_label"] == "political"
    assert "political" in result["labels"]
    assert result["automatic_proposal_available"] is False


def test_automatic_color_proposal_route_reports_generated_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sources = tmp_path / "documents"
    sources.mkdir()
    (sources / "source.pdf").write_bytes(b"source")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / "data/project-registry.json").read_text())
    document_id = registry["documents"][0]["document_id"]
    save_color_configuration(
        tmp_path,
        document_id,
        propose_color_configuration(["#CCCC00"]),
    )
    monkeypatch.setattr(
        "heva.app.routes.project.generate_automatic_color_proposals",
        lambda root, selected_id: 1,
    )
    client = TestClient(create_app(tmp_path))

    available = client.get(f"/api/documents/{document_id}/colors")
    proposed = client.post(f"/api/documents/{document_id}/colors/propose")

    assert available.json()["automatic_proposal_available"] is True
    assert proposed.status_code == 200
    assert proposed.json()["proposed_color_count"] == 1


def test_batch_color_candidates_explain_palette_mismatch(tmp_path: Path) -> None:
    sources = tmp_path / "documents"
    sources.mkdir()
    (sources / "source.pdf").write_bytes(b"source")
    (sources / "target.pdf").write_bytes(b"target")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / "data/project-registry.json").read_text())
    ids = {
        Path(item["source_path"]).name: item["document_id"]
        for item in registry["documents"]
    }
    source = propose_color_configuration(["#CCCC00"])
    source = resolve_color(source, "#CCCC00", label="political")
    source = confirm_color_configuration(source, confirmed_by="Reviewer")
    save_color_configuration(tmp_path, ids["source.pdf"], source)
    save_color_configuration(
        tmp_path,
        ids["target.pdf"],
        propose_color_configuration(["#FF66CC"]),
    )
    client = TestClient(create_app(tmp_path))

    response = client.get(
        f"/api/documents/{ids['source.pdf']}/colors/batch"
    )

    assert response.status_code == 200
    candidate = response.json()["candidates"][0]
    assert candidate["palette_matches"] is False
    assert candidate["eligible"] is False
    assert "Palette mismatch" in candidate["reason"]


def test_extraction_interface_has_progress_timeout_and_visible_errors() -> None:
    script = (
        Path(__file__).parents[2] / "src" / "heva" / "app" / "static" / "create.js"
    ).read_text(encoding="utf-8")

    assert "new AbortController()" in script
    assert "progress.hidden = false" in script
    assert "progress.hidden = true" in script
    assert "Extraction did not finish within two minutes" in script
    assert "result.message" in script
    assert "/colors/propose" in script
    assert "Automatic proposals did not finish in time" in script
    assert "/extraction" in script
    assert "?force=true" in script
    assert "must be rebuilt" in script


def test_extraction_endpoint_passes_deliberate_force_rebuild(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def fake_run(root, document_id, *, force):
        calls.append((document_id, force))
        package = tmp_path / "package"
        return SimpleNamespace(
            document_id=document_id,
            annotations_path=package / "annotations.json",
            session_path=package / "extraction-session.json",
            record_count=3,
            reused_checkpoint=False,
            warnings=(),
        )

    monkeypatch.setattr(
        "heva.app.routes.project.run_registered_extraction",
        fake_run,
    )
    client = TestClient(create_app(tmp_path))

    response = client.post("/api/documents/HEVA-TEST/extract?force=true")

    assert response.status_code == 200
    assert calls == [("HEVA-TEST", True)]


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


def test_legacy_annotations_receive_pending_review_state_when_queue_opens(
    tmp_path: Path,
) -> None:
    sources = tmp_path / "documents"
    sources.mkdir()
    (sources / "source.pdf").write_bytes(b"source")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / "data/project-registry.json").read_text())
    entry = registry["documents"][0]
    package = tmp_path / entry["package_path"]
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
    (package / "annotations.json").write_text(
        json.dumps([canonical]),
        encoding="utf-8",
    )
    client = TestClient(create_app(tmp_path))

    selected = client.get(f"/api/review/{entry['document_id']}")
    queue = client.get("/api/review-queue")

    assert selected.status_code == 200
    assert selected.json()["sentences"][0]["review"]["status"] == "pending"
    assert queue.status_code == 200
    assert queue.json()["documents"][0]["review_available"] is True
    review = json.loads((package / "review-state.json").read_text())
    assert review["sentences"][0]["status"] == "pending"
    assert review["sentences"][0]["audit"] == []


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


def test_sentence_review_page_exposes_selected_batch_controls(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))

    response = client.get("/review/HEVA-TEST")

    assert response.status_code == 200
    assert 'src="/static/review_document.js?v=6"' in response.text
    assert 'href="/static/review.css?v=6"' in response.text
    assert 'value="to_check"' in response.text
    assert 'value="problematic"' in response.text
    assert 'value="checked"' in response.text
    assert 'id="select-visible"' in response.text
    assert 'data-batch-status="approved"' in response.text
    assert 'data-batch-status="needs_correction"' in response.text
    assert 'data-batch-status="excluded"' in response.text
    assert 'id="sentence-editor"' in response.text
    assert 'id="edit-entities"' in response.text
    assert 'id="edit-tokens"' not in response.text
    assert 'id="edit-ner-tags"' not in response.text
    assert 'id="review-citation-link"' in response.text
    assert 'id="review-colors-link"' in response.text
    assert 'href="/annotator"' in response.text
    assert 'id="review-readiness"' in response.text
    assert 'id="submit-document-review"' in response.text
    assert "raw JSON" not in response.text


def test_sentence_review_asset_limits_batch_actions_to_visible_selection() -> None:
    script = (
        Path(__file__).parents[2]
        / "src"
        / "heva"
        / "app"
        / "static"
        / "review_document.js"
    ).read_text(encoding="utf-8")

    assert "visibleSentences" in script
    assert "selectedSentenceIds" in script
    assert '.slice(0, limit)' in script
    assert "Select this visible batch" not in script
    assert "sentence_ids: sentenceIds" in script
    assert 'filter === "checked"' in script
    assert 'filter === "to_check"' in script
    assert '"Edit sentence"' in script
    assert "correctedRecord" in script
    assert "values: [...new Set" in script
    assert "locateExtraction" in script
    assert "deriveBioTags" in script
    assert "row.dataset.originalStart" in script
    assert "&section=citation" in script
    assert "&section=colors" in script
    assert "highlightedSentence(record)" in script
    assert 'textElement("mark", "annotation-highlight", text)' in script
    assert '"aria-label"' in script
    assert "entity-list" not in script
    assert "renderReadiness" in script
    assert "/submit" in script
    assert '"Submitted for curator review"' in script


def test_document_setup_asset_opens_requested_review_section() -> None:
    script = (
        Path(__file__).parents[2]
        / "src"
        / "heva"
        / "app"
        / "static"
        / "create.js"
    ).read_text(encoding="utf-8")

    assert 'parameters.get("section")' in script
    assert 'requestedSection === "citation"' in script
    assert 'requestedSection === "colors"' in script


def test_sentence_correction_route_validates_persists_and_audits(tmp_path: Path) -> None:
    sources = tmp_path / "documents"
    sources.mkdir()
    (sources / "source.pdf").write_bytes(b"source")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / "data/project-registry.json").read_text())
    entry = registry["documents"][0]
    package = tmp_path / entry["package_path"]
    original = {
        "sentence_id": 1,
        "page": 1,
        "sentence": "A historic port.",
        "tokens": ["A", "historic", "port", "."],
        "values": ["historic"],
        "entities": [{
            "start": 2,
            "end": 15,
            "text": "historic port",
            "label": "historic",
            "color": "#FFFF00",
        }],
        "ner_tags": ["O", "B-historic", "I-historic", "O"],
        "schema_version": "1.0",
    }
    (package / "annotations.json").write_text(json.dumps([original]), encoding="utf-8")
    initialize_sentence_reviews(tmp_path, entry["document_id"])
    client = TestClient(create_app(tmp_path))
    assert client.post("/api/annotators", json={"name": "Sentence Editor"}).status_code == 201
    corrected = {
        **original,
        "sentence": "A historic harbour.",
        "tokens": ["A", "historic", "harbour", "."],
        "entities": [{
            "start": 2,
            "end": 18,
            "text": "historic harbour",
            "label": "historic",
            "color": "#FFFF00",
        }],
    }

    response = client.put(
        f"/api/review/{entry['document_id']}/sentences/1",
        json={"record": corrected},
    )

    assert response.status_code == 200
    assert response.json()["sentences"][0]["review"]["status"] == "needs_correction"
    saved = json.loads((package / "annotations.json").read_text())
    audit = json.loads((package / "review-state.json").read_text())
    assert saved[0]["sentence"] == "A historic harbour."
    assert audit["sentences"][0]["audit"][-1]["actor"] == "Sentence Editor"
    assert audit["sentences"][0]["audit"][-1]["details"]["before"] == original
    assert audit["sentences"][0]["audit"][-1]["details"]["after"] == corrected


def test_invalid_sentence_correction_reports_field_and_preserves_record(tmp_path: Path) -> None:
    sources = tmp_path / "documents"
    sources.mkdir()
    (sources / "source.pdf").write_bytes(b"source")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / "data/project-registry.json").read_text())
    entry = registry["documents"][0]
    package = tmp_path / entry["package_path"]
    original = {
        "sentence_id": 1,
        "page": 1,
        "sentence": "A historic port.",
        "tokens": ["A", "historic", "port", "."],
        "values": ["historic"],
        "entities": [{
            "start": 2, "end": 15, "text": "historic port",
            "label": "historic", "color": "#FFFF00",
        }],
        "ner_tags": ["O", "B-historic", "I-historic", "O"],
        "schema_version": "1.0",
    }
    (package / "annotations.json").write_text(json.dumps([original]), encoding="utf-8")
    initialize_sentence_reviews(tmp_path, entry["document_id"])
    client = TestClient(create_app(tmp_path))
    client.post("/api/annotators", json={"name": "Sentence Editor"})
    invalid = {**original, "ner_tags": ["O"]}

    response = client.put(
        f"/api/review/{entry['document_id']}/sentences/1",
        json={"record": invalid},
    )

    assert response.status_code == 422
    assert "$.ner_tags" in response.json()["action"]
    assert json.loads((package / "annotations.json").read_text()) == [original]


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


def test_registered_document_citation_can_be_confirmed_by_active_annotator(
    tmp_path: Path,
) -> None:
    sources = tmp_path / "documents"
    sources.mkdir()
    (sources / "source.pdf").write_bytes(b"not-a-real-pdf")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / "data/project-registry.json").read_text())
    document_id = registry["documents"][0]["document_id"]
    client = TestClient(create_app(tmp_path))
    client.post("/api/annotators", json={"name": "Citation Reviewer"})

    proposal = client.get(f"/api/documents/{document_id}/citation")
    confirmed = client.post(
        f"/api/documents/{document_id}/citation/confirm",
        json={
            "title": "Source",
            "creators": ["Research Author"],
            "citation": "Research Author. Source.",
            "reference": "https://example.org/source",
            "not_findable_reason": None,
        },
    )

    assert proposal.status_code == 200
    assert "title" in proposal.json()["proposed_fields"]
    assert confirmed.status_code == 200
    assert confirmed.json()["human_confirmed"] is True
    assert confirmed.json()["confirmed_by"] == "Citation Reviewer"


def test_citation_confirmation_explains_missing_findability(tmp_path: Path) -> None:
    sources = tmp_path / "documents"
    sources.mkdir()
    (sources / "source.pdf").write_bytes(b"not-a-real-pdf")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / "data/project-registry.json").read_text())
    document_id = registry["documents"][0]["document_id"]
    client = TestClient(create_app(tmp_path))
    client.post("/api/annotators", json={"name": "Citation Reviewer"})

    response = client.post(
        f"/api/documents/{document_id}/citation/confirm",
        json={
            "title": "Source",
            "creators": ["Research Author"],
            "citation": "Research Author. Source.",
        },
    )

    assert response.status_code == 422
    assert "DOI/public URL" in response.json()["detail"]


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
