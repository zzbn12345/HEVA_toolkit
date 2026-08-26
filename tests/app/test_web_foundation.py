"""Acceptance tests for the first researcher-facing web interface slice."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

from fastapi.testclient import TestClient
import pytest

from heva.app.main import create_app
from heva.app.routes import project as project_routes
from heva.workflow.color_mapping import (
    ColorMappingError,
    confirm_color_configuration,
    propose_color_configuration,
    resolve_color,
    save_color_configuration,
)
from heva.workflow.project_registry import register_external_source, sync_registry
from heva.workflow.package_validator import PackageValidationError
from heva.workflow.extraction_draft import (
    ExtractionDraftError,
    persist_extraction_draft,
)
from heva.workflow.people_registry import PersonRecord, activate_curator, add_person
from heva.workflow.review_state import initialize_sentence_reviews


def test_home_only_offers_project_selection_without_inline_assets() -> None:
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert "Welcome to HEVA" in response.text
    assert "Open existing project" in response.text
    assert "Create from source folder" in response.text
    assert "Add or prepare documents" not in response.text
    assert "Validate this project" not in response.text
    assert "HEVA project workspace" not in response.text
    assert 'href="/static/app.css?v=4"' in response.text
    assert 'src="/static/home.js?v=9"' in response.text
    assert "Choose folder and open" in response.text
    assert "Choose source folder" in response.text
    assert "HEVA Toolkit for annotation" in response.text
    assert 'class="sidebar"' not in response.text
    assert 'class="workflow"' not in response.text
    assert 'name="path"' not in response.text
    assert "<style>" not in response.text
    assert 'href="/"' in response.text
    assert 'href="/guide"' in response.text


def test_bundled_guide_is_available_without_an_open_project() -> None:
    client = TestClient(create_app())

    home = client.get("/guide")
    installation = client.get("/guide/INSTALLATION")

    assert home.status_code == 200
    assert "<h1" in home.text
    assert "HEVA Toolkit" in home.text
    assert 'href="/guide/INSTALLATION"' in home.text
    assert 'href="/guide/SOFTWARE_DESIGN"' in home.text
    assert "Create or open a project" not in home.text
    assert "Curator decisions" not in home.text
    assert "Approved releases" not in home.text
    assert "Essential guide" in home.text
    assert "DOCUMENTATION_NAVIGATION" not in home.text
    assert "DOCUMENTATION_CONTENT" not in home.text
    assert installation.status_code == 200
    assert "Install and run HEVA" in installation.text
    assert 'href="/guide/TUTORIAL"' in installation.text
    assert 'href="/static/documentation.css?v=1"' in installation.text


def test_guide_rejects_unknown_or_traversing_pages() -> None:
    client = TestClient(create_app())

    missing = client.get("/guide/not-a-page")
    traversal = client.get("/guide/../README", follow_redirects=False)

    assert missing.status_code == 404
    assert traversal.status_code in {303, 307, 404}


def test_internal_curator_submission_surfaces_are_not_exposed(tmp_path: Path) -> None:
    """Repository governance is not a reachable Alpha application workflow."""

    client = TestClient(create_app(tmp_path))

    assert client.get("/curation").status_code == 404
    assert client.get("/api/curation/HEVA-TEST").status_code == 404
    assert client.post("/api/review/HEVA-TEST/submit").status_code == 404
    assert client.post("/api/curation/HEVA-TEST/decisions").status_code == 404
    assert client.post("/api/curation/HEVA-TEST/data-owner-approval").status_code == 404


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
    home = client.get("/", follow_redirects=False)
    main_page = client.get("/")
    status = client.get("/api/project")
    closed = client.post("/api/projects/close")
    after_close = client.get("/api/project")

    assert opened.status_code == 200
    assert opened.json()["document_count"] == 1
    assert home.status_code == 303
    assert home.headers["location"] == "/review"
    assert "Review one document at a time" in main_page.text
    assert status.json()["project_name"] == "existing-project"
    assert "project_root" not in status.json()
    assert closed.json() == {"closed": True}
    assert after_close.status_code == 404


def test_open_reports_new_sources_and_session_decisions_are_explicit(tmp_path: Path) -> None:
    """New PDFs are offered on open and dismissal is never persisted to project data."""

    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "known.pdf").write_bytes(b"known")
    sync_registry(project_root, source_dir=".")
    (project_root / "accept.pdf").write_bytes(b"accept")
    (project_root / "dismiss.pdf").write_bytes(b"dismiss")
    client = TestClient(create_app())

    opened = client.post("/api/projects/open", json={"path": str(project_root)})
    dismissed = client.post(
        "/api/projects/source-scan/dismiss",
        json={"source_paths": ["dismiss.pdf"]},
    )
    after_dismiss = client.get("/api/projects/source-scan")
    accepted = client.post(
        "/api/projects/source-scan/accept",
        json={"source_paths": ["accept.pdf"]},
    )

    assert opened.json()["source_scan"]["discovered"] == ["accept.pdf", "dismiss.pdf"]
    assert dismissed.json()["scope"] == "current_session"
    assert after_dismiss.json()["discovered"] == ["accept.pdf"]
    assert len(accepted.json()["registered_document_ids"]) == 1
    registry = json.loads((project_root / ".heva/project.json").read_text())
    assert {item["source_path"] for item in registry["documents"]} == {
        "known.pdf",
        "accept.pdf",
    }

    client.post("/api/projects/close")
    client.post("/api/projects/open", json={"path": str(project_root)})
    assert client.get("/api/projects/source-scan").json()["discovered"] == ["dismiss.pdf"]


def test_review_queue_registers_new_project_documents_automatically(tmp_path: Path) -> None:
    """Opening the main project view immediately includes unseen supported sources."""

    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "known.pdf").write_bytes(b"known")
    sync_registry(project_root, source_dir=".")
    (project_root / "new-document.docx").write_bytes(b"new")
    client = TestClient(create_app(project_root))

    response = client.get("/api/review-queue")

    assert response.status_code == 200
    result = response.json()
    assert len(result["added_document_ids"]) == 1
    assert {item["source_path"] for item in result["documents"]} == {
        "known.pdf",
        "new-document.docx",
    }
    assert client.get("/api/projects/source-scan").json()["discovered"] == []


def test_existing_parent_root_project_moves_into_selected_source_folder(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "existing-project"
    sources = project_root / "documents"
    sources.mkdir(parents=True)
    (sources / "source.pdf").write_bytes(b"source")
    sync_registry(project_root, source_dir="documents")
    client = TestClient(create_app())

    opened = client.post(
        "/api/projects/open",
        json={"path": str(sources)},
    )

    assert opened.status_code == 200
    assert opened.json()["project_name"] == "documents"
    assert (sources / ".heva/project.json").is_file()
    assert not (project_root / ".heva").exists()
    relocated = json.loads((sources / ".heva/project.json").read_text())
    assert relocated["source_directory"] == "."
    assert relocated["documents"][0]["source_path"] == "source.pdf"
    assert relocated["documents"][0]["package_path"].startswith("documents/HEVA-")
    assert "project_root" not in opened.json()


def test_project_selection_is_not_restored_by_a_new_app_session(tmp_path: Path) -> None:
    project_root = tmp_path / "existing-project"
    sources = project_root / "documents"
    sources.mkdir(parents=True)
    (sources / "source.pdf").write_bytes(b"source")
    sync_registry(project_root, source_dir="documents")
    first = TestClient(create_app())
    opened = first.post("/api/projects/open", json={"path": str(project_root)})
    restored = TestClient(create_app()).get("/api/project")

    assert opened.status_code == 200
    assert restored.status_code == 404
    assert restored.json()["code"] == "no_active_project"


def test_native_folder_picker_returns_selection_without_uploading_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        project_routes,
        "select_local_folder",
        lambda prompt: str(tmp_path),
    )
    client = TestClient(create_app())

    response = client.post("/api/folders/select")

    assert response.status_code == 200
    assert response.json() == {"selected": True, "path": str(tmp_path)}


def test_native_source_picker_registers_external_file_without_copying(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The local app can bind an authorized source outside the dataset repository."""

    project = tmp_path / "dataset"
    project.mkdir()
    (project / "seed.pdf").write_bytes(b"seed")
    sync_registry(project, source_dir=".")
    external = tmp_path / "private-sources/source.pdf"
    external.parent.mkdir()
    external.write_bytes(b"external")
    monkeypatch.setattr(project_routes, "select_local_source_file", lambda prompt: str(external))
    client = TestClient(create_app())
    client.post("/api/projects/open", json={"path": str(project)})

    response = client.post("/api/files/select-source")

    assert response.status_code == 200
    assert response.json()["filename"] == "source.pdf"
    assert not (project / "source.pdf").exists()
    assert str(external) not in (project / ".heva/project.json").read_text()


