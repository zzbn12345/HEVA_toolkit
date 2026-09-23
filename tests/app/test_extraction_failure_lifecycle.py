"""Regression coverage for terminal background-extraction failures."""

from pathlib import Path
import hashlib
import json
import shutil

import pytest
from fastapi.testclient import TestClient

from heva.app.main import create_app
from heva.curation.review_queue import list_review_queue


EXAMPLE = Path(__file__).parents[2] / "examples/source-diagnostics-dummy-project"


def test_unexpected_worker_failure_reaches_terminal_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A crashed worker must not leave the browser polling a permanently running job."""

    def crash(*args, **kwargs):
        raise UnboundLocalError("simulated worker bug")

    monkeypatch.setattr(
        "heva.app.routes.project.run_registered_raw_extraction",
        crash,
    )
    client = TestClient(create_app(tmp_path))

    queued = client.post("/api/documents/HEVA-TEST/extract")
    progress = client.get("/api/documents/HEVA-TEST/extraction/progress").json()

    assert queued.status_code == 202
    assert progress["state"] == "failed"
    assert progress["stage"] == "failed"
    assert progress["error"]["code"] == "unexpected_extraction_failure"


def test_broken_font_example_reaches_actionable_failed_state(tmp_path: Path) -> None:
    """The representative PDF must terminate polling instead of remaining in running."""

    project = tmp_path / "source-diagnostics-dummy-project"
    shutil.copytree(EXAMPLE, project)
    client = TestClient(create_app(project))

    queued = client.post("/api/documents/HEVA-DEMO-BROKEN-FONT/extract")
    progress = client.get(
        "/api/documents/HEVA-DEMO-BROKEN-FONT/extraction/progress"
    ).json()

    assert queued.status_code == 202
    assert progress["state"] == "failed"
    assert progress["stage"] == "failed"
    assert progress["error"]["code"] == "pdf_text_unreadable"
    assert "searchable Unicode text or apply OCR" in progress["error"]["action"]

    diagnosis = client.post(
        "/api/documents/HEVA-DEMO-BROKEN-FONT/source-diagnostics"
    )

    assert diagnosis.status_code == 200
    assert diagnosis.json()["affected_pages"] == [1, 2, 3, 4]
    assert diagnosis.json()["issues"][0]["code"] == "broken_unicode_mapping"
    assert diagnosis.json()["recommended_strategy"] == "ocr_span_alignment"
    assert diagnosis.json()["assistance_started"] is False

    source = project / "documents/broken-type3-font.pdf"
    source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    assisted = client.post(
        "/api/documents/HEVA-DEMO-BROKEN-FONT/ocr-candidate"
    )

    assert assisted.status_code == 200
    assert assisted.json()["status"] == "pending_review"
    assert assisted.json()["requires_review"] is True
    assert assisted.json()["record_count"] > 0
    assert assisted.json()["processed_pages"] == [1, 2, 3, 4]
    assert assisted.json()["canonical_data_changed"] is False
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_sha256
    workspace = project / ".heva/documents/HEVA-DEMO-BROKEN-FONT"
    assert (workspace / "ocr-candidate.json").is_file()
    assert not (workspace / "extraction-draft.json").exists()
    assert not (
        project / "documents/HEVA-DEMO-BROKEN-FONT/annotations.json"
    ).exists()

    preview = client.get(
        "/api/documents/HEVA-DEMO-BROKEN-FONT/ocr-candidate"
    )

    assert preview.status_code == 200
    assert len(preview.json()["records"]) == assisted.json()["record_count"]
    assert all(record["entities"] for record in preview.json()["records"])

    promoted = client.post(
        "/api/documents/HEVA-DEMO-BROKEN-FONT/ocr-candidate/promote"
    )

    assert promoted.status_code == 200
    assert promoted.json()["status"] == "promoted"
    assert promoted.json()["requires_sentence_review"] is True
    assert promoted.json()["canonical_data_changed"] is True
    assert promoted.json()["record_count"] == assisted.json()["record_count"]
    assert (workspace / "extraction-draft.json").is_file()
    annotations = project / "documents/HEVA-DEMO-BROKEN-FONT/annotations.json"
    assert annotations.is_file()
    assert len(json.loads(annotations.read_text(encoding="utf-8"))) == promoted.json()[
        "record_count"
    ]
    review = json.loads((workspace / "review-state.json").read_text(encoding="utf-8"))
    assert {sentence["status"] for sentence in review["sentences"]} == {"pending"}
    [queue_item] = list_review_queue(project)
    assert queue_item.readiness_gates["extraction"] is True
    assert queue_item.readiness_gates["sentence_review"] is False
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_sha256

    repeated = client.post("/api/documents/HEVA-DEMO-BROKEN-FONT/extract")

    assert repeated.status_code == 409
    assert repeated.json()["code"] == "extraction_already_current"
    assert "Continue with annotation review" in repeated.json()["action"]
    assert len(json.loads(annotations.read_text(encoding="utf-8"))) == promoted.json()[
        "record_count"
    ]


def test_create_interface_offers_diagnostics_only_for_unreadable_pdf_failure() -> None:
    root = Path(__file__).parents[2]
    template = (root / "src/heva/app/templates/create.html").read_text(encoding="utf-8")
    script = (root / "src/heva/app/static/create.js").read_text(encoding="utf-8")

    assert 'id="run-source-diagnostics"' in template
    assert 'job.error?.code !== "pdf_text_unreadable"' in script
    assert "/source-diagnostics" in script
    assert "HEVA has not started OCR or changed the source" in script
    assert 'id="start-ocr-assistance"' in template
    assert "/ocr-candidate" in script
    assert "will not replace existing annotations or extraction evidence" in script
    assert 'id="ocr-candidate-review"' in template
    assert 'id="promote-ocr-candidate"' in template
    assert "function loadOcrCandidate()" in script
    assert "/ocr-candidate/promote" in script
    assert "Review every sentence before validation or export" in script
    assert "extract.hidden = canonicalReady" in script
    assert "rebuild.hidden = !canonicalReady" in script


def test_ocr_assistance_requires_prior_unreadable_pdf_failure(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))

    response = client.post("/api/documents/HEVA-TEST/ocr-candidate")

    assert response.status_code == 409
    assert response.json()["code"] == "ocr_assistance_not_recommended"
