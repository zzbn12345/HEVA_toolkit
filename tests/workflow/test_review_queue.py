"""Acceptance tests for document-by-document review queue assembly."""

from __future__ import annotations

import json
from pathlib import Path

from heva.workflow.project_registry import sync_registry
from heva.workflow.review_queue import list_review_queue, load_review_document
from heva.workflow.review_state import initialize_sentence_reviews, record_decisions


def record(sentence_id: int, sentence: str) -> dict[str, object]:
    return {
        "sentence_id": sentence_id,
        "page": 1,
        "sentence": sentence,
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


def prepared_project(tmp_path: Path) -> list[dict[str, object]]:
    sources = tmp_path / "documents"
    sources.mkdir()
    (sources / "b.pdf").write_bytes(b"b")
    (sources / "a.pdf").write_bytes(b"a")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / "data/project-registry.json").read_text())
    for entry in registry["documents"]:
        package = tmp_path / entry["package_path"]
        (package / "annotations.json").write_text(
            json.dumps(
                [
                    record(1, "Historic harbour."),
                    record(2, "Short"),
                ]
            ),
            encoding="utf-8",
        )
        initialize_sentence_reviews(tmp_path, entry["document_id"])
    return registry["documents"]


def test_queue_summarizes_batches_but_keeps_documents_separate(tmp_path: Path) -> None:
    documents = prepared_project(tmp_path)
    first_id = documents[0]["document_id"]
    record_decisions(
        tmp_path,
        first_id,
        [1],
        status="approved",
        reviewer="Annotator",
    )

    queue = list_review_queue(tmp_path)

    assert len(queue) == 2
    assert queue[0].document_id == first_id
    assert queue[0].counts.approved == 1
    assert queue[0].counts.pending == 1
    assert queue[0].completion_percent == 50
    assert queue[1].counts.approved == 0
    assert queue[1].counts.pending == 2
    assert queue[1].completion_percent == 0


def test_needs_correction_is_not_counted_as_completed_review(tmp_path: Path) -> None:
    documents = prepared_project(tmp_path)
    document_id = documents[0]["document_id"]
    record_decisions(
        tmp_path,
        document_id,
        [1],
        status="needs_correction",
        reviewer="Annotator",
    )
    record_decisions(
        tmp_path,
        document_id,
        [2],
        status="excluded",
        reviewer="Annotator",
    )

    item = next(
        row for row in list_review_queue(tmp_path) if row.document_id == document_id
    )

    assert item.completion_percent == 50
    assert item.counts.needs_correction == 1
    assert item.counts.excluded == 1


def test_document_review_contains_only_selected_document_and_navigation(tmp_path: Path) -> None:
    documents = prepared_project(tmp_path)

    selected = load_review_document(tmp_path, documents[0]["document_id"])

    assert selected["document_id"] == documents[0]["document_id"]
    assert selected["previous_document_id"] is None
    assert selected["next_document_id"] == documents[1]["document_id"]
    assert [item["record"]["sentence_id"] for item in selected["sentences"]] == [1, 2]
    assert selected["sentences"][1]["flags"]