def test_cancelled_native_folder_picker_is_not_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(project_routes, "select_local_folder", lambda prompt: None)
    client = TestClient(create_app())

    response = client.post("/api/folders/select")

    assert response.status_code == 200
    assert response.json() == {"selected": False, "path": ""}


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
    assert (source_folder / ".heva/project.json").is_file()
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


def test_create_rejects_source_folder_that_already_belongs_to_parent_project(
    tmp_path: Path,
) -> None:
    sources = tmp_path / "documents"
    sources.mkdir()
    (sources / "source.pdf").write_bytes(b"source")
    sync_registry(tmp_path, source_dir="documents")
    client = TestClient(create_app())

    response = client.post("/api/projects/create", json={"path": str(sources)})

    assert response.status_code == 409
    assert "sources of a HEVA project" in response.json()["detail"]


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
    assert "Active project curator" in response.text
    assert 'href="/people">Manage people and roles</a>' in response.text
    assert 'id="annotator-name"' not in response.text
    assert "Document citation" in response.text
    assert "<span>Citation</span>" in response.text
    assert 'src="/static/create.js?v=27"' in response.text
    assert 'href="/static/create.css?v=13"' in response.text
    assert "Individual" in response.text
    assert "Batch" in response.text
    assert 'id="pdf-preview"' in response.text
    assert 'id="toggle-pdf"' in response.text
    assert 'href="/">← HEVA home</a>' in response.text
    assert "<script>" not in response.text
    assert 'id="confirm-citation"' in response.text
    assert 'id="extraction-progress"' in response.text
    assert 'id="cancel-extraction"' in response.text
    assert 'id="proposal-progress"' in response.text
    assert 'id="color-code-list"' in response.text
    assert "Document color code" in response.text
    assert "Two shades of yellow may both mean the same label" in response.text
    assert "HEVA reference color code" in response.text
    assert 'id="reference-color-list"' in response.text
    assert 'id="discover-colors"' in response.text
    assert 'id="propose-colors"' in response.text
    assert 'id="batch-mapping"' in response.text
    assert 'id="apply-batch-mapping"' in response.text
    assert 'id="rebuild-annotations"' in response.text
    assert 'id="annotations-review"' in response.text
    assert "<span>Documents</span>" not in response.text
    assert "<span>Color review</span>" not in response.text
    assert '<span>Color config</span>' in response.text
    assert '<span>Annotations extracted</span>' in response.text
    assert '<span>Curated sentences</span>' in response.text
    assert '<span>Validated document</span>' in response.text
    assert "Step 1 of 4" not in response.text
    assert "Step 2 of 4" not in response.text
    assert 'data-readiness-key="curator"><b aria-hidden="true">×</b>' in response.text
    assert response.text.count('data-step-target="4"') == 3
    assert response.text.index('data-step="3"') < response.text.index('data-step="4"')
    assert response.text.index("<h1>Color configuration</h1>") < response.text.index(
        "<h1>Annotations</h1>"
    )
    assert "#FFFF00" not in response.text
    assert "Label not decided" not in response.text


def test_color_review_api_loads_the_document_palette(tmp_path: Path) -> None:
    sources = tmp_path / "documents"
    sources.mkdir()
    (sources / "source.pdf").write_bytes(b"source")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / ".heva/project.json").read_text())
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
    registry = json.loads((tmp_path / ".heva/project.json").read_text())
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


def test_confirmed_document_colors_create_and_select_reusable_project_palette(
    tmp_path: Path,
) -> None:
    """The GUI makes project-level immutable semantics usable without Python editing."""

    sources = tmp_path / "documents"
    sources.mkdir()
    (sources / "source.pdf").write_bytes(b"source")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / ".heva/project.json").read_text())
    document_id = registry["documents"][0]["document_id"]
    save_color_configuration(tmp_path, document_id, propose_color_configuration(["#CCCC00"]))
    client = TestClient(create_app(tmp_path))
    client.put("/api/annotator", json={"name": "Project Curator"})

    response = client.post(
        f"/api/documents/{document_id}/colors/confirm",
        json={"decisions": [{"hex": "#CCCC00", "label": "political"}]},
    )

    assert response.status_code == 200
    project_colors = json.loads((tmp_path / ".heva/color-configurations.json").read_text())
    assert project_colors["selected"]["configuration_id"] == "project-palette"
    assert project_colors["configurations"][0]["mappings"] == [
        {"label": "political", "hexes": ["#CCCC00"]}
    ]
    metadata = json.loads(
        (tmp_path / registry["documents"][0]["metadata_path"]).read_text()
    )
    assert metadata["color_configuration"]["human_confirmed"] is True
    queue = client.get("/api/review-queue").json()["documents"]
    selected = next(item for item in queue if item["document_id"] == document_id)
    assert selected["readiness_gates"]["color_configuration"] is True


