"""Persist validated HEVA extraction results in a registered document package."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Iterable, Literal, Mapping, Sequence

from pydantic import ValidationError

from heva.curation.color_mapping import (
    authorize_pending_mapping_for_extraction,
    ColorMappingError,
    load_confirmed_color_mapping,
    load_extraction_color_mapping,
    save_color_configuration,
)
from heva.curation.document_metadata import (
    ColorConfigurationMetadata,
    PackageMetadata,
    ResourceMetadata,
)
from heva.curation.contract import ContractIssue, validate_record
from heva.curation.project_registry import (
    DEFAULT_REGISTRY_PATH,
    ProjectRegistry,
    RegistrySummary,
    document_workspace_directory,
    require_current_document_source,
)


TOOLKIT_VERSION = "0.1.0"


class ExtractionSessionError(ValueError):
    """Raised when extraction results cannot safely enter a document package."""


class EmptyExtractionError(ExtractionSessionError):
    """Raised when extraction finds no annotation records."""

    code = "no_annotations_found"


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
    reused_checkpoint: bool = False
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExtractionCheckpointStatus:
    document_id: str
    state: Literal["not_extracted", "current", "stale", "invalid"]
    record_count: int = 0
    completed_at: str | None = None
    mapping_status: str | None = None
    warnings: tuple[str, ...] = ()
    stale_reasons: tuple[str, ...] = ()


def _mapping_checksum(mapping_status: str, values: Mapping[str, str]) -> str:
    encoded = json.dumps(
        {
            "mapping_status": mapping_status,
            "values": sorted(values.items()),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class BatchDocumentResult:
    document_id: str
    status: Literal["completed", "reused", "failed"]
    record_count: int = 0
    error: str | None = None
    error_code: str | None = None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class BatchExtractionReport:
    documents: tuple[BatchDocumentResult, ...]

    @property
    def successful(self) -> bool:
        return all(document.status != "failed" for document in self.documents)

    def to_dict(self) -> dict[str, Any]:
        return {
            "successful": self.successful,
            "documents": [
                {
                    "document_id": document.document_id,
                    "status": document.status,
                    "record_count": document.record_count,
                    "error": document.error,
                    "error_code": document.error_code,
                    "warnings": list(document.warnings),
                }
                for document in self.documents
            ],
        }


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
    mapping_status: Literal["approved", "pending_review"] = "approved",
    selected_pages: Sequence[int] | None = None,
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
        if mapping_status == "approved":
            mapping_values = load_confirmed_color_mapping(
                root,
                document_id,
                registry_path=registry_path,
            )
        else:
            selected = load_extraction_color_mapping(
                root, document_id, registry_path=registry_path
            )
            if selected.status != "pending_review":
                raise ColorMappingError("Expected an authorized pending color mapping.")
            mapping_values = selected.values
    except ColorMappingError as error:
        raise ExtractionSessionError(str(error)) from error

    if not records:
        raise EmptyExtractionError(
            "No annotation records were extracted. Check that the document contains "
            "colored annotations covered by its confirmed color configuration."
        )
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
    session_file = document_workspace_directory(root, document_id) / "extraction-session.json"
    session_file.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)

    _write_json(annotations_file, canonical)
    from heva.curation.review_state import initialize_sentence_reviews

    initialize_sentence_reviews(root, document_id)
    metadata.annotation_process.method = extraction_method
    metadata.annotation_process.extractor = extractor
    metadata.annotation_process.extractor_version = extractor_version
    metadata.annotation_process.performed_at = now
    metadata.annotation_process.source_scope = (
        "selected_pages" if selected_pages is not None else "full_source"
    )
    metadata.annotation_process.selected_pages = (
        sorted(selected_pages) if selected_pages is not None else []
    )
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
            "session_version": "1.1",
            "document_id": document_id,
            "status": (
                "mapping_review_pending"
                if mapping_status == "pending_review"
                else "awaiting_review"
            ),
            "mapping_status": mapping_status,
            "mapping_checksum_sha256": _mapping_checksum(
                mapping_status,
                mapping_values,
            ),
            "source_checksum_sha256": entry.checksum_sha256,
            "annotations_path": "annotations.json",
            "record_count": len(canonical),
            "source_scope": metadata.annotation_process.source_scope,
            "selected_pages": metadata.annotation_process.selected_pages,
            "completed_at": now.isoformat(),
        },
    )
    entry.status = "in_progress"
    registry.summary = _summary(registry)
    _write_json(registry_file, registry.model_dump(mode="json"))
    warnings = (
        ("Extraction used a pending color map and is not curator-ready.",)
        if mapping_status == "pending_review"
        else ()
    )
    return SessionResult(
        document_id,
        annotations_file,
        session_file,
        len(canonical),
        warnings=warnings,
    )


def load_extraction_checkpoint_status(
    project_root: str | Path,
    document_id: str,
) -> ExtractionCheckpointStatus:
    """Describe persisted extraction state without modifying or rebuilding it."""

    root = Path(project_root).resolve()
    try:
        registry = ProjectRegistry.model_validate_json(
            (root / DEFAULT_REGISTRY_PATH).read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as error:
        raise ExtractionSessionError(
            f"Cannot load project registry: {error}"
        ) from error
    entry = next(
        (item for item in registry.documents if item.document_id == document_id),
        None,
    )
    if entry is None:
        raise ExtractionSessionError(f"Document {document_id} is not registered.")
    package = root / entry.package_path
    session_file = document_workspace_directory(root, document_id) / "extraction-session.json"
    annotations_file = package / "annotations.json"
    if not session_file.exists() and not annotations_file.exists():
        return ExtractionCheckpointStatus(document_id, "not_extracted")
    if not session_file.exists() or not annotations_file.exists():
        return ExtractionCheckpointStatus(
            document_id,
            "invalid",
            stale_reasons=(
                "The extraction checkpoint is incomplete; rebuild annotations.",
            ),
        )
    try:
        session = json.loads(session_file.read_text(encoding="utf-8"))
        annotations = json.loads(annotations_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ExtractionCheckpointStatus(
            document_id,
            "invalid",
            stale_reasons=(
                "The persisted extraction files cannot be read; rebuild annotations.",
            ),
        )
    if not isinstance(session, dict) or not isinstance(annotations, list):
        return ExtractionCheckpointStatus(
            document_id,
            "invalid",
            stale_reasons=(
                "The persisted extraction files have an invalid structure.",
            ),
        )
    reasons: list[str] = []
    declared_count = session.get("record_count")
    if not isinstance(declared_count, int) or declared_count != len(annotations):
        reasons.append("The persisted record count does not match annotations.json.")
    if not annotations:
        reasons.append("The persisted extraction contains zero annotation records.")
    if entry.source_state != "present":
        reasons.append(
            f"The registered source state is {entry.source_state}; synchronize it "
            "before rebuilding."
        )
    if session.get("source_checksum_sha256") != entry.checksum_sha256:
        reasons.append("The source document has changed since extraction.")
    try:
        selected = load_extraction_color_mapping(root, document_id)
        expected_mapping_checksum = _mapping_checksum(
            selected.status,
            selected.values,
        )
        if session.get("mapping_checksum_sha256") != expected_mapping_checksum:
            reasons.append(
                "The selected color mapping has changed or its legacy checkpoint "
                "does not record mapping provenance."
            )
    except ColorMappingError as error:
        reasons.append(f"The extraction mapping is unavailable: {error}")
    mapping_status = session.get("mapping_status")
    warnings = (
        ("Checkpoint uses a pending color map and is not curator-ready.",)
        if mapping_status == "pending_review"
        else ()
    )
    return ExtractionCheckpointStatus(
        document_id=document_id,
        state="stale" if reasons else "current",
        record_count=len(annotations),
        completed_at=(
            str(session.get("completed_at"))
            if session.get("completed_at")
            else None
        ),
        mapping_status=(
            str(mapping_status) if mapping_status is not None else None
        ),
        warnings=warnings,
        stale_reasons=tuple(reasons),
    )


def run_registered_extraction(
    project_root: str | Path,
    document_id: str,
    *,
    force: bool = False,
) -> SessionResult:
    """Run the appropriate extractor for one registered source and persist its results."""

    root = Path(project_root).resolve()
    registry_file = root / DEFAULT_REGISTRY_PATH
    registry = ProjectRegistry.model_validate_json(registry_file.read_text(encoding="utf-8"))
    matches = [item for item in registry.documents if item.document_id == document_id]
    if not matches:
        raise ExtractionSessionError(f"Document {document_id} is not registered.")
    entry = matches[0]
    if entry.source_state != "present":
        raise ExtractionSessionError(
            f"Document {document_id} source state is {entry.source_state}; synchronize it first."
        )
    package = root / entry.package_path
    session_file = document_workspace_directory(root, document_id) / "extraction-session.json"
    annotations_file = package / "annotations.json"
    extraction_mapping = load_extraction_color_mapping(root, document_id)
    mapping_checksum = _mapping_checksum(
        extraction_mapping.status,
        extraction_mapping.values,
    )
    if not force and session_file.is_file() and annotations_file.is_file():
        try:
            session = json.loads(session_file.read_text(encoding="utf-8"))
            annotations = json.loads(annotations_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            session = {}
            annotations = None
        record_count = session.get("record_count")
        checkpoint_current = (
            session.get("source_checksum_sha256") == entry.checksum_sha256
            and session.get("mapping_checksum_sha256") == mapping_checksum
            and isinstance(annotations, list)
            and isinstance(record_count, int)
            and record_count > 0
            and len(annotations) == record_count
        )
        if checkpoint_current:
            mapping_status = session.get("mapping_status")
            return SessionResult(
                document_id,
                annotations_file,
                session_file,
                record_count,
                reused_checkpoint=True,
                warnings=(
                    ("Checkpoint uses a pending color map and is not curator-ready.",)
                    if mapping_status == "pending_review"
                    else ()
                ),
            )

    mapping = extraction_mapping.values
    source = require_current_document_source(root, entry)
    if source.suffix.lower() == ".pdf":
        try:
            import fitz
        except ImportError as error:
            raise ExtractionSessionError(
                'PDF extraction is optional. Install the project with ".[extraction]".'
            ) from error
        with fitz.open(source) as document:
            has_text = any(page.get_text().strip() for page in document)
        if not has_text:
            raise ExtractionSessionError(
                "This PDF contains no extractable text. Image-only/scanned PDFs are "
                "unsupported because HEVA does not currently provide OCR."
            )
        from heva.extraction.pdf_extractor import extract_colored_highlights

        records = extract_colored_highlights(source, color_label_map=mapping)
        extractor_name = "HEVA PDF extractor"
    elif source.suffix.lower() == ".docx":
        from heva.extraction.docx_extractor import extract_docx_highlights

        records = extract_docx_highlights(source, color_label_map=mapping)
        extractor_name = "HEVA DOCX extractor"
    else:
        raise ExtractionSessionError(f"Unsupported source format: {source.suffix or '(none)'}")
    result = persist_extraction_results(
        root,
        document_id,
        records,
        extraction_method="automatic",
        extractor=extractor_name,
        extractor_version=TOOLKIT_VERSION,
        mapping_status=extraction_mapping.status,
    )
    return result


def run_registered_batch(
    project_root: str | Path,
    document_ids: Sequence[str] | None = None,
    *,
    force: bool = False,
    runner: Callable[..., SessionResult] = run_registered_extraction,
) -> BatchExtractionReport:
    """Run independent document sessions in stable registry order."""

    root = Path(project_root).resolve()
    registry = ProjectRegistry.model_validate_json(
        (root / DEFAULT_REGISTRY_PATH).read_text(encoding="utf-8")
    )
    requested = set(document_ids) if document_ids is not None else None
    known = {entry.document_id for entry in registry.documents}
    results: list[BatchDocumentResult] = []
    if requested is not None:
        for missing in sorted(requested - known):
            results.append(
                BatchDocumentResult(
                    document_id=missing,
                    status="failed",
                    error="Document is not registered.",
                    error_code="document_not_registered",
                )
            )
    selected = [
        entry
        for entry in sorted(registry.documents, key=lambda item: item.source_path)
        if requested is None or entry.document_id in requested
    ]
    for entry in selected:
        try:
            session = runner(root, entry.document_id, force=force)
            results.append(
                BatchDocumentResult(
                    document_id=entry.document_id,
                    status="reused" if session.reused_checkpoint else "completed",
                    record_count=session.record_count,
                    warnings=getattr(session, "warnings", ()),
                )
            )
        except Exception as error:
            results.append(
                BatchDocumentResult(
                    document_id=entry.document_id,
                    status="failed",
                    error=str(error),
                    error_code=getattr(error, "code", "extraction_failed"),
                )
            )
    return BatchExtractionReport(documents=tuple(results))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run registered HEVA document extraction sessions."
    )
    parser.add_argument("project_root", nargs="?", default=".")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--document-id", action="append", dest="document_ids")
    target.add_argument("--all", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--authorize-pending-map-by",
        metavar="NAME",
        help=(
            "Explicitly authorize existing pending color proposals for extraction "
            "before running the selected documents."
        ),
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    if args.authorize_pending_map_by:
        root = Path(args.project_root).resolve()
        registry = ProjectRegistry.model_validate_json(
            (root / DEFAULT_REGISTRY_PATH).read_text(encoding="utf-8")
        )
        selected_ids = (
            [entry.document_id for entry in registry.documents]
            if args.all
            else args.document_ids
        )
        by_id = {entry.document_id: entry for entry in registry.documents}
        for document_id in selected_ids:
            entry = by_id.get(document_id)
            if entry is None or entry.metadata_path is None:
                continue
            metadata = PackageMetadata.model_validate_json(
                (root / entry.metadata_path).read_text(encoding="utf-8")
            )
            configuration: ColorConfigurationMetadata = metadata.color_configuration
            if configuration.human_confirmed or configuration.use_for_extraction:
                continue
            authorized = authorize_pending_mapping_for_extraction(
                configuration,
                authorized_by=args.authorize_pending_map_by,
            )
            save_color_configuration(root, document_id, authorized)
    report = run_registered_batch(
        args.project_root,
        None if args.all else args.document_ids,
        force=args.force,
    )
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        for document in report.documents:
            if document.error:
                print(
                    f"{document.document_id}: ERROR [{document.error_code}] "
                    f"{document.error}"
                )
            else:
                print(f"{document.document_id}: {document.status}")
            for warning in document.warnings:
                print(f"  WARNING: {warning}")
    return 0 if report.successful else 1


if __name__ == "__main__":
    raise SystemExit(main())
