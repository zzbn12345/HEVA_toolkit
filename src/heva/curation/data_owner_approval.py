"""Per-document data-owner accountability for distributable HEVA packages."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from heva.curation.curation_state import CurationError, load_curation_state, verify_current_candidate
from heva.curation.people_registry import PersonRecord, load_people_registry
from heva.curation.project_registry import document_workspace_directory


APPROVAL_FILENAME = "data-owner-approval.json"


class DataOwnerApproval(BaseModel):
    """Approval of one exact curator-accepted candidate by its accountable owner."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    document_id: str
    candidate_id: str
    data_owner_id: str = Field(pattern=r"^PERSON-[A-Z0-9]+$")
    approved_at: datetime
    license_or_waiver: str = Field(min_length=1)
    statement: str = Field(min_length=1)


class DataOwnerApprovalError(ValueError):
    """Raised when accountability cannot be proven for the current document evidence."""


def _owner(project_root: str | Path, person_id: str) -> PersonRecord:
    registry = load_people_registry(project_root)
    person = next((item for item in registry.people if item.person_id == person_id), None)
    if person is None:
        raise DataOwnerApprovalError(f"Person {person_id} does not exist.")
    if "data_owner" not in person.roles:
        raise DataOwnerApprovalError("Only a person with the data_owner role can approve distribution.")
    return person


def approve_document_distribution(
    project_root: str | Path,
    document_id: str,
    *,
    data_owner_id: str,
    license_or_waiver: str,
    statement: str,
) -> DataOwnerApproval:
    """Approve distribution of the exact currently accepted document candidate."""

    root = Path(project_root).resolve()
    _owner(root, data_owner_id)
    try:
        candidate = verify_current_candidate(root, document_id)
        decision = load_curation_state(root, document_id).current_decision()
    except CurationError as error:
        raise DataOwnerApprovalError(str(error)) from error
    if decision is None or decision.candidate_id != candidate.candidate_id or decision.decision != "accepted":
        raise DataOwnerApprovalError("The data owner can approve only a curator-accepted candidate.")
    if not license_or_waiver.strip():
        raise DataOwnerApprovalError("Record the applicable license or waiver.")
    if not statement.strip():
        raise DataOwnerApprovalError("Record the data owner's approval statement.")
    approval = DataOwnerApproval(
        document_id=document_id,
        candidate_id=candidate.candidate_id,
        data_owner_id=data_owner_id,
        approved_at=datetime.now(timezone.utc),
        license_or_waiver=license_or_waiver.strip(),
        statement=statement.strip(),
    )
    path = document_workspace_directory(root, document_id) / APPROVAL_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(approval.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return approval


def load_current_data_owner_approval(
    project_root: str | Path,
    document_id: str,
) -> tuple[DataOwnerApproval, PersonRecord]:
    """Load approval and prove that it still targets the current accepted candidate."""

    root = Path(project_root).resolve()
    path = document_workspace_directory(root, document_id) / APPROVAL_FILENAME
    try:
        approval = DataOwnerApproval.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as error:
        raise DataOwnerApprovalError("This document has no valid data-owner approval.") from error
    if approval.document_id != document_id:
        raise DataOwnerApprovalError("Data-owner approval refers to another document.")
    try:
        candidate = verify_current_candidate(root, document_id)
    except CurationError as error:
        raise DataOwnerApprovalError(str(error)) from error
    if approval.candidate_id != candidate.candidate_id:
        raise DataOwnerApprovalError("Data-owner approval is stale because document evidence changed.")
    return approval, _owner(root, approval.data_owner_id)
