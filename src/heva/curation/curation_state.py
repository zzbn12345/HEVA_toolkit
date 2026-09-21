"""Immutable submission snapshots and audited local curator decisions."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from heva.curation.package_validator import (
    DocumentValidation,
    PackageValidationError,
    approve_document,
    curation_blocking_issues,
    validate_document_package,
)
from heva.curation.project_registry import (
    DEFAULT_REGISTRY_PATH,
    ProjectRegistry,
    RegistrySummary,
    document_workspace_directory,
)


CURATION_VERSION = "1.0"
EVIDENCE_VERSION = "1.1"
CURATION_FILENAME = "curation-state.json"
SNAPSHOT_FILES = (
    "annotations.json",
    "metadata.json",
    "review-state.json",
)


class CandidateSnapshot(BaseModel):
    """Content-addressed evidence recorded when an annotator submits a package."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    evidence_version: Literal["1.0", "1.1"] = "1.0"
    created_at: datetime
    submitted_by: str
    source_checksum_sha256: str
    file_checksums_sha256: dict[str, str]
    validator_report: DocumentValidation


class CuratorDecision(BaseModel):
    """One curator action tied to an exact submitted candidate."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    decision: Literal["accepted", "changes_requested", "rejected", "quarantined"]
    actor: str
    decided_at: datetime
    evidence: str
    requested_changes: list[str] = Field(default_factory=list)


class CurationState(BaseModel):
    """Append-only candidate and decision history for one document package."""

    model_config = ConfigDict(extra="forbid")

    curation_version: str = CURATION_VERSION
    document_id: str
    candidates: list[CandidateSnapshot] = Field(default_factory=list)
    decisions: list[CuratorDecision] = Field(default_factory=list)

    def current_candidate(self) -> CandidateSnapshot | None:
        """Return the most recent submitted candidate, if one exists."""

        return self.candidates[-1] if self.candidates else None

    def current_decision(self) -> CuratorDecision | None:
        """Return the latest decision for the current candidate, if one exists."""

        candidate = self.current_candidate()
        if candidate is None:
            return None
        return next(
            (
                decision
                for decision in reversed(self.decisions)
                if decision.candidate_id == candidate.candidate_id
            ),
            None,
        )


class CurationError(ValueError):
    """Raised when candidate evidence or a curator transition is unsafe."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _file_checksum(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise CurationError(f"Cannot read candidate evidence {path.name}: {error}") from error


def _candidate_checksum(path: Path, filename: str, evidence_version: str) -> str:
    """Hash curation evidence while allowing citation completion after review."""

    if filename != "metadata.json" or evidence_version == "1.0":
        return _file_checksum(path)
    try:
        metadata = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CurationError(f"Cannot read candidate evidence {path.name}: {error}") from error
    metadata.pop("source", None)
    return hashlib.sha256(_canonical_bytes(metadata)).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _registry_entry(root: Path, document_id: str):
    try:
        registry = ProjectRegistry.model_validate_json(
            (root / DEFAULT_REGISTRY_PATH).read_text(encoding="utf-8")
        )
    except OSError as error:
        raise CurationError(f"Cannot load project registry: {error}") from error
    entry = next(
        (item for item in registry.documents if item.document_id == document_id),
        None,
    )
    if entry is None:
        raise CurationError(f"Document {document_id} is not registered.")
    return registry, entry


def load_curation_state(
    project_root: str | Path,
    document_id: str,
) -> CurationState:
    """Load local curation history, returning an empty history before submission."""

    root = Path(project_root).resolve()
    _, entry = _registry_entry(root, document_id)
    path = document_workspace_directory(root, document_id) / CURATION_FILENAME
    if not path.exists():
        return CurationState(document_id=document_id)
    try:
        return CurationState.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise CurationError(f"Cannot load curation state: {error}") from error