def test_confirmed_colors_compile_saved_draft_without_rerunning_extraction(
    tmp_path: Path,
) -> None:
    """Color confirmation immediately promotes saved evidence for sentence review."""

    sources = tmp_path / "documents"
    sources.mkdir()
    (sources / "source.pdf").write_bytes(b"source")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / ".heva/project.json").read_text())
    document_id = registry["documents"][0]["document_id"]
    curator = add_person(tmp_path, PersonRecord(name="Researcher", roles=["curator"]))
    activate_curator(tmp_path, curator.person_id)
    persist_extraction_draft(
        tmp_path,
        document_id,
        [
            {
                "sentence_id": 1,
                "page": 1,
                "sentence": "Historic harbour",
                "tokens": ["Historic", "harbour"],
                "values": ["#CCCC00"],
                "entities": [
                    {
                        "start": 0,
                        "end": 16,
                        "text": "Historic harbour",
                        "label": "#CCCC00",
                    }
                ],
                "ner_tags": ["B-#CCCC00", "I-#CCCC00"],
            }
        ],
        extractor="test extractor",
        extractor_version="1.0",
    )
    save_color_configuration(
        tmp_path,
        document_id,
        propose_color_configuration(["#CCCC00"]),
    )
    client = TestClient(create_app(tmp_path))

    confirmed = client.post(
        f"/api/documents/{document_id}/colors/confirm",
        json={"decisions": [{"hex": "#CCCC00", "label": "historic"}]},
    )
    after = client.get(f"/api/documents/{document_id}/extraction").json()
    review = client.get(f"/api/review/{document_id}").json()

    assert confirmed.status_code == 200
    assert confirmed.json()["canonical_annotations"]["status"] == "canonical_saved"
    assert confirmed.json()["canonical_annotations"]["record_count"] == 1
    assert after["state"] == "current"
    assert after["extraction_scope"] == {"mode": "full_source", "selected_pages": []}
    assert after["record_count"] == 1
    assert review["draft_only"] is False
    assert review["sentences"][0]["record"]["values"] == ["historic"]


def test_failed_draft_compilation_preserves_raw_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A compilation failure remains actionable and never destroys collaborative evidence."""

    sources = tmp_path / "documents"
    sources.mkdir()
    (sources / "source.pdf").write_bytes(b"source")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / ".heva/project.json").read_text())
    document_id = registry["documents"][0]["document_id"]
    draft = tmp_path / ".heva" / "documents" / document_id / "extraction-draft.json"
    draft.parent.mkdir(parents=True, exist_ok=True)
    draft.write_text('{"preserved": true}\n', encoding="utf-8")
    original = draft.read_bytes()
    monkeypatch.setattr(
        project_routes,
        "promote_extraction_draft",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ExtractionDraftError("The selected palette does not resolve #CCCC00.")
        ),
    )
    client = TestClient(create_app(tmp_path))

    response = client.post(f"/api/documents/{document_id}/annotations/compile")

    assert response.status_code == 422
    assert response.json()["code"] == "annotation_compilation_failed"
    assert "#CCCC00" in response.json()["action"]
    assert draft.read_bytes() == original


def test_batch_color_candidates_explain_palette_mismatch(tmp_path: Path) -> None:
    sources = tmp_path / "documents"
    sources.mkdir()
    (sources / "source.pdf").write_bytes(b"source")
    (sources / "target.pdf").write_bytes(b"target")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / ".heva/project.json").read_text())
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


def test_batch_color_candidates_return_guidance_for_unconfirmed_source(
    tmp_path: Path,
) -> None:
    sources = tmp_path / "documents"
    sources.mkdir()
    (sources / "source.pdf").write_bytes(b"source")
    (sources / "target.pdf").write_bytes(b"target")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / ".heva/project.json").read_text())
    document_ids = [item["document_id"] for item in registry["documents"]]
    for document_id in document_ids:
        save_color_configuration(
            tmp_path,
            document_id,
            propose_color_configuration(["#CCCC00"]),
        )
    client = TestClient(create_app(tmp_path))

    response = client.get(f"/api/documents/{document_ids[0]}/colors/batch")

    assert response.status_code == 200
    assert response.json()["source_confirmed"] is False
    assert response.json()["candidates"][0]["eligible"] is False
    assert "Confirm the source mapping" in response.json()["candidates"][0]["reason"]


def test_extraction_interface_polls_background_stages_and_shows_errors() -> None:
    script = (
        Path(__file__).parents[2] / "src" / "heva" / "app" / "static" / "create.js"
    ).read_text(encoding="utf-8")

    assert "progress.hidden = false" in script
    assert "progress.hidden = true" in script
    assert "/extraction/progress" in script
    assert 'job.stage === "extracting" && job.total_pages' in script
    assert "job.completed_pages" in script
    assert "of ${job.total_pages} source pages" in script
    assert "Stage ${Math.min(job.completed_steps + 1, job.total_steps)}" in script
    assert "still running after ten minutes" in script
    assert "result.message" in script
    assert "/colors/propose" in script
    assert "Automatic proposals did not finish in time" in script
    assert "/extraction" in script
    assert "?force=${force}" in script
    assert "page_start=" in script
    assert "page_end=" in script
    assert "must be rebuilt" in script
    assert "await loadColors(documentId)" in script


def test_color_form_prefills_suggestions_without_presenting_model_reasoning() -> None:
    script = (
        Path(__file__).parents[2] / "src" / "heva" / "app" / "static" / "create.js"
    ).read_text(encoding="utf-8")

    assert "select.value = color.suggested_label" in script
    assert 'color.method === "document_legend"' in script
    assert "Document legend mapping:" in script
    assert "color.reasoning" not in script
    assert "No explanation was recorded" not in script
    assert "result.configuration.colors.length === 0" in script
    assert "/colors/discover" in script
    assert "function renderDocumentColorCode()" in script
    assert 'selected || "HEVA label not assigned"' in script
    assert 'arrow.textContent = "means"' in script
    assert "groups.entries()" in script
    assert 'fetch("/static/heva-reference-palette.json")' in script
    assert "function contrastingTextColor(hex)" in script


def test_extraction_endpoint_persists_raw_evidence_before_canonical_promotion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def fake_raw(
        root, document_id, *, progress_callback=None, cancellation_callback=None,
        selected_pages=None,
    ):
        calls.append(("raw", document_id))
        progress_callback(1, 4)
        progress_callback(4, 4)

    def fake_promote(root, document_id):
        calls.append(("canonical", document_id))
        package = tmp_path / "package"
        return SimpleNamespace(
            document_id=document_id,
            annotations_path=package / "annotations.json",
            session_path=package / "extraction-session.json",
            record_count=3,
            reused_checkpoint=False,
            warnings=(),
        )

    monkeypatch.setattr("heva.app.routes.project.run_registered_raw_extraction", fake_raw)
    monkeypatch.setattr("heva.app.routes.project.promote_extraction_draft", fake_promote)
    client = TestClient(create_app(tmp_path))

    response = client.post("/api/documents/HEVA-TEST/extract?force=true")

    assert response.status_code == 202
    assert calls == [("raw", "HEVA-TEST"), ("canonical", "HEVA-TEST")]
    progress = client.get("/api/documents/HEVA-TEST/extraction/progress").json()
    assert progress["state"] == "completed"
    assert progress["completed_steps"] == 3
    assert progress["completed_pages"] == 4
    assert progress["total_pages"] == 4
    assert progress["result"]["record_count"] == 3


def test_pending_color_map_keeps_successful_raw_extraction_as_draft(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The web app must not report saved raw evidence as a failed extraction."""

    calls = []

    def fake_raw(
        root, document_id, *, progress_callback=None, cancellation_callback=None,
        selected_pages=None,
    ):
        calls.append(("raw", document_id))

    def pending_map(root, document_id):
        raise ColorMappingError("Pending mapping requires CLI authorization.")

    monkeypatch.setattr("heva.app.routes.project.run_registered_raw_extraction", fake_raw)
    monkeypatch.setattr("heva.app.routes.project.promote_extraction_draft", pending_map)
    client = TestClient(create_app(tmp_path))

    response = client.post("/api/documents/HEVA-TEST/extract")

    assert response.status_code == 202
    assert calls == [("raw", "HEVA-TEST")]
    progress = client.get("/api/documents/HEVA-TEST/extraction/progress").json()
    assert progress["state"] == "draft_saved"
    assert "Raw extraction evidence was saved" in progress["message"]
    assert "Color config" in progress["message"]
    assert "--authorize-pending-map-by" not in progress["message"]


