"""Document-scoped review queue assembled from canonical HEVA project state."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from heva.workflow.document_metadata import PackageMetadata, save_package_metadata
from heva.workflow.extraction_draft import ExtractionDraftError, load_extraction_draft
from heva.workflow.project_registry import (
    DEFAULT_REGISTRY_PATH,
    ProjectRegistry,
    RegistryError,
    document_workspace_directory,
    resolve_document_source,
)
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
    annotation_complete: bool
    readiness_gates: dict[str, bool]
    blocking_reasons: list[str]
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


def _readiness(
    package: Path,
    records: list[dict[str, Any]],
    review: DocumentReview | None,
) -> tuple[dict[str, bool], list[str]]:
    """Project four researcher-facing gates from persisted package evidence."""

    reasons: list[str] = []
    try:
        metadata = PackageMetadata.model_validate_json(
            (package / "metadata.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        metadata = None

    source = metadata.source if metadata else None
    citation_ready = bool(
        source
        and source.human_confirmed
        and source.title
        and source.creators
        and source.citation
        and (source.reference or source.not_findable_reason)
    )

    colors = metadata.color_configuration if metadata else None
    color_ready = bool(
        colors
        and colors.human_confirmed
        and colors.colors
        and all(item.status in {"approved", "ignored"} for item in colors.colors)
    )
    if not color_ready:
        reasons.append("Review and confirm the document color configuration.")

    annotations_resource = (
        next(
            (
                resource
                for resource in metadata.resources
                if resource.name == "annotations"
            ),
            None,
        )
        if metadata
        else None
    )
    extraction_ready = bool(
        records
        and annotations_resource
        and annotations_resource.record_count == len(records)
    )
    if not extraction_ready:
        reasons.append("Run extraction and persist a non-empty sentence inventory.")

    states = [item.status for item in review.sentences] if review else []
    sentence_review_ready = bool(
        records
        and review
        and len(states) == len(records)
        and all(state in {"approved", "excluded"} for state in states)
    )
    if not sentence_review_ready:
        reasons.append("Approve or exclude every extracted sentence.")

    return (
        {
            "citation": citation_ready,
            "color_configuration": color_ready,
            "extraction": extraction_ready,
            "sentence_review": sentence_review_ready,
        },
        reasons,
    )


def list_review_queue(project_root: str | Path) -> list[ReviewQueueItem]:
    """Return stable document summaries without combining their review decisions."""

    root = Path(project_root).resolve()
    items: list[ReviewQueueItem] = []
    for entry in sorted(_registry(root).documents, key=lambda item: item.source_path):
        package = root / entry.package_path
        annotations_path = package / "annotations.json"
        review_path = document_workspace_directory(root, entry.document_id) / "review-state.json"
        if annotations_path.exists() and not review_path.exists():
            from heva.workflow.review_state import initialize_sentence_reviews

            initialize_sentence_reviews(root, entry.document_id)
        if not annotations_path.exists() or not review_path.exists():
            records = _load_records(package) if annotations_path.exists() else []
            gates, reasons = _readiness(package, records, None)
            items.append(
                ReviewQueueItem(
                    document_id=entry.document_id,
                    source_path=entry.source_path,
                    status=entry.status,
                    source_state=entry.source_state,
                    review_available=False,
                    completion_percent=0,
                    annotation_complete=False,
                    readiness_gates=gates,
                    blocking_reasons=reasons,
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
        gates, reasons = _readiness(package, records, review)
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
                annotation_complete=all(
                    gates[name]
                    for name in (
                        "color_configuration",
                        "extraction",
                        "sentence_review",
                    )
                ),
                readiness_gates=gates,
                blocking_reasons=reasons,
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
    draft_only = False
    try:
        records = _load_records(package)
    except ReviewQueueError:
        records = []
    if not records:
        try:
            draft = load_extraction_draft(root, document_id)
        except ExtractionDraftError as error:
            raise ReviewQueueError(
                "No canonical annotations or unresolved extraction draft are available."
            ) from error
        draft_only = True
        records = [
            {
                "sentence_id": sentence.sentence_id,
                "page": sentence.page,
                "sentence": sentence.sentence,
                "tokens": sentence.tokens,
                "values": [],
                "entities": [
                    {
                        "start": entity.start,
                        "end": entity.end,
                        "text": entity.text,
                        "label": "unresolved",
                        "color": entity.color,
                    }
                    for entity in sentence.entities
                ],
                "ner_tags": sentence.ner_tags,
            }
            for sentence in draft.sentences
        ]
    review_path = document_workspace_directory(root, document_id) / "review-state.json"
    if not draft_only and not review_path.exists():
        from heva.workflow.review_state import initialize_sentence_reviews

        initialize_sentence_reviews(root, document_id)
    if draft_only:
        decisions = {}
    else:
        try:
            review = DocumentReview.model_validate_json(
                review_path.read_text(encoding="utf-8")
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
        if decision is None and not draft_only:
            raise ReviewQueueError(
                f"Sentence {sentence_id} has no matching persisted review state."
            )
        review_value = (
            decision.model_dump(mode="json")
            if decision is not None
            else {
                "sentence_id": sentence_id,
                "record_sha256": "unresolved-draft",
                "status": "pending",
                "reviewer": None,
                "decided_at": None,
                "comment": None,
                "audit": [],
            }
        )
        sentences.append(
            {
                "record": record,
                "review": review_value,
                "flags": ([
                    {
                        "code": "unresolved_color_mapping",
                        "severity": "warning",
                        "message": "Choose a color configuration before reviewing this annotation.",
                        "evidence": None,
                    }
                ] if draft_only else [
                    {
                        "code": flag.code,
                        "severity": flag.severity,
                        "message": flag.message,
                        "evidence": flag.evidence,
                    }
                    for flag in assess_record(record)
                ]),
            }
        )
    all_items = list_review_queue(root)
    selected_summary = next(
        item for item in all_items if item.document_id == document_id
    )
    queue = [item for item in all_items if item.review_available]
    identifiers = [item.document_id for item in queue]
    position = identifiers.index(document_id) if document_id in identifiers else -1
    readiness_gates = selected_summary.readiness_gates
    blocking_reasons = selected_summary.blocking_reasons
    if draft_only:
        readiness_gates = {
            **readiness_gates,
            "color_configuration": False,
            "extraction": False,
            "sentence_review": False,
        }
        blocking_reasons = [
            "Review and confirm the document color configuration.",
            "Convert the unresolved color draft into canonical HEVA annotations.",
            "Approve or exclude every extracted sentence.",
        ]
    return {
        "document_id": document_id,
        "source_path": entry.source_path,
        "status": entry.status,
        "source_state": entry.source_state,
        "annotation_complete": selected_summary.annotation_complete and not draft_only,
        "completion_percent": selected_summary.completion_percent,
        "readiness_gates": readiness_gates,
        "blocking_reasons": blocking_reasons,
        "draft_only": draft_only,
        "previous_document_id": identifiers[position - 1] if position > 0 else None,
        "next_document_id": (
            identifiers[position + 1]
            if position >= 0 and position + 1 < len(identifiers)
            else None
        ),
        "sentences": sentences,
    }


def submit_review_document(
    project_root: str | Path,
    document_id: str,
    *,
    submitted_by: str,
) -> dict[str, Any]:
    """Submit completed annotation curation while leaving citation as a release gate."""

    root = Path(project_root).resolve()
    summary = next(
        (item for item in list_review_queue(root) if item.document_id == document_id),
        None,
    )
    if summary is None:
        raise ReviewQueueError(f"Document {document_id} is not registered.")
    if summary.status in {"in_review", "done"}:
        raise ReviewQueueError("This document has already been submitted for review.")
    if not summary.annotation_complete:
        reasons = " ".join(summary.blocking_reasons)
        raise ReviewQueueError(
            f"This document is not ready for submission. {reasons}".strip()
        )
    package = _package_for_document(root, document_id)
    try:
        metadata = PackageMetadata.model_validate_json(
            (package / "metadata.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as error:
        raise ReviewQueueError(f"Cannot update annotation-process metadata: {error}") from error
    metadata.annotation_process.review.completed = True
    metadata.annotation_process.review.reviewed_at = datetime.now(timezone.utc)
    save_package_metadata(root, metadata)

    from heva.workflow.curation_state import create_candidate_snapshot
    from heva.workflow.review_state import submit_document_for_review

    snapshot = create_candidate_snapshot(
        root,
        document_id,
        submitted_by=submitted_by,
    )
    submit_document_for_review(root, document_id)
    result = load_review_document(root, document_id)
    result["candidate"] = snapshot.model_dump(mode="json")
    return result


def _package_for_document(root: Path, document_id: str) -> Path:
    entry = next(
        (item for item in _registry(root).documents if item.document_id == document_id),
        None,
    )
    if entry is None:
        raise ReviewQueueError(f"Document {document_id} is not registered.")
    return root / entry.package_path


def registered_source_path(project_root: str | Path, document_id: str) -> Path:
    """Resolve only the project or machine-local source bound to a registered ID."""

    root = Path(project_root).resolve()
    entry = next(
        (item for item in _registry(root).documents if item.document_id == document_id),
        None,
    )
    if entry is None:
        raise ReviewQueueError(f"Document {document_id} is not registered.")
    try:
        source = resolve_document_source(root, entry)
    except RegistryError as error:
        raise ReviewQueueError(str(error)) from error
    if not source.is_file():
        raise ReviewQueueError("The registered source file is missing.")
    return source