def create_candidate_snapshot(
    project_root: str | Path,
    document_id: str,
    *,
    submitted_by: str,
) -> CandidateSnapshot:
    """Persist a validated, content-addressed submission without copying source PDFs."""

    root = Path(project_root).resolve()
    _, entry = _registry_entry(root, document_id)
    report = validate_document_package(root, document_id)
    blockers = curation_blocking_issues(report)
    if blockers:
        codes = ", ".join(issue.code for issue in blockers)
        raise CurationError(f"Candidate failed HEVA curation checks: {codes}")
    package = root / entry.package_path
    checksums = {
        filename: _candidate_checksum(
            document_workspace_directory(root, document_id) / filename
            if filename == "review-state.json"
            else package / filename,
            filename,
            EVIDENCE_VERSION,
        )
        for filename in SNAPSHOT_FILES
    }
    identity = {
        "document_id": document_id,
        "source_checksum_sha256": entry.checksum_sha256,
        "evidence_version": EVIDENCE_VERSION,
        "file_checksums_sha256": checksums,
        "validator_report": report.model_dump(mode="json"),
    }
    snapshot = CandidateSnapshot(
        candidate_id=hashlib.sha256(_canonical_bytes(identity)).hexdigest(),
        evidence_version=EVIDENCE_VERSION,
        created_at=datetime.now(timezone.utc),
        submitted_by=submitted_by,
        source_checksum_sha256=entry.checksum_sha256,
        file_checksums_sha256=checksums,
        validator_report=report,
    )
    state = load_curation_state(root, document_id)
    if not state.candidates or state.candidates[-1].candidate_id != snapshot.candidate_id:
        state.candidates.append(snapshot)
    _write_json(
        document_workspace_directory(root, document_id) / CURATION_FILENAME,
        state.model_dump(mode="json"),
    )
    return snapshot


def verify_current_candidate(
    project_root: str | Path,
    document_id: str,
) -> CandidateSnapshot:
    """Reject curator action when submitted package evidence changed afterward."""

    root = Path(project_root).resolve()
    _, entry = _registry_entry(root, document_id)
    state = load_curation_state(root, document_id)
    candidate = state.current_candidate()
    if candidate is None:
        raise CurationError("This document has no submitted candidate snapshot.")
    package = root / entry.package_path
    current = {
        filename: _candidate_checksum(
            document_workspace_directory(root, document_id) / filename
            if filename == "review-state.json"
            else package / filename,
            filename,
            candidate.evidence_version,
        )
        for filename in SNAPSHOT_FILES
    }
    if current != candidate.file_checksums_sha256:
        raise CurationError(
            "Submitted evidence changed after snapshot creation. Reopen and resubmit it."
        )
    return candidate


def _move_to_in_progress(root: Path, document_id: str) -> None:
    registry, entry = _registry_entry(root, document_id)
    entry.status = "in_progress"
    registry.summary = RegistrySummary(
        total=len(registry.documents),
        backlog=sum(item.status == "backlog" for item in registry.documents),
        in_progress=sum(item.status == "in_progress" for item in registry.documents),
        in_review=sum(item.status == "in_review" for item in registry.documents),
        done=sum(item.status == "done" for item in registry.documents),
        changed=sum(item.source_state == "changed" for item in registry.documents),
        missing=sum(item.source_state == "missing" for item in registry.documents),
    )
    _write_json(
        root / DEFAULT_REGISTRY_PATH,
        registry.model_dump(mode="json"),
    )


def record_curator_decision(
    project_root: str | Path,
    document_id: str,
    *,
    decision: Literal["accepted", "changes_requested", "rejected", "quarantined"],
    actor: str,
    evidence: str,
    requested_changes: list[str] | None = None,
) -> CuratorDecision:
    """Audit a curator decision and apply its permitted workflow transition."""

    actor = actor.strip()
    evidence = evidence.strip()
    changes = [item.strip() for item in requested_changes or [] if item.strip()]
    if not actor:
        raise CurationError("Curator name is required.")
    if not evidence:
        raise CurationError("Decision evidence or rationale is required.")
    if decision == "changes_requested" and not changes:
        raise CurationError("List at least one requested change.")

    root = Path(project_root).resolve()
    registry, entry = _registry_entry(root, document_id)
    if entry.status != "in_review":
        raise CurationError("Only a submitted document can receive a curator decision.")
    candidate = verify_current_candidate(root, document_id)
    state = load_curation_state(root, document_id)
    if state.current_decision() is not None:
        raise CurationError("The current candidate already has a curator decision.")

    if decision == "accepted":
        try:
            approve_document(root, document_id)
        except PackageValidationError as error:
            raise CurationError(str(error)) from error
    elif decision == "changes_requested":
        _move_to_in_progress(root, document_id)

    result = CuratorDecision(
        candidate_id=candidate.candidate_id,
        decision=decision,
        actor=actor,
        decided_at=datetime.now(timezone.utc),
        evidence=evidence,
        requested_changes=changes,
    )
    state.decisions.append(result)
    _, current_entry = _registry_entry(root, document_id)
    _write_json(
        document_workspace_directory(root, document_id) / CURATION_FILENAME,
        state.model_dump(mode="json"),
    )
    return result