def test_missing_extraction_dependency_is_reported_clearly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing optional extractor package must become a useful UI error."""

    def missing_dependency(
        root, document_id, *, progress_callback=None, cancellation_callback=None,
        selected_pages=None,
    ):
        raise ModuleNotFoundError("No module named 'spacy'", name="spacy")

    monkeypatch.setattr(
        "heva.app.routes.project.run_registered_raw_extraction",
        missing_dependency,
    )
    client = TestClient(create_app(tmp_path))

    response = client.post("/api/documents/HEVA-TEST/extract")

    assert response.status_code == 202
    progress = client.get("/api/documents/HEVA-TEST/extraction/progress").json()
    assert progress["state"] == "failed"
    assert progress["error"]["code"] == "extraction_dependency_missing"
    assert "spacy" in progress["error"]["action"]
    assert "restart the server" in progress["error"]["action"]


def test_cancel_extraction_requires_an_active_job(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))

    response = client.post("/api/documents/HEVA-TEST/extraction/cancel")

    assert response.status_code == 409
    assert response.json()["code"] == "extraction_not_running"
    script = (
        Path(__file__).parents[2] / "src/heva/app/static/create.js"
    ).read_text(encoding="utf-8")
    assert "/extraction/cancel" in script
    assert 'job.state === "cancelled"' in script


def test_extraction_endpoint_validates_and_passes_selected_page_range(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected: list[int] | None = None

    def fake_raw(
        root, document_id, *, progress_callback=None, cancellation_callback=None,
        selected_pages=None,
    ):
        nonlocal selected
        selected = list(selected_pages) if selected_pages else None
        progress_callback(3, 3)

    def fake_promote(root, document_id):
        return SimpleNamespace(
            document_id=document_id,
            record_count=2,
            reused_checkpoint=False,
            warnings=(),
        )

    monkeypatch.setattr("heva.app.routes.project.run_registered_raw_extraction", fake_raw)
    monkeypatch.setattr("heva.app.routes.project.promote_extraction_draft", fake_promote)
    client = TestClient(create_app(tmp_path))

    incomplete = client.post("/api/documents/HEVA-TEST/extract?page_start=2")
    reversed_range = client.post(
        "/api/documents/HEVA-TEST/extract?page_start=4&page_end=2"
    )
    response = client.post(
        "/api/documents/HEVA-TEST/extract?page_start=2&page_end=4"
    )

    assert incomplete.status_code == 422
    assert reversed_range.status_code == 422
    assert response.status_code == 202
    assert selected == [2, 3, 4]
    progress = client.get("/api/documents/HEVA-TEST/extraction/progress").json()
    assert progress["result"]["selected_pages"] == [2, 3, 4]


def test_color_discovery_reports_missing_extraction_dependency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Color discovery must expose dependency failures instead of returning server errors."""

    def missing_dependency(root, document_id, *, progress_callback=None):
        raise ModuleNotFoundError("No module named 'spacy'", name="spacy")

    monkeypatch.setattr(
        "heva.app.routes.project.run_registered_raw_extraction",
        missing_dependency,
    )
    client = TestClient(create_app(tmp_path))

    response = client.post("/api/documents/HEVA-TEST/colors/discover")

    assert response.status_code == 503
    assert response.json()["code"] == "extraction_dependency_missing"
    assert "spacy" in response.json()["action"]


