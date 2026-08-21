"""Layered HEVA package validation and deterministic approved-data export."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any, Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from heva.workflow.document_metadata import (
    PackageMetadata,
    validate_review_readiness,
)
from heva.workflow.contract import validate_record
from heva.workflow.project_registry import (
    DEFAULT_REGISTRY_PATH,
    ProjectRegistry,
    RegistrySummary,
    document_workspace_directory,
    require_current_document_source,
)
from heva.workflow.review_state import DocumentReview


REPORT_VERSION = "1.0"
RELEASE_VERSION = "1.0"
DEFAULT_RELEASE_DIRECTORY = Path("exports/heva-data-package")
DEFAULT_DATASET_METADATA_PATH = Path("dataset-metadata.json")
TOOLKIT_VERSION = "0.1.0"
CITATION_REQUIREMENT_CODES = frozenset(
    {
        "missing_source_title",
        "missing_source_creator",
        "missing_citation",
        "missing_findability",
        "citation_not_validated",
    }
)


class DatasetReleaseMetadata(BaseModel):
    """Required citable identity and human release guidance for one dataset."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    creators: list[str] = Field(min_length=1)
    contributors: list[str] = Field(default_factory=list)
    license: str = Field(min_length=1)
    rights: str = Field(min_length=1)
    known_limitations: list[str] = Field(min_length=1)

    @field_validator(
        "name",
        "title",
        "description",
        "license",
        "rights",
        mode="before",
    )
    @classmethod
    def strip_required_text(cls, value: object) -> object:
        """Reject required values that contain only whitespace."""

        return value.strip() if isinstance(value, str) else value

    @field_validator("contributors")
    @classmethod
    def normalize_optional_text_list(cls, values: list[str]) -> list[str]:
        """Trim contributor entries, remove blanks, and preserve input order."""

        return list(dict.fromkeys(value.strip() for value in values if value.strip()))

    @field_validator("creators", "known_limitations")
    @classmethod
    def normalize_required_text_lists(cls, values: list[str]) -> list[str]:
        """Require at least one meaningful, unique item in release-critical lists."""

        normalized = list(dict.fromkeys(value.strip() for value in values if value.strip()))
        if not normalized:
            raise ValueError("at least one non-empty value is required")
        return normalized


class ValidationIssue(BaseModel):
    """One actionable issue located in a project document."""

    model_config = ConfigDict(extra="forbid")

    code: str
    severity: Literal["error", "warning"]
    document_id: str
    path: str
    message: str
    action: str
    guide: str


