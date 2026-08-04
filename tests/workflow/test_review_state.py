"""Acceptance tests for auditable per-sentence human review."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from heva.workflow.project_registry import sync_registry
from heva.workflow.review_state import (
    ReviewError,
    initialize_sentence_reviews,
    record_decisions,
    replace_sentence_record,
    submit_document_for_review,
)


def record(sentence_id: int) -> dict[str, object]:
    return {
        "sentence_id": sentence_id,
        "page": 1,
        "sentence": "The historic harbour remains visible.",
        "tokens": ["The", "historic", "harbour", "remains", "visible", "."],
        "values": ["historic"],
        "entities": [{
            "start": 4, "end": 20, "text": "historic harbour",
            "label": "historic", "color": "#FF40FF",
        }],
        "ner_tags": ["O", "B-historic", "I-historic", "O", "O", "O"],
        "schema_version": "1.0",
    }


def project(tmp_path: Path) -> tuple[str, Path]:
    sources = tmp_path / "documents"
    sources.mkdir()
    (sources / "source.pdf").write_bytes(b"source")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / ".heva/project.json").read_text())
    entry = registry["documents"][0]
    package = tmp_path / entry["package_path"]
    (package / "annotations.json").write_text(
        json.dumps([record(1), record(2)]),
        encoding="utf-8",
    )
    return entry["document_id"], package


def test_every_sentence_starts_pending_and_decisions_are_individual(tmp_path: Path) -> None:
    document_id, package = project(tmp_path)
    review_path = initialize_sentence_reviews(tmp_path, document_id)

    initial = json.loads(review_path.read_text())
    assert [item["status"] for item in initial["sentences"]] == ["pending", "pending"]

    record_decisions(
        tmp_path,
        document_id,
        [1, 2],
        status="approved",
        reviewer="Research Annotator",
    )
    reviewed = json.loads(review_path.read_text())

    assert all(len(item["audit"]) == 1 for item in reviewed["sentences"])
    assert all(item["reviewer"] == "Research Annotator" for item in reviewed["sentences"])


def test_document_cannot_enter_review_with_unresolved_sentences(tmp_path: Path) -> None:
    document_id, _ = project(tmp_path)
    initialize_sentence_reviews(tmp_path, document_id)
    record_decisions(
        tmp_path, document_id, [1], status="approved", reviewer="Annotator"
    )

    with pytest.raises(ReviewError, match="still require decisions"):
        submit_document_for_review(tmp_path, document_id)

    record_decisions(
        tmp_path, document_id, [2], status="excluded", reviewer="Annotator"
    )
    submit_document_for_review(tmp_path, document_id)
    registry = json.loads((tmp_path / ".heva/project.json").read_text())
    assert registry["documents"][0]["status"] == "in_review"


def test_edit_is_validated_read_back_and_audited(tmp_path: Path) -> None:
    document_id, package = project(tmp_path)
    initialize_sentence_reviews(tmp_path, document_id)
    replacement = record(1)
    replacement["sentence"] = "The historic port remains visible."
    replacement["tokens"] = ["The", "historic", "port", "remains", "visible", "."]
    replacement["entities"] = [{
        "start": 4, "end": 17, "text": "historic port",
        "label": "historic", "color": "#FF40FF",
    }]

    replace_sentence_record(
        tmp_path, document_id, 1, replacement, editor="Research Annotator"
    )

    persisted = json.loads((package / "annotations.json").read_text())
    review = json.loads((tmp_path / ".heva/documents" / document_id / "review-state.json").read_text())
    assert persisted[0]["sentence"] == "The historic port remains visible."
    assert review["sentences"][0]["status"] == "needs_correction"
    assert review["sentences"][0]["audit"][-1]["event"] == "edit"


def test_invalid_edit_names_contract_field_and_does_not_write(tmp_path: Path) -> None:
    document_id, package = project(tmp_path)
    initialize_sentence_reviews(tmp_path, document_id)
    replacement = record(1)
    replacement["entities"][0]["label"] = "invented"

    with pytest.raises(ReviewError, match=r"\$\.entities\[0\]\.label"):
        replace_sentence_record(
            tmp_path,
            document_id,
            1,
            replacement,
            editor="Research Annotator",
        )

    assert json.loads((package / "annotations.json").read_text())[0] == record(1)
