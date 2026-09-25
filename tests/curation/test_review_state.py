"""Acceptance tests for auditable per-sentence human review."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from heva.curation.document_metadata import PackageMetadata, save_package_metadata
from heva.curation.project_registry import sync_registry
from heva.curation.review_state import (
    ReviewError,
    accept_all_quality_warnings,
    accept_quality_warning,
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


def test_final_sentence_decision_updates_document_review_completion(tmp_path: Path) -> None:
    document_id, package = project(tmp_path)
    save_package_metadata(tmp_path, PackageMetadata(document_id=document_id))
    initialize_sentence_reviews(tmp_path, document_id)

    record_decisions(
        tmp_path, document_id, [1], status="approved", reviewer="Annotator"
    )
    incomplete = json.loads((package / "metadata.json").read_text())
    assert incomplete["annotation_process"]["review"]["completed"] is False
    assert incomplete["annotation_process"]["review"]["reviewed_at"] is None

    record_decisions(
        tmp_path, document_id, [2], status="excluded", reviewer="Annotator"
    )
    completed = json.loads((package / "metadata.json").read_text())
    assert completed["annotation_process"]["review"]["completed"] is True
    assert completed["annotation_process"]["review"]["reviewed_at"] is not None

    replacement = record(1)
    replacement["curated_sentence"] = "The historic harbor remains visible."
    replacement["tokens"] = ["The", "historic", "harbor", "remains", "visible", "."]
    replacement["entities"] = [{
        "start": 4, "end": 19, "text": "historic harbor",
        "label": "historic", "color": "#FF40FF",
    }]
    replace_sentence_record(
        tmp_path, document_id, 1, replacement, editor="Research Curator"
    )
    reset = json.loads((package / "metadata.json").read_text())
    assert reset["annotation_process"]["review"]["completed"] is False
    assert reset["annotation_process"]["review"]["reviewed_at"] is None


def test_edit_is_validated_read_back_and_audited(tmp_path: Path) -> None:
    document_id, package = project(tmp_path)
    initialize_sentence_reviews(tmp_path, document_id)
    replacement = record(1)
    replacement["entities"] = [{
        "start": 13, "end": 20, "text": "harbour",
        "label": "historic", "color": "#FF40FF",
    }]
    replacement["ner_tags"] = ["O", "O", "B-historic", "O", "O", "O"]

    replace_sentence_record(
        tmp_path, document_id, 1, replacement, editor="Research Annotator"
    )

    persisted = json.loads((package / "annotations.json").read_text())
    review = json.loads((tmp_path / ".heva/documents" / document_id / "review-state.json").read_text())
    assert persisted[0]["sentence"] == "The historic harbour remains visible."
    assert persisted[0]["entities"][0]["text"] == "harbour"
    assert review["sentences"][0]["status"] == "needs_correction"
    assert review["sentences"][0]["audit"][-1]["event"] == "edit"


def test_edit_rejects_changes_to_immutable_source_sentence(tmp_path: Path) -> None:
    document_id, package = project(tmp_path)
    initialize_sentence_reviews(tmp_path, document_id)
    replacement = record(1)
    replacement["sentence"] = "The historic port remains visible."
    replacement["tokens"] = ["The", "historic", "port", "remains", "visible", "."]
    replacement["entities"] = [{
        "start": 4, "end": 17, "text": "historic port",
        "label": "historic", "color": "#FF40FF",
    }]

    with pytest.raises(ReviewError, match="Source sentence evidence cannot be edited"):
        replace_sentence_record(
            tmp_path, document_id, 1, replacement, editor="Research Curator"
        )

    assert json.loads((package / "annotations.json").read_text())[0] == record(1)


def test_edit_persists_curated_sentence_without_replacing_source(tmp_path: Path) -> None:
    document_id, package = project(tmp_path)
    initialize_sentence_reviews(tmp_path, document_id)
    replacement = record(1)
    replacement["curated_sentence"] = "The historic harbor remains visible."
    replacement["tokens"] = ["The", "historic", "harbor", "remains", "visible", "."]
    replacement["entities"] = [{
        "start": 4, "end": 19, "text": "historic harbor",
        "label": "historic", "color": "#FF40FF",
    }]

    replace_sentence_record(
        tmp_path, document_id, 1, replacement, editor="Research Curator"
    )

    persisted = json.loads((package / "annotations.json").read_text())[0]
    assert persisted["sentence"] == "The historic harbour remains visible."
    assert persisted["curated_sentence"] == "The historic harbor remains visible."
    assert persisted["entities"][0]["text"] == "historic harbor"
    review = json.loads(
        (tmp_path / ".heva/documents" / document_id / "review-state.json").read_text()
    )
    assert review["sentences"][0]["audit"][-1]["actor"] == "Research Curator"


def test_edit_excludes_one_annotation_and_audits_exact_original(tmp_path: Path) -> None:
    document_id, package = project(tmp_path)
    original = record(1)
    original.update(
        sentence="Historic port and old harbour.",
        tokens=["Historic", "port", "and", "old", "harbour", "."],
        entities=[
            {
                "start": 0, "end": 13, "text": "Historic port",
                "label": "historic", "color": "#FF40FF",
            },
            {
                "start": 18, "end": 29, "text": "old harbour",
                "label": "historic", "color": "#FF40FF",
            },
        ],
        ner_tags=["B-historic", "I-historic", "O", "B-historic", "I-historic", "O"],
    )
    (package / "annotations.json").write_text(json.dumps([original]), encoding="utf-8")
    initialize_sentence_reviews(tmp_path, document_id)
    replacement = {
        **original,
        "entities": [original["entities"][1]],
        "ner_tags": ["O", "O", "O", "B-historic", "I-historic", "O"],
    }

    replace_sentence_record(
        tmp_path,
        document_id,
        1,
        replacement,
        editor="Research Curator",
        excluded_entity_indices=[0],
    )

    persisted = json.loads((package / "annotations.json").read_text())[0]
    assert persisted["entities"] == [original["entities"][1]]
    review = json.loads(
        (tmp_path / ".heva/documents" / document_id / "review-state.json").read_text()
    )
    audit = review["sentences"][0]["audit"][-1]
    assert audit["details"]["excluded_entities"] == [original["entities"][0]]


def test_edit_rejects_unidentified_annotation_removal(tmp_path: Path) -> None:
    document_id, package = project(tmp_path)
    initialize_sentence_reviews(tmp_path, document_id)
    replacement = record(1)
    replacement["entities"] = []
    replacement["values"] = []
    replacement["ner_tags"] = ["O", "O", "O", "O", "O", "O"]

    with pytest.raises(ReviewError, match="identified explicitly"):
        replace_sentence_record(
            tmp_path, document_id, 1, replacement, editor="Research Curator"
        )

    assert json.loads((package / "annotations.json").read_text())[0] == record(1)


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


def test_warning_acceptance_is_audited_and_survives_reload(tmp_path: Path) -> None:
    document_id, package = project(tmp_path)
    records = json.loads((package / "annotations.json").read_text())
    records[0]["sentence"] = "The historic harbour remains visible"
    records[0]["tokens"] = ["The", "historic", "harbour", "remains", "visible"]
    records[0]["ner_tags"] = ["O", "B-historic", "I-historic", "O", "O"]
    (package / "annotations.json").write_text(json.dumps(records), encoding="utf-8")
    review_path = initialize_sentence_reviews(tmp_path, document_id)

    accept_quality_warning(
        tmp_path,
        document_id,
        1,
        "likely_sentence_boundary_error",
        reviewer="Research Curator",
        comment="The source block intentionally ends here.",
    )

    reloaded = json.loads(review_path.read_text())
    sentence = reloaded["sentences"][0]
    assert sentence["accepted_warning_codes"] == ["likely_sentence_boundary_error"]
    assert sentence["audit"][-1]["event"] == "warning_accepted"
    assert sentence["audit"][-1]["actor"] == "Research Curator"
    assert sentence["audit"][-1]["details"]["comment"] == (
        "The source block intentionally ends here."
    )


def test_all_quality_warnings_can_be_removed_without_explanations(tmp_path: Path) -> None:
    document_id, package = project(tmp_path)
    records = json.loads((package / "annotations.json").read_text())
    for record_value in records:
        record_value["sentence"] = "The historic harbour remains visible"
        record_value["tokens"] = ["The", "historic", "harbour", "remains", "visible"]
        record_value["ner_tags"] = ["O", "B-historic", "I-historic", "O", "O"]
    (package / "annotations.json").write_text(json.dumps(records), encoding="utf-8")
    review_path = initialize_sentence_reviews(tmp_path, document_id)

    _, removed = accept_all_quality_warnings(
        tmp_path,
        document_id,
        reviewer="Research Curator",
    )

    assert removed == 2
    review = json.loads(review_path.read_text())
    for sentence in review["sentences"]:
        assert sentence["accepted_warning_codes"] == ["likely_sentence_boundary_error"]
        assert sentence["audit"][-1]["event"] == "warning_accepted"
        assert sentence["audit"][-1]["details"]["comment"] is None