class DocumentValidation(BaseModel):
    """Layered validation result for one registered package."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    source_path: str
    workflow_status: str
    completed: bool
    valid: bool
    curation_ready: bool = False
    release_ready: bool
    issues: list[ValidationIssue]


class ValidationSummary(BaseModel):
    """Test-runner-style counts for one project validation."""

    model_config = ConfigDict(extra="forbid")

    documents: int
    passed: int
    failed: int
    completed: int
    not_completed: int
    errors: int
    warnings: int


class ProjectValidation(BaseModel):
    """Stable machine-readable report for one validation run."""

    model_config = ConfigDict(extra="forbid")

    report_version: str = REPORT_VERSION
    valid: bool
    release_ready: bool
    summary: ValidationSummary
    documents: list[DocumentValidation]


class PackageValidationError(ValueError):
    """Raised when validation or release creation cannot proceed safely."""


def curation_blocking_issues(report: DocumentValidation) -> list[ValidationIssue]:
    """Return errors that block annotation curation, excluding release-only citation."""

    return [
        issue
        for issue in report.issues
        if issue.severity == "error" and issue.code not in CITATION_REQUIREMENT_CODES
    ]


def _guide_for_issue(code: str, path: str) -> str:
    """Return the most relevant stable documentation slug for a validation issue."""

    if "package" in code or "resource" in code or "citation" in path or "rights" in path:
        return "DATA_PACKAGE"
    if code.startswith("source_") or "registry" in path:
        return "TUTORIAL"
    return "HEVA_AND_VALIDATION"


def _issue(
    document_id: str,
    code: str,
    path: str,
    message: str,
    action: str,
    severity: Literal["error", "warning"] = "error",
) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        severity=severity,
        document_id=document_id,
        path=path,
        message=message,
        action=action,
        guide=_guide_for_issue(code, path),
    )


def _record_digest(record: dict[str, Any]) -> str:
    encoded = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _read_json(
    path: Path,
    document_id: str,
    logical_path: str,
    issues: list[ValidationIssue],
) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        issues.append(
            _issue(
                document_id,
                "missing_package_file",
                logical_path,
                f"Required package file {path.name} is missing.",
                f"Create or restore {path.name}, then validate again.",
            )
        )
    except json.JSONDecodeError as error:
        issues.append(
            _issue(
                document_id,
                "invalid_json",
                logical_path,
                f"Invalid JSON at line {error.lineno}, column {error.colno}: {error.msg}.",
                f"Correct the JSON syntax in {path.name}.",
            )
        )
    except OSError as error:
        issues.append(
            _issue(
                document_id,
                "unreadable_package_file",
                logical_path,
                f"Cannot read {path.name}: {error}.",
                "Check that the file exists and is readable.",
            )
        )
    return None


def validate_document_package(
    project_root: str | Path,
    document_id: str,
) -> DocumentValidation:
    """Validate syntax, contract, links, mapping, review, rights, and release state."""

    root = Path(project_root).resolve()
    registry_path = root / DEFAULT_REGISTRY_PATH
    try:
        registry = ProjectRegistry.model_validate_json(registry_path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as error:
        raise PackageValidationError(f"Cannot load project registry: {error}") from error
    entries = [entry for entry in registry.documents if entry.document_id == document_id]
    if not entries:
        raise PackageValidationError(f"Document {document_id} is not registered.")
    entry = entries[0]
    package = root / entry.package_path
    issues: list[ValidationIssue] = []

    if entry.source_state != "present":
        issues.append(
            _issue(
                document_id,
                "source_not_current",
                "$.registry.source_state",
                f"Registered source state is {entry.source_state}.",
                "Restore the source or synchronize and re-extract the changed document.",
            )
        )
    try:
        source = require_current_document_source(root, entry)
    except Exception:
        source = None
    if source is None or not source.is_file():
        issues.append(
            _issue(
                document_id,
                "source_missing",
                "$.registry.source_path",
                "The registered source file cannot be found.",
                "Restore the source file and synchronize the project registry.",
            )
        )

    # Migrate an unambiguous legacy singular annotator before evaluating the public record.
    try:
        from heva.workflow.document_contributors import load_document_annotators

        load_document_annotators(root, document_id)
    except ValueError:
        pass
    metadata_value = _read_json(
        root / entry.metadata_path if entry.metadata_path else package / "metadata.json",
        document_id,
        "$.package_metadata",
        issues,
    )
    metadata: PackageMetadata | None = None
    if metadata_value is not None:
        try:
            metadata = PackageMetadata.model_validate(metadata_value)
        except ValidationError as error:
            for item in error.errors():
                suffix = "".join(
                    f"[{part}]" if isinstance(part, int) else f".{part}"
                    for part in item.get("loc", ())
                )
                issues.append(
                    _issue(
                        document_id,
                        "invalid_package_metadata",
                        f"$.package_metadata{suffix}",
                        item.get("msg", "Package metadata is invalid."),
                        "Correct the package metadata field to match the HEVA specification.",
                    )
                )
        if metadata is not None:
            if metadata.document_id != document_id:
                issues.append(
                    _issue(
                        document_id,
                        "metadata_document_mismatch",
                        "$.package_metadata.document_id",
                        "Package metadata refers to a different document ID.",
                        "Set package metadata document_id to the registered document ID.",
                    )
                )
            for item in validate_review_readiness(metadata).issues:
                issues.append(
                    _issue(
                        document_id,
                        item.code,
                        f"$.package_metadata{item.path[1:]}",
                        item.message,
                        (
                            "No correction is required; the recorded findability explanation will be included in the Data Package."
                            if item.code == "source_not_findable"
                            else
                            "Complete and validate the citation before Data Package generation."
                            if item.code in CITATION_REQUIREMENT_CODES
                            else "Complete or correct this metadata before Data Package export."
                        ),
                        item.severity,
                    )
                )

    annotations_value = _read_json(
        package / "annotations.json",
        document_id,
        "$.annotations",
        issues,
    )
    records: list[dict[str, Any]] = []
    if annotations_value is not None:
        if not isinstance(annotations_value, list):
            issues.append(
                _issue(
                    document_id,
                    "invalid_annotations_document",
                    "$.annotations",
                    "Annotations must be a JSON array.",
                    "Store canonical sentence records as a JSON array.",
                )
            )
        else:
            seen_ids: set[int] = set()
            for index, value in enumerate(annotations_value):
                result = validate_record(value)
                for item in result.issues:
                    issues.append(
                        _issue(
                            document_id,
                            item.code,
                            f"$.annotations[{index}]{item.path[1:]}",
                            item.message,
                            "Correct the sentence record and run validation again.",
                        )
                    )
                if result.valid and result.record is not None:
                    record = result.record.to_dict()
                    sentence_id = record["sentence_id"]
                    if sentence_id in seen_ids:
                        issues.append(
                            _issue(
                                document_id,
                                "duplicate_sentence_id",
                                f"$.annotations[{index}].sentence_id",
                                f"Sentence ID {sentence_id} occurs more than once.",
                                "Assign a unique, stable sentence ID within the document.",
                            )
                        )
                    seen_ids.add(sentence_id)
                    records.append(record)

    if metadata is not None:
        resources = [item for item in metadata.resources if item.name == "annotations"]
        if resources and resources[0].path != "annotations.json":
            issues.append(
                _issue(
                    document_id,
                    "annotation_resource_mismatch",
                    "$.package_metadata.resources",
                    "The annotations resource does not point to annotations.json.",
                    "Set the annotations resource path to annotations.json.",
                )
            )
        if resources and annotations_value is not None:
            actual_count = len(annotations_value) if isinstance(annotations_value, list) else 0
            if resources[0].record_count != actual_count:
                issues.append(
                    _issue(
                        document_id,
                        "annotation_count_mismatch",
                        "$.package_metadata.resources",
                        "The declared annotation count does not match annotations.json.",
                        f"Set record_count to {actual_count}.",
                    )
                )

    review_value = _read_json(
        document_workspace_directory(root, document_id) / "review-state.json",
        document_id,
        "$.review_state",
        issues,
    )
    if review_value is not None:
        try:
            review = DocumentReview.model_validate(review_value)
        except ValidationError as error:
            issues.append(
                _issue(
                    document_id,
                    "invalid_review_state",
                    "$.review_state",
                    str(error),
                    "Reinitialize review state and repeat the sentence decisions.",
                )
            )
        else:
            if review.document_id != document_id:
                issues.append(
                    _issue(
                        document_id,
                        "review_document_mismatch",
                        "$.review_state.document_id",
                        "Review state refers to a different document.",
                        "Reinitialize review state for this document.",
                    )
                )
            record_ids = {record["sentence_id"] for record in records}
            review_ids = {item.sentence_id for item in review.sentences}
            if record_ids != review_ids:
                issues.append(
                    _issue(
                        document_id,
                        "review_annotation_mismatch",
                        "$.review_state.sentences",
                        "Review sentence IDs do not match the canonical annotations.",
                        "Reinitialize review state and review every current sentence.",
                    )
                )
            record_digests = {
                record["sentence_id"]: _record_digest(record) for record in records
            }
            stale = [
                item.sentence_id
                for item in review.sentences
                if record_digests.get(item.sentence_id) != item.record_sha256
            ]
            if stale:
                issues.append(
                    _issue(
                        document_id,
                        "stale_sentence_review",
                        "$.review_state.sentences",
                        f"Review decisions no longer match sentences: {stale}.",
                        "Reinitialize review state and review the changed sentences.",
                    )
                )
            unresolved = [
                item.sentence_id
                for item in review.sentences
                if item.status in {"pending", "needs_correction"}
            ]
            if unresolved:
                issues.append(
                    _issue(
                        document_id,
                        "sentence_review_incomplete",
                        "$.review_state.sentences",
                        f"Sentences still require a final decision: {unresolved}.",
                        "Approve, correct, or exclude every listed sentence.",
                    )
                )

    blocking = any(item.severity == "error" for item in issues)
    curation_blocking = any(
        item.severity == "error" and item.code not in CITATION_REQUIREMENT_CODES
        for item in issues
    )
    return DocumentValidation(
        document_id=document_id,
        source_path=entry.source_path,
        workflow_status=entry.status,
        completed=not blocking,
        valid=not blocking,
        curation_ready=not curation_blocking,
        release_ready=not blocking,
        issues=issues,
    )


def _project_report(documents: list[DocumentValidation]) -> ProjectValidation:
    """Summarize document reports without conflating validity and completion."""

    return ProjectValidation(
        valid=all(item.valid for item in documents),
        release_ready=bool(documents) and all(item.release_ready for item in documents),
        summary=ValidationSummary(
            documents=len(documents),
            passed=sum(item.valid for item in documents),
            failed=sum(not item.valid for item in documents),
            completed=sum(item.completed for item in documents),
            not_completed=sum(not item.completed for item in documents),
            errors=sum(
                issue.severity == "error"
                for document in documents
                for issue in document.issues
            ),
            warnings=sum(
                issue.severity == "warning"
                for document in documents
                for issue in document.issues
            ),
        ),
        documents=documents,
    )


def validate_project(project_root: str | Path) -> ProjectValidation:
    """Validate every registered package in stable document-ID order."""

    root = Path(project_root).resolve()
    try:
        registry = ProjectRegistry.model_validate_json(
            (root / DEFAULT_REGISTRY_PATH).read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as error:
        raise PackageValidationError(f"Cannot load project registry: {error}") from error
    documents = [
        validate_document_package(root, entry.document_id)
        for entry in sorted(registry.documents, key=lambda item: item.document_id)
    ]
    return _project_report(documents)


def format_validation_report(report: ProjectValidation) -> str:
    """Render a concise human report while preserving JSON as a separate interface."""

    lines = ["HEVA validation"]
    for document in report.documents:
        outcome = "PASS" if document.valid else "FAIL"
        completion = "completed" if document.completed else "not completed"
        lines.append(
            f"{outcome} {document.source_path} "
            f"({document.document_id}, {completion}, {document.workflow_status})"
        )
        for issue in document.issues:
            lines.append(
                f"  {issue.severity.upper()} {issue.code} {issue.path}: {issue.message}"
            )
            lines.append(f"    Fix: {issue.action}")
            lines.append(f"    Guide: docs/{issue.guide}.md")
    summary = report.summary
    lines.append(
        f"{summary.passed} passed, {summary.failed} failed; "
        f"{summary.completed} completed, {summary.not_completed} not completed; "
        f"{summary.errors} errors, {summary.warnings} warnings"
    )
    return "\n".join(lines)


def approve_document(project_root: str | Path, document_id: str) -> None:
    """Retain the former approval transition for legacy curation-state compatibility."""

    root = Path(project_root).resolve()
    registry_path = root / DEFAULT_REGISTRY_PATH
    registry = ProjectRegistry.model_validate_json(registry_path.read_text(encoding="utf-8"))
    entry = next(
        (item for item in registry.documents if item.document_id == document_id),
        None,
    )
    if entry is None:
        raise PackageValidationError(f"Document {document_id} is not registered.")
    if entry.status != "in_review":
        raise PackageValidationError("Only a document in_review can be approved.")
    report = validate_document_package(root, document_id)
    blockers = curation_blocking_issues(report)
    if blockers:
        codes = ", ".join(item.code for item in blockers)
        raise PackageValidationError(f"Document failed curation checks: {codes}")
    entry.status = "done"
    registry.summary = RegistrySummary(
        total=len(registry.documents),
        backlog=sum(item.status == "backlog" for item in registry.documents),
        in_progress=sum(item.status == "in_progress" for item in registry.documents),
        in_review=sum(item.status == "in_review" for item in registry.documents),
        done=sum(item.status == "done" for item in registry.documents),
        changed=sum(item.source_state == "changed" for item in registry.documents),
        missing=sum(item.source_state == "missing" for item in registry.documents),
    )
    _write_json(registry_path, registry.model_dump(mode="json"))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _csv_text(rows: list[dict[str, Any]]) -> str:
    fields = [
        "document_id",
        "sentence_id",
        "page",
        "sentence",
        "values",
        "tokens",
        "entities",
        "ner_tags",
        "schema_version",
    ]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                key: (
                    json.dumps(row[key], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                    if key in {"values", "tokens", "entities", "ner_tags"}
                    else row[key]
                )
                for key in fields
            }
        )
    return stream.getvalue()


def build_release(
    project_root: str | Path,
    *,
    output_directory: str | Path = DEFAULT_RELEASE_DIRECTORY,
) -> Path:
    """Build a deterministic Data Package from HEVA-valid registered documents."""

    root = Path(project_root).resolve()
    try:
        dataset_metadata = DatasetReleaseMetadata.model_validate_json(
            (root / DEFAULT_DATASET_METADATA_PATH).read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as error:
        raise PackageValidationError(
            "Cannot build a citable release without valid dataset-metadata.json: "
            f"{error}"
        ) from error
    registry = ProjectRegistry.model_validate_json(
        (root / DEFAULT_REGISTRY_PATH).read_text(encoding="utf-8")
    )
    documents_to_export = sorted(
        registry.documents,
        key=lambda item: (item.source_path, item.document_id),
    )
    if not documents_to_export:
        raise PackageValidationError("No registered documents are available for export.")
    rows: list[dict[str, Any]] = []
    documents: list[dict[str, Any]] = []
    for entry in documents_to_export:
        report = validate_document_package(root, entry.document_id)
        if not report.release_ready:
            codes = ", ".join(item.code for item in report.issues if item.severity == "error")
            raise PackageValidationError(
                f"Document {entry.document_id} failed validation: {codes}"
            )
        annotations = json.loads(
            (root / entry.package_path / "annotations.json").read_text(encoding="utf-8")
        )
        reviews = DocumentReview.model_validate_json(
            (
                document_workspace_directory(root, entry.document_id) / "review-state.json"
            ).read_text(encoding="utf-8")
        )
        package_metadata = PackageMetadata.model_validate_json(
            (root / (entry.metadata_path or f"{entry.package_path}/metadata.json")).read_text(
                encoding="utf-8"
            )
        )
        included = {
            item.sentence_id for item in reviews.sentences if item.status == "approved"
        }
        canonical = [
            validate_record(item).record.to_dict()
            for item in annotations
            if item["sentence_id"] in included
        ]
        canonical.sort(key=lambda item: (item["page"], item["sentence_id"]))
        annotations_checksum = hashlib.sha256(
            json.dumps(
                canonical,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        documents.append(
            {
                "document_id": entry.document_id,
                "source_checksum_sha256": entry.checksum_sha256,
                "annotations_checksum_sha256": annotations_checksum,
                "citation": package_metadata.source.citation,
                "source_creators": package_metadata.source.creators,
                "source_reference": package_metadata.source.reference,
                "source_not_findable_reason": (
                    package_metadata.source.not_findable_reason
                ),
                "rights": package_metadata.rights.model_dump(mode="json"),
                "original_annotators": [
                    item.model_dump(mode="json")
                    for item in package_metadata.original_annotators
                ],
                "record_count": len(canonical),
                "records": canonical,
            }
        )
        rows.extend({"document_id": entry.document_id, **item} for item in canonical)

    target = root / Path(output_directory)
    target.mkdir(parents=True, exist_ok=True)
    payload = {
        "release_version": RELEASE_VERSION,
        "schema_version": "1.0",
        "toolkit_version": TOOLKIT_VERSION,
        "dataset": dataset_metadata.model_dump(mode="json"),
        "document_count": len(documents),
        "record_count": len(rows),
        "membership": [document["document_id"] for document in documents],
        "documents": documents,
    }
    _write_json(target / "heva-annotations.json", payload)
    csv_target = target / "heva-annotations.csv"
    temporary = csv_target.with_suffix(".csv.tmp")
    temporary.write_text(_csv_text(rows), encoding="utf-8", newline="")
    temporary.replace(csv_target)
    build_log = {
        "build_version": RELEASE_VERSION,
        "toolkit_version": TOOLKIT_VERSION,
        "membership": [
            {
                "document_id": document["document_id"],
                "source_checksum_sha256": document["source_checksum_sha256"],
                "annotations_checksum_sha256": document["annotations_checksum_sha256"],
            }
            for document in documents
        ],
        "excluded_working_evidence": [
            "source documents",
            "review-state.json",
            "curation-state.json",
            "credentials",
        ],
    }
    _write_json(target / "build-log.json", build_log)
    resources = []
    for name, filename, media_type in (
        ("heva-annotations-json", "heva-annotations.json", "application/json"),
        ("heva-annotations-csv", "heva-annotations.csv", "text/csv"),
        ("build-log", "build-log.json", "application/json"),
    ):
        resource_path = target / filename
        resources.append(
            {
                "name": name,
                "path": filename,
                "mediatype": media_type,
                "bytes": resource_path.stat().st_size,
                "hash": f"sha256:{hashlib.sha256(resource_path.read_bytes()).hexdigest()}",
            }
        )
    _write_json(
        target / "datapackage.json",
        {
            "name": dataset_metadata.name,
            "title": dataset_metadata.title,
            "description": dataset_metadata.description,
            "profile": "data-package",
            "licenses": [{"name": dataset_metadata.license}],
            "contributors": [
                *(
                    {"title": creator, "role": "creator"}
                    for creator in dataset_metadata.creators
                ),
                *(
                    {"title": contributor, "role": "contributor"}
                    for contributor in dataset_metadata.contributors
                ),
            ],
            "resources": resources,
        },
    )
    return target


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and release HEVA packages.")
    parser.add_argument("project_root", nargs="?", default=".")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--document-id")
    validate.add_argument("--report")
    validate.add_argument(
        "--json",
        action="store_true",
        help="Print the stable machine-readable report instead of the terminal summary.",
    )
    release = commands.add_parser("release")
    release.add_argument("--output", default=DEFAULT_RELEASE_DIRECTORY.as_posix())
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "validate":
            if args.document_id:
                document = validate_document_package(args.project_root, args.document_id)
                report = _project_report([document])
            else:
                report = validate_project(args.project_root)
            rendered = json.dumps(
                report.model_dump(mode="json"),
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            )
            if args.report:
                report_path = Path(args.report)
                report_path.parent.mkdir(parents=True, exist_ok=True)
                report_path.write_text(rendered + "\n", encoding="utf-8")
            print(rendered if args.json else format_validation_report(report))
            return 0 if report.valid else 1
        target = build_release(args.project_root, output_directory=args.output)
        print(f"HEVA release written to {target}")
        return 0
    except (PackageValidationError, OSError, ValidationError, ValueError) as error:
        print(f"VALIDATION ERROR: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
