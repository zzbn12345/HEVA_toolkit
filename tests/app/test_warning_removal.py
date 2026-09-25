"""Tests for explanation-free warning removal in sentence review."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from heva.app.main import create_app
from heva.curation.people_registry import PersonRecord, activate_curator, add_person
from heva.curation.project_registry import sync_registry
from heva.curation.review_state import initialize_sentence_reviews


def test_reviewer_can_remove_all_warnings_without_explanations(tmp_path: Path) -> None:
    documents = tmp_path / "documents"
    documents.mkdir()
    (documents / "source.pdf").write_bytes(b"source")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / ".heva/project.json").read_text())
    document_id = registry["documents"][0]["document_id"]
    package = tmp_path / registry["documents"][0]["package_path"]
    (package / "annotations.json").write_text(
        json.dumps([{
            "sentence_id": 1,
            "page": 1,
            "sentence": "Historic harbour",
            "tokens": ["Historic", "harbour"],
            "values": ["historic"],
            "entities": [{
                "start": 0,
                "end": 16,
                "text": "Historic harbour",
                "label": "historic",
                "color": "#FF40FF",
            }],
            "ner_tags": ["B-historic", "I-historic"],
            "schema_version": "1.0",
        }]),
        encoding="utf-8",
    )
    initialize_sentence_reviews(tmp_path, document_id)
    curator = add_person(
        tmp_path,
        PersonRecord(name="Review Curator", roles=["curator"]),
    )
    activate_curator(tmp_path, curator.person_id)

    response = TestClient(create_app(tmp_path)).put(
        f"/api/review/{document_id}/warnings"
    )

    assert response.status_code == 200
    assert response.json()["removed_warning_count"] == 1
    assert response.json()["sentences"][0]["flags"] == []
    review = json.loads(
        (tmp_path / ".heva/documents" / document_id / "review-state.json").read_text()
    )
    event = review["sentences"][0]["audit"][-1]
    assert event["event"] == "warning_accepted"
    assert event["details"]["comment"] is None


def test_warning_controls_do_not_request_explanations() -> None:
    root = Path(__file__).parents[2]
    template = (root / "src/heva/app/templates/review_document.html").read_text()
    script = (root / "src/heva/app/static/review_document.js").read_text()

    assert 'id="remove-all-warnings"' in template
    assert "Optional note explaining why this warning is acceptable" not in script
    assert '"Remove warning"' in script
    assert '/api/review/${encodeURIComponent(documentId)}/warnings' in script
    assert "removeAllWarnings" in script
