"""Acceptance tests for immutable candidates and audited curator decisions."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

import pytest

from heva.workflow.curation_state import (
    CurationError,
    create_candidate_snapshot,
    load_curation_state,
    record_curator_decision,
    verify_current_candidate,
)
from heva.workflow.document_metadata import PackageMetadata
from heva.workflow.package_validator import approve_document
from tests.workflow.test_package_validator import project


def test_acceptance_is_bound_to_unchanged_candidate_and_marks_done(
    tmp_path: Path,
) -> None:
    document_id, _, registry_path = project(tmp_path)
    snapshot = create_candidate_snapshot(
        tmp_path,
        document_id,
        submitted_by="Annotator",
    )

    decision = record_curator_decision(
        tmp_path,
        document_id,
        decision="accepted",
        actor="Curator",
        evidence="Validator findings and source comparison reviewed.",
    )

    assert decision.candidate_id == snapshot.candidate_id
    assert decision.actor == "Curator"
    registry = json.loads(registry_path.read_text())
    assert registry["documents"][0]["status"] == "done"
    assert load_curation_state(tmp_path, document_id).current_decision() == decision


def test_requested_changes_reopen_annotation_and_are_audited(tmp_path: Path) -> None:
    document_id, _, registry_path = project(tmp_path)
    create_candidate_snapshot(tmp_path, document_id, submitted_by="Annotator")

    decision = record_curator_decision(
        tmp_path,
        document_id,
        decision="changes_requested",
        actor="Curator",
        evidence="Sentence 1 does not match the PDF.",
        requested_changes=["Correct sentence 1 extracted text."],
    )

    registry = json.loads(registry_path.read_text())
    assert decision.requested_changes == ["Correct sentence 1 extracted text."]
    assert registry["documents"][0]["status"] == "in_progress"


def test_changed_evidence_blocks_curator_decision(tmp_path: Path) -> None:
    document_id, package, _ = project(tmp_path)
    create_candidate_snapshot(tmp_path, document_id, submitted_by="Annotator")
    annotations = json.loads((package / "annotations.json").read_text())
    annotations[0]["sentence"] = "Changed after submission."
    (package / "annotations.json").write_text(json.dumps(annotations), encoding="utf-8")

    with pytest.raises(CurationError, match="changed after snapshot"):
        record_curator_decision(
            tmp_path,
            document_id,
            decision="accepted",
            actor="Curator",
            evidence="Attempted review.",
        )


def test_done_cannot_be_created_without_curator_acceptance(tmp_path: Path) -> None:
    document_id, _, registry_path = project(tmp_path)
    create_candidate_snapshot(tmp_path, document_id, submitted_by="Annotator")

    record_curator_decision(
        tmp_path,
        document_id,
        decision="rejected",
        actor="Curator",
        evidence="Rights evidence is not sufficient for this release.",
    )

    registry = json.loads(registry_path.read_text())
    assert registry["documents"][0]["status"] == "in_review"
    with pytest.raises(CurationError, match="already has"):
        record_curator_decision(
            tmp_path,
            document_id,
            decision="accepted",
            actor="Curator",
            evidence="Second decision is not permitted.",
        )


def test_citation_can_be_completed_after_annotation_curation(tmp_path: Path) -> None:
    document_id, package, registry_path = project(tmp_path)
    metadata_path = package / "metadata.json"
    metadata = PackageMetadata.model_validate_json(metadata_path.read_text(encoding="utf-8"))
    metadata.source.title = None
    metadata.source.creators = []
    metadata.source.citation = None
    metadata.source.reference = None
    metadata.source.human_confirmed = False
    metadata_path.write_text(metadata.model_dump_json(indent=2), encoding="utf-8")

    snapshot = create_candidate_snapshot(tmp_path, document_id, submitted_by="Annotator")
    assert snapshot.validator_report.valid is False
    assert snapshot.validator_report.curation_ready is True
    record_curator_decision(
        tmp_path,
        document_id,
        decision="accepted",
        actor="Curator",
        evidence="The annotations and source comparison were reviewed.",
    )

    metadata.source.title = "Harbour report"
    metadata.source.creators = ["Author"]
    metadata.source.citation = "Author. Harbour report."
    metadata.source.reference = "https://example.org/report"
    metadata.source.human_confirmed = True
    metadata.source.confirmed_by = "Data owner"
    metadata.source.confirmed_at = datetime.fromisoformat("2026-08-12T10:00:00+00:00")
    metadata_path.write_text(metadata.model_dump_json(indent=2), encoding="utf-8")

    assert verify_current_candidate(tmp_path, document_id).candidate_id == snapshot.candidate_id
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    assert registry["documents"][0]["status"] == "done"
