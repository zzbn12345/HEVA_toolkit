"""Auditable human review state for HEVA sentence annotations."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field

from src.heva_contract import validate_record
from src.project_registry import DEFAULT_REGISTRY_PATH, ProjectRegistry, RegistrySummary


ReviewStatus = Literal["pending", "approved", "needs_correction", "excluded"]


class ReviewError(ValueError):
    """Raised when a review decision cannot safely be persisted."""


class AuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: Literal["decision", "edit", "source_record_changed"]
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
    registry = ProjectRegistry.model_validate_json(
        (root / DEFAULT_REGISTRY_PATH).read_text(encoding="utf-8")
    )
    matches = [entry for entry in registry.documents if entry.document_id == document_id]
    if not matches:
        raise ReviewError(f"Document {document_id} is not registered.")
    return root / matches[0].package_path


def initialize_sentence_reviews(
    project_root: str | Path,
    document_id: str,
) -> Path:
    """Create pending states and retain decisions only for byte-equivalent records."""

    root = Path(project_root).resolve()
    package = _package(root, document_id)
    annotations = json.loads((package / "annotations.json").read_text(encoding="utf-8"))
    target = package / "review-state.json"
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
    target = _package(root, document_id) / "review-state.json"
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


def replace_sentence_record(
    project_root: str | Path,
    document_id: str,
    sentence_id: int,
    replacement: dict[str, Any],
    *,
    editor: str,
) -> None:
    """Validate and persist an edit with before/after evidence and read-back verification."""

    result = validate_record(replacement)
    if not result.valid or result.record is None:
        raise ReviewError("Edited sentence does not satisfy the HEVA record contract.")
    root = Path(project_root).resolve()
    package = _package(root, document_id)
    annotations_path = package / "annotations.json"
    records = json.loads(annotations_path.read_text(encoding="utf-8"))
    matches = [index for index, record in enumerate(records) if record["sentence_id"] == sentence_id]
    if len(matches) != 1:
        raise ReviewError(f"Expected exactly one sentence {sentence_id}.")
    index = matches[0]
    before = records[index]
    after = result.record.to_dict()
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
            details={"before": before, "after": after},
        )
    )
    _write_json(review_path, review.model_dump(mode="json"))


def submit_document_for_review(project_root: str | Path, document_id: str) -> None:
    """Move a document to in_review only after every sentence has a final decision."""

    root = Path(project_root).resolve()
    package = _package(root, document_id)
    review = DocumentReview.model_validate_json(
        (package / "review-state.json").read_text(encoding="utf-8")
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
