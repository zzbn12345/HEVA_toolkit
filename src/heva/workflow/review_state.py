"""Auditable human review state for HEVA sentence annotations."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field

from heva.workflow.contract import validate_record
from heva.workflow.project_registry import (
    DEFAULT_REGISTRY_PATH,
    ProjectRegistry,
    RegistrySummary,
    document_workspace_directory,
    load_project_registry,
)


ReviewStatus = Literal["pending", "approved", "needs_correction", "excluded"]


class ReviewError(ValueError):
    """Raised when a review decision cannot safely be persisted."""


class AuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: Literal["decision", "edit", "source_record_changed", "warning_accepted"]
    actor: str
    occurred_at: datetime
    details: dict[str, Any] = Field(default_factory=dict)


class SentenceReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sentence_id: int
    record_sha256: str
    status: ReviewStatus = "pending"
    reviewer: str | None = None
    decided_at: datetime | None = None
    comment: str | None = None
    audit: list[AuditEvent] = Field(default_factory=list)
    accepted_warning_codes: list[str] = Field(default_factory=list)


class DocumentReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_version: str = "1.0"
    document_id: str
    sentences: list[SentenceReview]


def _digest(record: dict[str, Any]) -> str:
    encoded = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _package(root: Path, document_id: str) -> Path:
    registry = load_project_registry(root)
    matches = [entry for entry in registry.documents if entry.document_id == document_id]
    if not matches:
        raise ReviewError(f"Document {document_id} is not registered.")
    return root / matches[0].package_path


def _require_editable(root: Path, document_id: str) -> None:
    """Require a registered document; legacy submission states no longer lock editing."""

    registry = load_project_registry(root)
    entry = next(
        (item for item in registry.documents if item.document_id == document_id),
        None,
    )
    if entry is None:
        raise ReviewError(f"Document {document_id} is not registered.")


def initialize_sentence_reviews(
    project_root: str | Path,
    document_id: str,
) -> Path:
    """Create pending states and retain decisions only for byte-equivalent records."""

    root = Path(project_root).resolve()
    package = _package(root, document_id)
    annotations = json.loads((package / "annotations.json").read_text(encoding="utf-8"))
    target = document_workspace_directory(root, document_id) / "review-state.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[int, SentenceReview] = {}
    if target.exists():
        previous = DocumentReview.model_validate_json(target.read_text(encoding="utf-8"))
        existing = {item.sentence_id: item for item in previous.sentences}
    sentences: list[SentenceReview] = []
    now = datetime.now(timezone.utc)
    for record in annotations:
        sentence_id = record["sentence_id"]
        digest = _digest(record)
        prior = existing.get(sentence_id)
        if prior is not None and prior.record_sha256 == digest:
            sentences.append(prior)
        else:
            review = SentenceReview(sentence_id=sentence_id, record_sha256=digest)
            if prior is not None:
                review.audit.append(
                    AuditEvent(
                        event="source_record_changed",
                        actor="system",
                        occurred_at=now,
                        details={"previous_sha256": prior.record_sha256},
                    )
                )
            sentences.append(review)
    review = DocumentReview(
        document_id=document_id,
        sentences=sorted(sentences, key=lambda item: item.sentence_id),
    )
    _write_json(target, review.model_dump(mode="json"))
    return target


def record_decisions(
    project_root: str | Path,
    document_id: str,
    sentence_ids: Sequence[int],
    *,
    status: ReviewStatus,
    reviewer: str,
    comment: str | None = None,
) -> Path:
    """Persist one explicit audit event for every selected sentence."""

    if status == "pending":
        raise ReviewError("A human decision cannot set a sentence back to pending.")
    if not reviewer.strip():
        raise ReviewError("Reviewer identity is required.")
    root = Path(project_root).resolve()
    _require_editable(root, document_id)
    target = document_workspace_directory(root, document_id) / "review-state.json"
    review = DocumentReview.model_validate_json(target.read_text(encoding="utf-8"))
    selected = set(sentence_ids)
    known = {item.sentence_id for item in review.sentences}
    if selected - known:
        raise ReviewError(f"Unknown sentence IDs: {sorted(selected - known)}")
    now = datetime.now(timezone.utc)
    for item in review.sentences:
        if item.sentence_id not in selected:
            continue
        previous = item.status
        item.status = status
        item.reviewer = reviewer.strip()
        item.decided_at = now
        item.comment = comment
        item.audit.append(
            AuditEvent(
                event="decision",
                actor=reviewer.strip(),
                occurred_at=now,
                details={"from": previous, "to": status, "comment": comment},
            )
        )
    _write_json(target, review.model_dump(mode="json"))
    return target


def accept_quality_warning(
    project_root: str | Path,
    document_id: str,
    sentence_id: int,
    code: str,
    *,
    reviewer: str,
    comment: str | None = None,
) -> Path:
    """Accept one current non-blocking warning while retaining auditable evidence."""

    if not reviewer.strip():
        raise ReviewError("Reviewer identity is required.")
    root = Path(project_root).resolve()
    _require_editable(root, document_id)
    package = _package(root, document_id)
    records = json.loads((package / "annotations.json").read_text(encoding="utf-8"))
    record = next(
        (item for item in records if item.get("sentence_id") == sentence_id),
        None,
    )
    if record is None:
        raise ReviewError(f"Unknown sentence ID: {sentence_id}")
    from heva.workflow.quality_flags import assess_record

    warning = next(
        (flag for flag in assess_record(record) if flag.code == code),
        None,
    )
    if warning is None:
        raise ReviewError(f"Warning {code!r} is not active for sentence {sentence_id}.")
    if warning.severity != "warning":
        raise ReviewError("Errors must be corrected and cannot be accepted as warnings.")
    target = document_workspace_directory(root, document_id) / "review-state.json"
    review = DocumentReview.model_validate_json(target.read_text(encoding="utf-8"))
    item = next(
        (candidate for candidate in review.sentences if candidate.sentence_id == sentence_id),
        None,
    )
    if item is None:
        raise ReviewError(f"Unknown sentence ID: {sentence_id}")
    if code not in item.accepted_warning_codes:
        item.accepted_warning_codes.append(code)
        item.accepted_warning_codes.sort()
        item.audit.append(
            AuditEvent(
                event="warning_accepted",
                actor=reviewer.strip(),
                occurred_at=datetime.now(timezone.utc),
                details={
                    "code": code,
                    "message": warning.message,
                    "evidence": warning.evidence,
                    "comment": comment,
                },
            )
        )
        _write_json(target, review.model_dump(mode="json"))
    return target


def replace_sentence_record(
    project_root: str | Path,
    document_id: str,
    sentence_id: int,
    replacement: dict[str, Any],
    *,
    editor: str,
    excluded_entity_indices: Sequence[int] = (),
) -> None:
    """Persist curated text and annotation corrections while retaining source evidence."""

    result = validate_record(replacement)
    if not result.valid or result.record is None:
        details = "; ".join(
            f"{issue.path}: {issue.message}" for issue in result.issues
        )
        raise ReviewError(
            "Edited sentence does not satisfy the HEVA record contract"
            + (f": {details}" if details else ".")
        )
    root = Path(project_root).resolve()
    _require_editable(root, document_id)
    package = _package(root, document_id)
    annotations_path = package / "annotations.json"
    records = json.loads(annotations_path.read_text(encoding="utf-8"))
    matches = [index for index, record in enumerate(records) if record["sentence_id"] == sentence_id]
    if len(matches) != 1:
        raise ReviewError(f"Expected exactly one sentence {sentence_id}.")
    index = matches[0]
    before = records[index]
    after = result.record.to_dict()
    immutable_fields = (
        "sentence_id", "page", "sentence", "schema_version",
        "mapping_provenance",
    )
    changed_immutable = [
        field for field in immutable_fields if before.get(field) != after.get(field)
    ]
    if changed_immutable:
        raise ReviewError(
            "Source sentence evidence cannot be edited during annotation curation: "
            + ", ".join(changed_immutable)
            + ". Use curated_sentence for transcription or OCR corrections."
        )
    if before.get("curated_sentence") == after.get("curated_sentence"):
        if before.get("tokens") != after.get("tokens"):
            raise ReviewError(
                "Tokens can change only when the curated sentence changes."
            )
    before_entities = before.get("entities", [])
    after_entities = after.get("entities", [])
    if not isinstance(excluded_entity_indices, (list, tuple)) or not all(
        isinstance(index, int) and not isinstance(index, bool)
        for index in excluded_entity_indices
    ):
        raise ReviewError("Excluded annotation indices must be integers.")
    excluded_indices = sorted(set(excluded_entity_indices))
    if any(index < 0 or index >= len(before_entities) for index in excluded_indices):
        raise ReviewError("An excluded annotation index is out of range.")
    if len(after_entities) > len(before_entities):
        raise ReviewError(
            "This editor cannot create new annotations yet."
        )
    if len(after_entities) != len(before_entities) - len(excluded_indices):
        raise ReviewError(
            "Every removed annotation must be identified explicitly for the review audit."
        )
    retained_before = [
        entity
        for index, entity in enumerate(before_entities)
        if index not in excluded_indices
    ]
    before_evidence = Counter(
        (entity.get("label"), entity.get("color")) for entity in retained_before
    )
    after_evidence = Counter(
        (entity.get("label"), entity.get("color")) for entity in after_entities
    )
    if after_evidence - before_evidence:
        raise ReviewError(
            "Annotation label and color are read-only. Change document Color config instead."
        )
    excluded_entities = [before_entities[index] for index in excluded_indices]
    records[index] = after
    _write_json(annotations_path, records)
    if json.loads(annotations_path.read_text(encoding="utf-8"))[index] != after:
        raise ReviewError("Persisted sentence edit could not be read back unchanged.")
    review_path = initialize_sentence_reviews(root, document_id)
    review = DocumentReview.model_validate_json(review_path.read_text(encoding="utf-8"))
    item = next(item for item in review.sentences if item.sentence_id == sentence_id)
    now = datetime.now(timezone.utc)
    item.status = "needs_correction"
    item.audit.append(
        AuditEvent(
            event="edit",
            actor=editor,
            occurred_at=now,
            details={
                "before": before,
                "after": after,
                "excluded_entities": excluded_entities,
            },
        )
    )
    _write_json(review_path, review.model_dump(mode="json"))


def submit_document_for_review(project_root: str | Path, document_id: str) -> None:
    """Move a document to in_review only after every sentence has a final decision."""

    root = Path(project_root).resolve()
    package = _package(root, document_id)
    review = DocumentReview.model_validate_json(
        (document_workspace_directory(root, document_id) / "review-state.json").read_text(
            encoding="utf-8"
        )
    )
    unresolved = [
        item.sentence_id
        for item in review.sentences
        if item.status in {"pending", "needs_correction"}
    ]
    if unresolved:
        raise ReviewError(f"Sentences still require decisions: {unresolved}")
    registry_path = root / DEFAULT_REGISTRY_PATH
    registry = ProjectRegistry.model_validate_json(registry_path.read_text(encoding="utf-8"))
    entry = next(item for item in registry.documents if item.document_id == document_id)
    entry.status = "in_review"
    documents = registry.documents
    registry.summary = RegistrySummary(
        total=len(documents),
        backlog=sum(item.status == "backlog" for item in documents),
        in_progress=sum(item.status == "in_progress" for item in documents),
        in_review=sum(item.status == "in_review" for item in documents),
        done=sum(item.status == "done" for item in documents),
        changed=sum(item.source_state == "changed" for item in documents),
        missing=sum(item.source_state == "missing" for item in documents),
    )
    _write_json(registry_path, registry.model_dump(mode="json"))


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage HEVA sentence review decisions.")
    parser.add_argument("project_root", nargs="?", default=".")
    commands = parser.add_subparsers(dest="command", required=True)
    initialize = commands.add_parser("initialize")
    initialize.add_argument("--document-id", required=True)
    decide = commands.add_parser("decide")
    decide.add_argument("--document-id", required=True)
    decide.add_argument("--sentence-id", type=int, action="append", required=True)
    decide.add_argument(
        "--status",
        choices=["approved", "needs_correction", "excluded"],
        required=True,
    )
    decide.add_argument("--reviewer", required=True)
    decide.add_argument("--comment")
    submit = commands.add_parser("submit")
    submit.add_argument("--document-id", required=True)
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "initialize":
            target = initialize_sentence_reviews(args.project_root, args.document_id)
            print(f"HEVA review state written to {target}")
        elif args.command == "decide":
            target = record_decisions(
                args.project_root,
                args.document_id,
                args.sentence_id,
                status=args.status,
                reviewer=args.reviewer,
                comment=args.comment,
            )
            print(f"HEVA review decisions written to {target}")
        else:
            submit_document_for_review(args.project_root, args.document_id)
            print(f"{args.document_id} moved to in_review")
    except (ReviewError, OSError, ValueError) as error:
        print(f"REVIEW ERROR: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
