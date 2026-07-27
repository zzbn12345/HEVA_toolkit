"""Document-scoped review queue assembled from canonical HEVA project state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from heva.workflow.project_registry import DEFAULT_REGISTRY_PATH, ProjectRegistry
from heva.workflow.quality_flags import assess_record
from heva.workflow.review_state import DocumentReview


class ReviewQueueError(ValueError):
    """Raised when a registered document cannot be presented safely for review."""


class ReviewCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int
    pending: int
    approved: int
    needs_correction: int
    excluded: int
    flagged: int


class ReviewQueueItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    source_path: str
    status: str
    source_state: str
    review_available: bool
    completion_percent: int
    counts: ReviewCounts


def _registry(root: Path) -> ProjectRegistry:
    try:
        return ProjectRegistry.model_validate_json(
            (root / DEFAULT_REGISTRY_PATH).read_text(encoding="utf-8")
        )
    except OSError as error:
        raise ReviewQueueError(f"Cannot load the project registry: {error}") from error


def _load_records(package: Path) -> list[dict[str, Any]]:
    try:
        decoded = json.loads((package / "annotations.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReviewQueueError(f"Cannot load canonical annotations: {error}") from error
    if not isinstance(decoded, list):
        raise ReviewQueueError("Canonical annotations must be a JSON array.")
    return decoded


def list_review_queue(project_root: str | Path) -> list[ReviewQueueItem]:
    """Return stable document summaries without combining their review decisions."""

    root = Path(project_root).resolve()
    items: list[ReviewQueueItem] = []
    for entry in sorted(_registry(root).documents, key=lambda item: item.source_path):
        package = root / entry.package_path
        annotations_path = package / "annotations.json"
        review_path = package / "review-state.json"
        if not annotations_path.exists() or not review_path.exists():
            items.append(
                ReviewQueueItem(
                    document_id=entry.document_id,
                    source_path=entry.source_path,
                    status=entry.status,
                    source_state=entry.source_state,
                    review_available=False,
                    completion_percent=0,
                    counts=ReviewCounts(
                        total=0,
                        pending=0,
                        approved=0,
                        needs_correction=0,
                        excluded=0,
                        flagged=0,
                    ),
                )
            )
            continue
        records = _load_records(package)
        review = DocumentReview.model_validate_json(review_path.read_text(encoding="utf-8"))
        states = {item.sentence_id: item.status for item in review.sentences}
        flagged = sum(bool(assess_record(record)) for record in records)
        completed = sum(
            state in {"approved", "excluded"} for state in states.values()
        )
        completion_percent = (
            round(100 * completed / len(records)) if records else 0
        )
        items.append(
            ReviewQueueItem(
                document_id=entry.document_id,
                source_path=entry.source_path,
                status=entry.status,
                source_state=entry.source_state,
                review_available=True,
                completion_percent=completion_percent,
                counts=ReviewCounts(
                    total=len(records),
                    pending=sum(state == "pending" for state in states.values()),
                    approved=sum(state == "approved" for state in states.values()),
                    needs_correction=sum(
                        state == "needs_correction" for state in states.values()
                    ),
                    excluded=sum(state == "excluded" for state in states.values()),
                    flagged=flagged,
                ),
            )
        )
    return items


def load_review_document(project_root: str | Path, document_id: str) -> dict[str, Any]:
    """Load one document's records, decisions, and flags for human inspection."""

    root = Path(project_root).resolve()
    registry = _registry(root)
    entry = next(
        (item for item in registry.documents if item.document_id == document_id),
        None,
    )
    if entry is None:
        raise ReviewQueueError(f"Document {document_id} is not registered.")
    package = root / entry.package_path
    records = _load_records(package)
    try:
        review = DocumentReview.model_validate_json(
            (package / "review-state.json").read_text(encoding="utf-8")
        )
    except OSError as error:
        raise ReviewQueueError(
            "Review state is not available. Run extraction or initialize sentence review first."
        ) from error
    decisions = {item.sentence_id: item for item in review.sentences}
    sentences = []
    for record in sorted(records, key=lambda item: (item["page"], item["sentence_id"])):
        sentence_id = record["sentence_id"]
        decision = decisions.get(sentence_id)
        if decision is None:
            raise ReviewQueueError(
                f"Sentence {sentence_id} has no matching persisted review state."
            )
        sentences.append(
            {
                "record": record,
                "review": decision.model_dump(mode="json"),
                "flags": [
                    {
                        "code": flag.code,
                        "severity": flag.severity,
                        "message": flag.message,
                        "evidence": flag.evidence,
                    }
                    for flag in assess_record(record)
                ],
            }
        )
    queue = [item for item in list_review_queue(root) if item.review_available]
    identifiers = [item.document_id for item in queue]
    position = identifiers.index(document_id)
    return {
        "document_id": document_id,
        "source_path": entry.source_path,
        "status": entry.status,
        "source_state": entry.source_state,
        "previous_document_id": identifiers[position - 1] if position > 0 else None,
        "next_document_id": (
            identifiers[position + 1] if position + 1 < len(identifiers) else None
        ),
        "sentences": sentences,
    }


def registered_source_path(project_root: str | Path, document_id: str) -> Path:
    """Resolve only the exact source path recorded for one document."""

    root = Path(project_root).resolve()
    entry = next(
        (item for item in _registry(root).documents if item.document_id == document_id),
        None,
    )
    if entry is None:
        raise ReviewQueueError(f"Document {document_id} is not registered.")
    source = (root / entry.source_path).resolve()
    try:
        source.relative_to(root)
    except ValueError as error:
        raise ReviewQueueError("Registered source path leaves the project directory.") from error
    if not source.is_file():
        raise ReviewQueueError("The registered source file is missing.")
    return source
