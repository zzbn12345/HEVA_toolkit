"""Persist validated HEVA extraction results in a registered document package."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Literal, Sequence

from pydantic import ValidationError

from src.color_mapping import ColorMappingError, load_confirmed_color_mapping
from src.document_metadata import PackageMetadata, ResourceMetadata
from src.heva_contract import ContractIssue, validate_record
from src.project_registry import DEFAULT_REGISTRY_PATH, ProjectRegistry, RegistrySummary


class ExtractionSessionError(ValueError):
    """Raised when extraction results cannot safely enter a document package."""


@dataclass(frozen=True)
class ExtractionValidationError(ExtractionSessionError):
    """All record issues found before package files are changed."""

    issues: tuple[ContractIssue, ...]

    def __str__(self) -> str:
        return f"Extraction contains {len(self.issues)} HEVA contract issue(s)."


@dataclass(frozen=True)
class SessionResult:
    document_id: str
    annotations_path: Path
    session_path: Path
    record_count: int


def _write_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _summary(registry: ProjectRegistry) -> RegistrySummary:
    documents = registry.documents
    return RegistrySummary(
        total=len(documents),
        backlog=sum(item.status == "backlog" for item in documents),
        in_progress=sum(item.status == "in_progress" for item in documents),
        in_review=sum(item.status == "in_review" for item in documents),
        done=sum(item.status == "done" for item in documents),
        changed=sum(item.source_state == "changed" for item in documents),
        missing=sum(item.source_state == "missing" for item in documents),
    )


def persist_extraction_results(
    project_root: str | Path,
    document_id: str,
    records: Sequence[dict[str, Any]],
    *,
    extraction_method: Literal["manual", "automatic", "hybrid"],
    extractor: str,
    extractor_version: str,
    registry_path: str | Path = DEFAULT_REGISTRY_PATH,
) -> SessionResult:
    """Validate all records, then atomically persist annotations and provenance."""

    root = Path(project_root).resolve()
    registry_file = root / Path(registry_path)
    try:
        registry = ProjectRegistry.model_validate_json(registry_file.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as error:
        raise ExtractionSessionError(f"Cannot load project registry: {error}") from error
    matches = [item for item in registry.documents if item.document_id == document_id]
    if not matches:
        raise ExtractionSessionError(f"Document {document_id} is not registered.")
    entry = matches[0]
    if entry.source_state != "present":
        raise ExtractionSessionError(
            f"Document {document_id} source state is {entry.source_state}; synchronize it first."
        )
    try:
        load_confirmed_color_mapping(root, document_id, registry_path=registry_path)
    except ColorMappingError as error:
        raise ExtractionSessionError(str(error)) from error

    results = [validate_record(record) for record in records]
    issues = tuple(issue for result in results for issue in result.issues)
    if issues:
        raise ExtractionValidationError(issues)
    canonical = [result.record.to_dict() for result in results if result.record is not None]

    if entry.metadata_path is None:
        raise ExtractionSessionError(f"Document {document_id} has no package metadata.")
    metadata_file = root / entry.metadata_path
    metadata = PackageMetadata.model_validate_json(metadata_file.read_text(encoding="utf-8"))
    package = root / entry.package_path
    annotations_file = package / "annotations.json"
    session_file = package / "extraction-session.json"
    now = datetime.now(timezone.utc)

    _write_json(annotations_file, canonical)
    metadata.annotation_process.method = extraction_method
    metadata.annotation_process.extractor = extractor
    metadata.annotation_process.extractor_version = extractor_version
    metadata.annotation_process.performed_at = now
    metadata.annotation_process.review.completed = False
    metadata.annotation_process.review.reviewed_at = None
    metadata.resources = [
        resource for resource in metadata.resources if resource.name != "annotations"
    ]
    metadata.resources.append(
        ResourceMetadata(
            name="annotations",
            path="annotations.json",
            format="json",
            record_count=len(canonical),
        )
    )
    _write_json(metadata_file, metadata.model_dump(mode="json"))
    _write_json(
        session_file,
        {
            "session_version": "1.0",
            "document_id": document_id,
            "status": "awaiting_review",
            "source_checksum_sha256": entry.checksum_sha256,
            "annotations_path": "annotations.json",
            "record_count": len(canonical),
            "completed_at": now.isoformat(),
        },
    )
    entry.status = "in_progress"
    registry.summary = _summary(registry)
    _write_json(registry_file, registry.model_dump(mode="json"))
    return SessionResult(document_id, annotations_file, session_file, len(canonical))
