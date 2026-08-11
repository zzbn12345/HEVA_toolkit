"""Acceptance tests for per-document data-owner distribution approval."""

from __future__ import annotations

from pathlib import Path

import pytest

from heva.workflow.data_owner_approval import (
    DataOwnerApprovalError,
    approve_document_distribution,
    load_current_data_owner_approval,
)
from heva.workflow.people_registry import PersonRecord, add_person
from tests.workflow.test_package_validator import project
from heva.workflow.curation_state import create_candidate_snapshot, record_curator_decision
from heva.workflow.package_validator import PackageValidationError, build_release


def _accepted(tmp_path: Path) -> str:
    document_id, _, _ = project(tmp_path)
    create_candidate_snapshot(tmp_path, document_id, submitted_by="Annotator")
    record_curator_decision(
        tmp_path,
        document_id,
        decision="accepted",
        actor="Curator",
        evidence="Reviewed the submitted candidate.",
    )
    return document_id


def test_data_owner_role_and_license_evidence_are_required(tmp_path: Path) -> None:
    """A curator cannot substitute for the accountable distribution owner."""

    document_id = _accepted(tmp_path)
    curator = add_person(tmp_path, PersonRecord(name="Curator", roles=["curator"]))

    with pytest.raises(DataOwnerApprovalError, match="data_owner"):
        approve_document_distribution(
            tmp_path,
            document_id,
            data_owner_id=curator.person_id,
            license_or_waiver="CC-BY-4.0",
            statement="Approved.",
        )


def test_approval_is_bound_to_one_exact_document_candidate(tmp_path: Path) -> None:
    """The released metadata identifies who accepted responsibility and for what evidence."""

    document_id = _accepted(tmp_path)
    owner = add_person(
        tmp_path,
        PersonRecord(name="Data Owner", roles=["data_owner"], affiliation="Museum"),
    )
    saved = approve_document_distribution(
        tmp_path,
        document_id,
        data_owner_id=owner.person_id,
        license_or_waiver="Institutional waiver 2026-04",
        statement="I approve distribution of the annotation data, excluding the PDF.",
    )

    restored, restored_owner = load_current_data_owner_approval(tmp_path, document_id)

    assert restored.candidate_id == saved.candidate_id
    assert restored_owner.name == "Data Owner"
    assert restored_owner.affiliation == "Museum"


def test_release_is_blocked_until_each_accepted_document_has_an_owner(tmp_path: Path) -> None:
    """Curator acceptance alone cannot authorize a distributable Data Package."""

    _accepted(tmp_path)

    with pytest.raises(PackageValidationError, match="lacks data-owner approval"):
        build_release(tmp_path)
