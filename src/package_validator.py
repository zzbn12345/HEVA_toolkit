"""Layered HEVA package validation and deterministic approved-data export."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any, Iterable, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from src.document_metadata import PackageMetadata, validate_review_readiness
from src.heva_contract import validate_record
from src.project_registry import DEFAULT_REGISTRY_PATH, ProjectRegistry, RegistrySummary
from src.review_state import DocumentReview


REPORT_VERSION = "1.0"
RELEASE_VERSION = "1.0"
DEFAULT_RELEASE_DIRECTORY = Path("data/release")


class ValidationIssue(BaseModel):
    """One actionable issue located in a project document."""

    model_config = ConfigDict(extra="forbid")

    code: str
    severity: Literal["error", "warning"]
    document_id: str
    path: str
    message: str
    action: str


class DocumentValidation(BaseModel):
    """Layered validation result for one registered package."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    valid: bool
    release_ready: bool
    issues: list[ValidationIssue]


class ProjectValidation(BaseModel):
    """Stable machine-readable report for one validation run."""

    model_config = ConfigDict(extra="forbid")

    report_version: str = REPORT_VERSION
    valid: bool
    release_ready: bool
    documents: list[DocumentValidation]


class PackageValidationError(ValueError):
    """Raised when validation or release creation cannot proceed safely."""


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
    source = root / entry.source_path
    if not source.is_file():
        issues.append(
            _issue(
                document_id,
                "source_missing",
                "$.registry.source_path",
                "The registered source file cannot be found.",
                "Restore the source file and synchronize the project registry.",
            )
        )

    metadata_value = _read_json(
        package / "package-metadata.json",
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
                        "Complete or correct this metadata before curator approval.",
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
        package / "review-state.json",
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
    return DocumentValidation(
        document_id=document_id,
        valid=not blocking,
        release_ready=not blocking and entry.status == "done",
        issues=issues,
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
    return ProjectValidation(
        valid=all(item.valid for item in documents),
        release_ready=bool(documents) and all(item.release_ready for item in documents),
        documents=documents,
    )


def approve_document(project_root: str | Path, document_id: str) -> None:
    """Mark an in-review document done only after all package gates pass."""

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
    if not report.valid:
        codes = ", ".join(item.code for item in report.issues if item.severity == "error")
        raise PackageValidationError(f"Document failed validation: {codes}")
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
    """Build byte-stable JSON and CSV representations from done documents only."""

    root = Path(project_root).resolve()
    registry = ProjectRegistry.model_validate_json(
        (root / DEFAULT_REGISTRY_PATH).read_text(encoding="utf-8")
    )
    done = sorted(
        (entry for entry in registry.documents if entry.status == "done"),
        key=lambda item: (item.source_path, item.document_id),
    )
    if not done:
        raise PackageValidationError("No approved documents are available for release.")
    rows: list[dict[str, Any]] = []
    documents: list[dict[str, Any]] = []
    for entry in done:
        report = validate_document_package(root, entry.document_id)
        if not report.release_ready:
            codes = ", ".join(item.code for item in report.issues if item.severity == "error")
            raise PackageValidationError(
                f"Approved document {entry.document_id} failed validation: {codes}"
            )
        annotations = json.loads(
            (root / entry.package_path / "annotations.json").read_text(encoding="utf-8")
        )
        reviews = DocumentReview.model_validate_json(
            (root / entry.package_path / "review-state.json").read_text(encoding="utf-8")
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
        documents.append(
            {
                "document_id": entry.document_id,
                "source_checksum_sha256": entry.checksum_sha256,
                "record_count": len(canonical),
                "records": canonical,
            }
        )
        rows.extend({"document_id": entry.document_id, **item} for item in canonical)

    target = root / Path(output_directory)
    target.mkdir(parents=True, exist_ok=True)
    payload = {
        "release_version": RELEASE_VERSION,
        "document_count": len(documents),
        "record_count": len(rows),
        "documents": documents,
    }
    _write_json(target / "heva-annotations.json", payload)
    csv_target = target / "heva-annotations.csv"
    temporary = csv_target.with_suffix(".csv.tmp")
    temporary.write_text(_csv_text(rows), encoding="utf-8", newline="")
    temporary.replace(csv_target)
    _write_json(
        target / "datapackage.json",
        {
            "name": "heva-approved-annotations",
            "profile": "data-package",
            "resources": [
                {"name": "heva-annotations-json", "path": "heva-annotations.json"},
                {"name": "heva-annotations-csv", "path": "heva-annotations.csv"},
            ],
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
    approve = commands.add_parser("approve")
    approve.add_argument("--document-id", required=True)
    release = commands.add_parser("release")
    release.add_argument("--output", default=DEFAULT_RELEASE_DIRECTORY.as_posix())
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "validate":
            if args.document_id:
                document = validate_document_package(args.project_root, args.document_id)
                report = ProjectValidation(
                    valid=document.valid,
                    release_ready=document.release_ready,
                    documents=[document],
                )
            else:
                report = validate_project(args.project_root)
            rendered = json.dumps(
                report.model_dump(mode="json"),
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            )
            if args.report:
                Path(args.report).write_text(rendered + "\n", encoding="utf-8")
            print(rendered)
            return 0 if report.valid else 1
        if args.command == "approve":
            approve_document(args.project_root, args.document_id)
            print(f"{args.document_id} approved for release")
            return 0
        target = build_release(args.project_root, output_directory=args.output)
        print(f"HEVA release written to {target}")
        return 0
    except (PackageValidationError, OSError, ValidationError, ValueError) as error:
        print(f"VALIDATION ERROR: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