def test_color_discovery_exposes_raw_hex_evidence_to_the_interface(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The dedicated action connects raw extraction to the Color config step."""

    calls = []
    monkeypatch.setattr(
        "heva.app.routes.project.run_registered_raw_extraction",
        lambda root, document_id: calls.append(document_id),
    )
    monkeypatch.setattr(
        "heva.app.routes.project.load_extraction_draft",
        lambda root, document_id: SimpleNamespace(sentences=[object(), object()]),
    )
    monkeypatch.setattr(
        "heva.app.routes.project.load_color_configuration",
        lambda root, document_id: SimpleNamespace(colors=[object(), object(), object()]),
    )
    client = TestClient(create_app(tmp_path))

    response = client.post("/api/documents/HEVA-TEST/colors/discover")

    assert response.status_code == 200
    assert calls == ["HEVA-TEST"]
    assert response.json()["color_count"] == 3
    assert response.json()["sentence_count"] == 2


def test_annotator_is_persisted_in_project_collection(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))

    saved = client.put(
        "/api/annotator",
        json={"name": "Research Annotator", "orcid": "0000-0002-1825-0097"},
    )
    restored = client.get("/api/annotator")

    assert saved.status_code == 200
    assert restored.json()["annotator"]["name"] == "Research Annotator"
    collection = json.loads((tmp_path / ".heva/annotators.json").read_text())
    assert collection["active_annotator_id"]
    assert collection["annotators"][0]["name"] == "Research Annotator"
    assert collection["annotators"][0]["orcid"] == "0000-0002-1825-0097"


def test_people_and_roles_have_a_separate_project_view(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))

    response = client.get("/annotator")

    assert response.status_code == 200
    assert "People and workflow roles" in response.text
    assert "Original annotator" in response.text
    assert "Data owner" in response.text
    assert 'id="person-form"' in response.text
    assert 'id="people-list"' in response.text
    assert 'id="import-people"' in response.text
    assert 'src="/static/people.js?v=2"' in response.text
    assert 'href="/static/annotator.css?v=2"' in response.text
    assert "Add person" in response.text
    assert 'href="/">← HEVA home</a>' in response.text


def test_shared_record_forms_use_themed_controls_and_respect_hidden_actions() -> None:
    root = Path(__file__).parents[2] / "src" / "heva" / "app" / "static"
    form_styles = (root / "annotator.css").read_text(encoding="utf-8")
    app_styles = (root / "app.css").read_text(encoding="utf-8")

    assert ".json-editor form" in form_styles
    assert 'input:not([type="checkbox"]):not([type="radio"])' in form_styles
    assert ".json-editor fieldset > label" in form_styles
    assert ".json-editor select" in form_styles
    assert "[hidden] { display: none !important; }" in app_styles


def test_people_view_imports_a_validated_local_csv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = Path(__file__).parents[1] / "fixtures" / "people.csv"
    monkeypatch.setattr(project_routes, "select_local_csv_file", lambda _prompt: str(fixture))
    client = TestClient(create_app(tmp_path))

    response = client.post("/api/people/import-csv")

    assert response.status_code == 200
    assert response.json()["imported"] == 3
    assert response.json()["registry"]["active_curator_id"] == "PERSON-CURATOR01"
    assert (tmp_path / ".heva/people.json").is_file()


def test_people_form_supports_role_crud_and_active_curator(tmp_path: Path) -> None:
    """The GUI API edits validated people without conflating their responsibilities."""

    client = TestClient(create_app(tmp_path))
    created = client.post(
        "/api/people",
        json={
            "name": "Researcher",
            "roles": ["annotator", "curator"],
            "affiliation": "Heritage Lab",
        },
    )
    person_id = created.json()["person_id"]
    activated = client.post(f"/api/people/{person_id}/activate-curator")
    listed = client.get("/api/people")
    updated = client.put(
        f"/api/people/{person_id}",
        json={
            "person_id": person_id,
            "name": "Researcher",
            "roles": ["curator", "data_owner"],
            "affiliation": "Heritage Lab",
        },
    )

    assert created.status_code == 201
    assert activated.json()["active_curator_id"] == person_id
    assert listed.json()["active_curator_id"] == person_id
    assert updated.json()["roles"] == ["curator", "data_owner"]


def test_project_palette_view_appends_and_selects_immutable_versions(tmp_path: Path) -> None:
    """Researchers can manage reusable semantics without editing registry JSON."""

    client = TestClient(create_app(tmp_path))
    curator = client.post(
        "/api/people",
        json={"name": "Palette Curator", "roles": ["curator"]},
    ).json()
    client.post(f"/api/people/{curator['person_id']}/activate-curator")

    page = client.get("/project-colors")
    first = client.post(
        "/api/project-colors",
        json={
            "configuration_id": "research-palette",
            "name": "Research palette",
            "mappings": [{"label": "historic", "hexes": ["#FFFF00", "#FFF200"]}],
        },
    )
    second = client.post(
        "/api/project-colors",
        json={
            "configuration_id": "research-palette",
            "name": "Research palette",
            "description": "Revised after protocol review.",
            "mappings": [{"label": "political", "hexes": ["#FFFF00"]}],
        },
    )
    selected = client.post(
        "/api/project-colors/select",
        json={"configuration_id": "research-palette", "version": 1},
    )
    registry = client.get("/api/project-colors")

    assert page.status_code == 200
    assert "Versioned project palettes" in page.text
    assert first.json()["version"] == 1
    assert second.json()["version"] == 2
    assert selected.json()["version"] == 1
    assert len(registry.json()["configurations"]) == 2
    assert registry.json()["selected"]["version"] == 1


def test_project_palette_form_rejects_ambiguous_hex_meaning(tmp_path: Path) -> None:
    """The GUI cannot create one version where a color has competing labels."""

    client = TestClient(create_app(tmp_path))
    curator = client.post(
        "/api/people",
        json={"name": "Palette Curator", "roles": ["curator"]},
    ).json()
    client.post(f"/api/people/{curator['person_id']}/activate-curator")

    response = client.post(
        "/api/project-colors",
        json={
            "configuration_id": "ambiguous",
            "name": "Ambiguous",
            "mappings": [
                {"label": "historic", "hexes": ["#FFFF00"]},
                {"label": "political", "hexes": ["#FFFF00"]},
            ],
        },
    )

    assert response.status_code == 422
    assert "assigned to both" in response.json()["detail"]


def test_original_annotator_cannot_be_activated_as_curator_through_app(tmp_path: Path) -> None:
    """The interface enforces the same accountability rule as the domain contract."""

    client = TestClient(create_app(tmp_path))
    person = client.post(
        "/api/people",
        json={"name": "Original Annotator", "roles": ["annotator"]},
    ).json()

    response = client.post(f"/api/people/{person['person_id']}/activate-curator")

    assert response.status_code == 422
    assert "curator role" in response.json()["detail"]


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
    collection = json.loads((tmp_path / ".heva/annotators.json").read_text())
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


def test_app_preserves_selected_documents_in_release_download(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = tmp_path / "release"
    release.mkdir()
    (release / "datapackage.json").write_text("{}", encoding="utf-8")
    selections = []

    def fake_build_release(_root: Path, **options) -> Path:
        selections.append(options.get("document_ids"))
        return release

    monkeypatch.setattr(project_routes, "build_release", fake_build_release)
    client = TestClient(create_app(tmp_path))

    generated = client.post(
        "/api/release",
        json={"document_ids": ["HEVA-FIRST", "HEVA-SECOND"]},
    )
    downloaded = client.get(generated.json()["download"])

    assert generated.status_code == 200
    assert downloaded.status_code == 200
    assert selections == [
        ["HEVA-FIRST", "HEVA-SECOND"],
        ["HEVA-FIRST", "HEVA-SECOND"],
    ]


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
    assert (tmp_path / ".heva/annotators.json").is_file()


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
    registry = json.loads((tmp_path / ".heva/project.json").read_text())
    document_id = registry["documents"][0]["document_id"]
    client = TestClient(create_app(tmp_path))

    response = client.post("/api/validate")

    assert response.status_code == 200
    report = response.json()
    assert report["documents"][0]["document_id"] == document_id
    assert report["documents"][0]["valid"] is False
    assert report["documents"][0]["source_path"] == "documents/source.pdf"
    assert report["documents"][0]["completed"] is False
    assert report["summary"]["failed"] == 1
    assert all(issue["action"] for issue in report["documents"][0]["issues"])
    assert all(issue["guide"] for issue in report["documents"][0]["issues"])


def test_active_document_validation_returns_timestamped_shared_report(
    tmp_path: Path,
) -> None:
    """The document action uses the same validator contract as project and CLI checks."""

    sources = tmp_path / "documents"
    sources.mkdir()
    (sources / "source.pdf").write_bytes(b"source")
    sync_registry(tmp_path, source_dir="documents")
    document_id = json.loads((tmp_path / ".heva/project.json").read_text())["documents"][0]["document_id"]
    client = TestClient(create_app(tmp_path))
    registry_before = (tmp_path / ".heva/project.json").read_bytes()

    response = client.post(f"/api/review/{document_id}/validate")
    project_response = client.post("/api/validate")

    assert response.status_code == 200
    assert response.json()["checked_at"].endswith("+00:00")
    assert response.json()["document"]["document_id"] == document_id
    assert response.json()["document"]["valid"] is False
    assert response.json()["document"]["issues"]
    assert {
        issue["code"] for issue in response.json()["document"]["issues"]
    } == {
        issue["code"] for issue in project_response.json()["documents"][0]["issues"]
    }
    assert (tmp_path / ".heva/project.json").read_bytes() == registry_before


def test_active_document_validation_reports_server_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A validator exception becomes a finite, actionable HTTP response."""

    monkeypatch.setattr(
        "heva.app.routes.review.validate_document_package",
        lambda root, document_id: (_ for _ in ()).throw(PackageValidationError("broken metadata")),
    )
    client = TestClient(create_app(tmp_path))

    response = client.post("/api/review/HEVA-TEST/validate")

    assert response.status_code == 422
    assert response.json()["code"] == "document_validation_unavailable"
    assert "broken metadata" in response.json()["action"]


def test_validation_page_exposes_report_runner_filters_and_download(
    tmp_path: Path,
) -> None:
    client = TestClient(create_app(tmp_path))

    response = client.get("/validate")

    assert response.status_code == 200
    assert "Run validation" in response.text
    assert 'id="download-validation"' in response.text
    assert 'data-validation-filter="issues"' in response.text
    assert 'data-validation-filter="completed"' in response.text
    assert 'data-validation-filter="incomplete"' in response.text
    assert 'href="/static/app.css?v=7"' in response.text
    assert 'src="/static/notifications.js?v=1"' in response.text
    assert 'src="/static/validate.js?v=9"' in response.text
    assert 'href="/static/validation.css?v=3"' in response.text
    assert 'id="select-visible-documents"' in response.text
    assert "Select all shown" in response.text
    assert 'id="clear-document-selection"' in response.text
    assert "Export selected Data Package" in response.text
    assert 'id="generate-release"' in response.text
    assert 'id="download-release"' in response.text
    script = (
        Path(__file__).parents[2]
        / "src"
        / "heva"
        / "app"
        / "static"
        / "validate.js"
    ).read_text(encoding="utf-8")
    assert '"Read the relevant guide"' in script
    assert "/guide/${issue.guide" in script
    assert "filteredDocuments(currentReport).forEach" in script
    assert "selectedDocumentIds.add(documentReport.document_id)" in script
    assert "selectedDocumentIds.clear()" in script
    assert "updateReleaseSelection()" in script
    assert "document_ids: [...selectedDocumentIds]" in script
    assert 'id: "project-validation"' in script
    assert 'id: "data-package-export"' in script
    assert 'title: "Download initiated"' in script


def test_app_generates_and_downloads_only_release_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = tmp_path / "release"
    release.mkdir()
    (release / "datapackage.json").write_text('{"name":"demo"}', encoding="utf-8")
    (release / "heva-annotations.csv").write_text("sentence_id,text\n1,Demo\n", encoding="utf-8")
    (release / "source.pdf").write_bytes(b"must not be distributed")
    included = {"datapackage.json", "heva-annotations.csv"}

    def fake_build_release(_root: Path, **_options) -> Path:
        return release

    monkeypatch.setattr(project_routes, "build_release", fake_build_release)
    client = TestClient(create_app(tmp_path))

    generated = client.post("/api/release")
    first = client.get("/api/release/download")
    second = client.get("/api/release/download")

    assert generated.status_code == 200
    assert generated.json()["files"] == sorted(included)
    assert first.status_code == 200
    assert first.headers["content-type"] == "application/zip"
    assert first.content == second.content
    with ZipFile(BytesIO(first.content)) as archive:
        assert set(archive.namelist()) == {
            f"heva-data-package/{name}" for name in included
        }
        assert all(".pdf" not in name for name in archive.namelist())


def test_app_explains_release_gate_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_release(_root: Path, **_options) -> Path:
        raise PackageValidationError("Document lacks data-owner approval.")

    monkeypatch.setattr(project_routes, "build_release", fail_release)
    client = TestClient(create_app(tmp_path))

    response = client.post("/api/release")

    assert response.status_code == 422
    assert response.json()["code"] == "release_not_generated"
    assert response.json()["message"] == "Document lacks data-owner approval."
    assert response.json()["action"]


def test_dataset_metadata_page_safely_edits_validated_project_json(
    tmp_path: Path,
) -> None:
    client = TestClient(create_app(tmp_path))
    payload = {
        "name": "heritage-value-annotations",
        "title": "Heritage value annotations",
        "description": "Reviewed annotations for heritage-value research.",
        "creators": ["Research team"],
        "contributors": ["Example annotator"],
        "license": "CC-BY-4.0",
        "rights": "Only annotation derivatives are distributed.",
        "known_limitations": ["Not representative of every heritage context."],
    }

    page = client.get("/dataset-metadata")
    empty = client.get("/api/dataset-metadata")
    saved = client.put("/api/dataset-metadata", json=payload)
    loaded = client.get("/api/dataset-metadata")

    assert page.status_code == 200
    assert "Describe the dataset" in page.text
    assert 'src="/static/dataset_metadata.js?v=1"' in page.text
    assert empty.json() == {"configured": False, "metadata": None}
    assert saved.status_code == 200
    assert loaded.json()["metadata"] == payload
    assert json.loads((tmp_path / "dataset-metadata.json").read_text()) == payload


def test_dataset_metadata_api_rejects_blank_release_requirements(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))

    response = client.put(
        "/api/dataset-metadata",
        json={
            "name": "Not a package name",
            "title": " ",
            "description": " ",
            "creators": [" "],
            "contributors": [],
            "license": " ",
            "rights": " ",
            "known_limitations": [" "],
        },
    )

    assert response.status_code == 422
    assert not (tmp_path / "dataset-metadata.json").exists()


def test_review_queue_opens_only_one_document_at_a_time(tmp_path: Path) -> None:
    sources = tmp_path / "documents"
    sources.mkdir()
    (sources / "one.pdf").write_bytes(b"one")
    (sources / "two.pdf").write_bytes(b"two")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / ".heva/project.json").read_text())
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
        "curator",
        "original_annotator",
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
    registry = json.loads((tmp_path / ".heva/project.json").read_text())
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
    review = json.loads((tmp_path / ".heva/documents" / entry["document_id"] / "review-state.json").read_text())
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
    assert 'href="/validate">Validate project</a>' in response.text
    assert 'href="/validate#data-package">Export Data Package</a>' in response.text


def test_sentence_review_page_exposes_selected_batch_controls(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))

    response = client.get("/review/HEVA-TEST")

    assert response.status_code == 200
    assert 'src="/static/review_document.js?v=17"' in response.text
    assert 'id="edit-source-sentence"' in response.text
    assert "Source sentence — read only" in response.text
    assert 'href="/static/review.css?v=14"' in response.text
    assert 'id="review-extraction-panel" class="review-extraction-panel" open' in response.text
    assert 'id="review-page-start"' in response.text
    assert 'id="review-page-end"' in response.text
    assert 'id="review-run-extraction"' in response.text
    script = (
        Path(__file__).parents[2] / "src/heva/app/static/review_document.js"
    ).read_text(encoding="utf-8")
    assert "page_start=" in script
    assert "page_end=" in script
    assert "/extraction/cancel" in script
    assert "Re-extraction replaces this document's extracted draft" in script
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
    assert 'id="add-entity"' not in response.text
    assert 'id="edit-page" type="number" readonly' in response.text
    assert 'id="review-citation-link"' in response.text
    assert 'id="review-rights-link"' in response.text
    assert 'id="review-colors-link"' in response.text
    assert 'href="/people"' in response.text
    assert 'id="review-readiness"' in response.text
    assert 'id="validate-document"' in response.text
    assert 'id="document-validation-result"' in response.text
    assert 'id="submit-document-review"' not in response.text
    assert "Submit for curator review" not in response.text
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
    assert "filteredSentences.slice(pageStart, pageStart + limit)" in script
    assert "currentSentencePage += 1" in script
    assert "currentSentencePage -= 1" in script
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
    assert "row.dataset.label" in script
    assert "row.dataset.color" in script
    assert 'label: row.dataset.label' in script
    assert '"Remove"' not in script
    assert "new Option" not in script
    assert "&section=citation" in script
    assert "&section=colors" in script
    assert "highlightedSentence(record)" in script
    assert 'textElement("mark", "annotation-highlight", text)' in script
    assert '"aria-label"' in script
    assert "entity-list" not in script
    assert "renderReadiness" in script
    assert "/submit" not in script
    assert '"Submitted for curator review"' not in script
    assert '"Ready for validation"' in script
    assert "/validate" in script
    assert "renderDocumentValidation" in script
    assert "acceptWarning" in script
    assert "/warnings/" in script
    assert "Accept warning" in script
    assert "Accepted warning:" in script
    assert "validationCategory" in script
    assert 'return "People and roles"' in script
    assert "issue.severity" in script
    assert "issue.document_id" in script
    assert "issue.sentence_id" in script
    assert "issue.path" in script
    assert "Go to sentence" in script
    assert "scrollIntoView" in script
    assert 'button.textContent = "Validate document"' in script


def test_sentence_review_exposes_independent_pagination_controls(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))

    response = client.get("/review/HEVA-EXAMPLE")

    assert response.status_code == 200
    assert 'id="previous-sentence-page"' in response.text
    assert 'id="sentence-page-status"' in response.text
    assert 'id="next-sentence-page"' in response.text


def test_embedded_sentence_review_uses_parent_workflow_shell(tmp_path: Path) -> None:
    """Embedded review keeps its content but suppresses duplicate navigation and gates."""

    client = TestClient(create_app(tmp_path))

    embedded = client.get("/review/HEVA-EXAMPLE?embedded=1")
    standalone = client.get("/review/HEVA-EXAMPLE")
    styles = (
        Path(__file__).parents[2]
        / "src"
        / "heva"
        / "app"
        / "static"
        / "review.css"
    ).read_text(encoding="utf-8")

    assert 'class="review-body embedded-review"' in embedded.text
    assert 'class="review-body "' in standalone.text
    assert ".review-body.embedded-review .review-toolbar { display: none; }" in styles
    assert ".review-body.embedded-review .review-readiness > div" in styles
    assert 'id="validate-document"' in embedded.text
    script = (
        Path(__file__).parents[2]
        / "src"
        / "heva"
        / "app"
        / "static"
        / "review_document.js"
    ).read_text(encoding="utf-8")
    assert 'link.target = "_top"' in script


def test_shared_notifications_are_accessible_and_update_by_event_id() -> None:
    """One notification surface owns timing, severity, deduplication, and dismissal."""

    script = (
        Path(__file__).parents[2]
        / "src"
        / "heva"
        / "app"
        / "static"
        / "notifications.js"
    ).read_text(encoding="utf-8")

    assert 'notifications.id = "heva-notifications"' in script
    assert 'notifications.setAttribute("aria-label", "Application notifications")' in script
    assert 'type === "error" ? "alert" : "status"' in script
    assert 'data-notification-id=' in script
    assert "item.onmouseenter" in script
    assert "item.onfocusin" in script
    assert "window.hevaNotifications = {notify, dismiss}" in script


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
    assert 'requestedSection === "colors") showStep(3)' in script
    assert 'requestedSection === "annotations") showStep(4)' in script
    assert "result.draft_record_count > 0" in script
    assert "?embedded=1" in script
    assert "result.candidates.filter((candidate) => candidate.eligible)" in script
    assert "refreshAnnotationsReview()" in script
    assert "/annotations/compile" in script
    assert "compile-annotations" in script
    assert "automaticCompilationAttempts" in script
    assert 'button.querySelector("b").textContent = complete ? "✓" : "×"' in script
    assert 'setReadiness("curator", true' in script
    assert "citationIsReady" in script
    assert 'setReadiness("citation", ready' in script
    assert "refreshAnnotationsReview();" in script
    assert 'setReadiness("colors", confirmed' in script
    assert 'setReadiness("curated"' in script
    assert 'setReadiness("validated"' in script
    assert 'fetch("/api/validate", {method: "POST"})' in script
    assert "result.record_count > 0" in script
    template = (
        Path(__file__).parents[2]
        / "src"
        / "heva"
        / "app"
        / "templates"
        / "create.html"
    ).read_text(encoding="utf-8")
    styles = (
        Path(__file__).parents[2]
        / "src"
        / "heva"
        / "app"
        / "static"
        / "create.css"
    ).read_text(encoding="utf-8")
    assert "Build canonical annotations" in template
    assert "#draft-compilation" in styles
    assert "grid-template-columns: minmax(0, 1fr) max-content" in styles


def test_sentence_correction_route_validates_persists_and_audits(tmp_path: Path) -> None:
    sources = tmp_path / "documents"
    sources.mkdir()
    (sources / "source.pdf").write_bytes(b"source")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / ".heva/project.json").read_text())
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
    curator = add_person(
        tmp_path,
        PersonRecord(name="Sentence Curator", roles=["curator"]),
    )
    activate_curator(tmp_path, curator.person_id)
    corrected = {
        **original,
        "entities": [{
            "start": 11,
            "end": 15,
            "text": "port",
            "label": "historic",
            "color": "#FFFF00",
        }],
        "ner_tags": ["O", "O", "B-historic", "O"],
    }

    response = client.put(
        f"/api/review/{entry['document_id']}/sentences/1",
        json={"record": corrected},
    )

    assert response.status_code == 200
    assert response.json()["sentences"][0]["review"]["status"] == "needs_correction"
    saved = json.loads((package / "annotations.json").read_text())
    audit = json.loads((tmp_path / ".heva/documents" / entry["document_id"] / "review-state.json").read_text())
    assert saved[0]["sentence"] == "A historic port."
    assert saved[0]["entities"][0]["text"] == "port"
    assert audit["sentences"][0]["audit"][-1]["actor"] == "Sentence Curator"
    assert audit["sentences"][0]["audit"][-1]["details"]["before"] == original
    assert audit["sentences"][0]["audit"][-1]["details"]["after"] == corrected

    reloaded = client.get(f"/api/review/{entry['document_id']}")
    assert reloaded.status_code == 200
    assert reloaded.json()["sentences"][0]["record"]["entities"][0]["text"] == "port"


def test_invalid_sentence_correction_reports_field_and_preserves_record(tmp_path: Path) -> None:
    sources = tmp_path / "documents"
    sources.mkdir()
    (sources / "source.pdf").write_bytes(b"source")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / ".heva/project.json").read_text())
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


def test_sentence_correction_route_retains_source_and_returns_curated_text(
    tmp_path: Path,
) -> None:
    sources = tmp_path / "documents"
    sources.mkdir()
    (sources / "source.pdf").write_bytes(b"source")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / ".heva/project.json").read_text())
    entry = registry["documents"][0]
    package = tmp_path / entry["package_path"]
    original = {
        "sentence_id": 1,
        "page": 1,
        "sentence": "A historic prot.",
        "tokens": ["A", "historic", "prot", "."],
        "values": ["historic"],
        "entities": [{
            "start": 2, "end": 15, "text": "historic prot",
            "label": "historic", "color": "#FFFF00",
        }],
        "ner_tags": ["O", "B-historic", "I-historic", "O"],
        "schema_version": "1.0",
    }
    (package / "annotations.json").write_text(json.dumps([original]), encoding="utf-8")
    initialize_sentence_reviews(tmp_path, entry["document_id"])
    curator = add_person(tmp_path, PersonRecord(name="Sentence Curator", roles=["curator"]))
    activate_curator(tmp_path, curator.person_id)
    client = TestClient(create_app(tmp_path))
    corrected = {
        **original,
        "curated_sentence": "A historic port.",
        "tokens": ["A", "historic", "port", "."],
        "entities": [{
            "start": 2, "end": 15, "text": "historic port",
            "label": "historic", "color": "#FFFF00",
        }],
    }

    response = client.put(
        f"/api/review/{entry['document_id']}/sentences/1",
        json={"record": corrected},
    )

    assert response.status_code == 200
    returned = response.json()["sentences"][0]["record"]
    assert returned["sentence"] == "A historic prot."
    assert returned["curated_sentence"] == "A historic port."
    persisted = json.loads((package / "annotations.json").read_text())[0]
    assert persisted == corrected


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
    assert 'scopeLink.textContent = "Extraction scope"' in script
    assert "/create?document_id=" in script
    assert "&section=annotations" in script
    assert 'fetch("/api/projects/close", {method: "POST"})' in script


def test_sentence_editor_offers_individual_annotation_exclusion() -> None:
    script = (
        Path(__file__).parents[2]
        / "src"
        / "heva"
        / "app"
        / "static"
        / "review_document.js"
    ).read_text(encoding="utf-8")

    assert '"Exclude annotation"' in script
    assert "excluded_entity_indices" in script


def test_review_queue_can_close_or_switch_project(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    script = (
        Path(__file__).parents[2]
        / "src"
        / "heva"
        / "app"
        / "static"
        / "review_queue.js"
    ).read_text(encoding="utf-8")

    response = client.get("/review")

    assert response.status_code == 200
    assert 'id="open-another-project"' in response.text
    assert 'id="close-project"' in response.text
    assert 'id="stop-app"' in response.text
    assert 'href="/static/app.css?v=6"' in response.text
    assert 'src="/static/review_queue.js?v=8"' in response.text
    assert 'badge.textContent = item.annotation_complete ? "Complete" : "Incomplete"' in script
    assert "readiness_gates" in script
    assert 'fetch("/api/app/shutdown", {method: "POST"})' in script

    styles = (
        Path(__file__).parents[2]
        / "src"
        / "heva"
        / "app"
        / "static"
        / "app.css"
    ).read_text(encoding="utf-8")
    assert "container-type: inline-size" in styles
    assert "@container (max-width: 1000px)" in styles
    assert "grid-column: 3" in styles
    assert ".project-action .button { display: block; text-align: center; }" in styles


def test_local_app_can_request_a_graceful_shutdown(tmp_path: Path) -> None:
    calls = []
    client = TestClient(create_app(tmp_path, shutdown_handler=lambda: calls.append("stop")))

    response = client.post("/api/app/shutdown")

    assert response.status_code == 200
    assert response.json()["stopping"] is True
    assert calls == ["stop"]


def test_app_shutdown_explains_terminal_fallback_when_unavailable(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))

    response = client.post("/api/app/shutdown")

    assert response.status_code == 501
    assert "Ctrl+C" in response.json()["detail"]


def test_registered_pdf_can_be_loaded_for_immediate_edit_preview(tmp_path: Path) -> None:
    sources = tmp_path / "documents"
    sources.mkdir()
    pdf = sources / "source.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / ".heva/project.json").read_text())
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


def test_registered_external_pdf_can_be_previewed_without_exposing_its_path(
    tmp_path: Path,
) -> None:
    project = tmp_path / "dataset"
    project.mkdir()
    seed = project / "seed.pdf"
    seed.write_bytes(b"seed")
    sync_registry(project, source_dir=".")
    external = tmp_path / "protected-source.pdf"
    external.write_bytes(b"%PDF-1.4\nprotected\n%%EOF")
    document_id = register_external_source(project, external)
    client = TestClient(create_app(project))

    descriptor = client.get(f"/api/documents/{document_id}")
    preview = client.get(f"/api/review/{document_id}/source")

    assert descriptor.status_code == 200
    assert descriptor.json()["source_path"] == "external/protected-source.pdf"
    assert str(external) not in descriptor.text
    assert preview.status_code == 200
    assert preview.content == external.read_bytes()


def test_registered_document_citation_can_be_confirmed_by_active_annotator(
    tmp_path: Path,
) -> None:
    sources = tmp_path / "documents"
    sources.mkdir()
    (sources / "source.pdf").write_bytes(b"not-a-real-pdf")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / ".heva/project.json").read_text())
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


def test_document_rights_form_persists_explicit_distribution_boundaries(
    tmp_path: Path,
) -> None:
    sources = tmp_path / "documents"
    sources.mkdir()
    (sources / "source.pdf").write_bytes(b"authorized source")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / ".heva/project.json").read_text())
    document_id = registry["documents"][0]["document_id"]
    client = TestClient(create_app(tmp_path))
    client.get(f"/api/documents/{document_id}/citation")
    payload = {
        "access_level": "restricted",
        "authorization_status": "authorized",
        "authorization_date": "2026-08-12",
        "authorized_by": "Rights holder",
        "evidence_reference": "agreements/source-authorization",
        "source_distribution_allowed": False,
        "extracted_text_distribution_allowed": True,
        "annotation_distribution_allowed": True,
        "license": "CC-BY-4.0",
        "embargo_until": None,
    }

    page = client.get(f"/documents/{document_id}/rights")
    saved = client.put(f"/api/documents/{document_id}/rights", json=payload)
    loaded = client.get(f"/api/documents/{document_id}/rights")

    assert page.status_code == 200
    assert "Record rights and access" in page.text
    assert 'src="/static/document_rights.js?v=1"' in page.text
    assert saved.status_code == 200
    assert loaded.json() == payload


def test_citation_confirmation_explains_missing_findability(tmp_path: Path) -> None:
    sources = tmp_path / "documents"
    sources.mkdir()
    (sources / "source.pdf").write_bytes(b"not-a-real-pdf")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / ".heva/project.json").read_text())
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
