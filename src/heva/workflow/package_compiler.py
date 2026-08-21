"""Compile edited HEVA CSV rows into validated document-local package records."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Iterable

from pydantic import ValidationError

from heva.workflow.color_mapping import (
    ColorMappingError,
    load_confirmed_color_mapping,
)
from heva.workflow.contract import validate_record
from heva.workflow.extraction_session import (
    ExtractionSessionError,
    persist_extraction_results,
)
from heva.workflow.project_registry import (
    DEFAULT_REGISTRY_PATH,
    ProjectRegistry,
    document_workspace_directory,
)


CSV_FIELDS = (
    "document_id",
    "sentence_id",
    "page",
    "sentence",
    "values",
    "tokens",
    "entities",
    "ner_tags",
    "schema_version",
)
JSON_FIELDS = frozenset({"values", "tokens", "entities", "ner_tags"})


class PackageCompileError(ValueError):
    """Raised when edited CSV cannot safely replace working annotations."""


def _decode_row(row: dict[str, str], row_number: int) -> tuple[str, dict[str, Any]]:
    document_id = (row.get("document_id") or "").strip()
    if not document_id:
        raise PackageCompileError(f"CSV row {row_number}: document_id is required.")
    decoded: dict[str, Any] = {}
    for field in CSV_FIELDS[1:]:
        value = row.get(field)
        if value is None:
            raise PackageCompileError(f"CSV row {row_number}: missing column {field}.")
        if field in JSON_FIELDS:
            try:
                decoded[field] = json.loads(value)
            except json.JSONDecodeError as error:
                raise PackageCompileError(
                    f"CSV row {row_number}, {field}: invalid JSON: {error.msg}."
                ) from error
        elif field in {"sentence_id", "page"}:
            try:
                decoded[field] = int(value)
            except ValueError as error:
                raise PackageCompileError(
                    f"CSV row {row_number}, {field}: expected an integer."
                ) from error
        else:
            decoded[field] = value
    result = validate_record(decoded)
    if not result.valid or result.record is None:
        issues = "; ".join(
            f"{issue.code} {issue.path}: {issue.message}" for issue in result.issues
        )
        raise PackageCompileError(f"CSV row {row_number}: {issues}")
    return document_id, result.record.to_dict()


def load_compilation_rows(csv_path: str | Path) -> dict[str, list[dict[str, Any]]]:
    """Parse and validate every CSV row before any document package is changed."""

    path = Path(csv_path)
    try:
        with path.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            missing = [field for field in CSV_FIELDS if field not in (reader.fieldnames or [])]
            if missing:
                raise PackageCompileError(
                    f"CSV is missing required columns: {', '.join(missing)}."
                )
            grouped: dict[str, list[dict[str, Any]]] = {}
            identities: set[tuple[str, int]] = set()
            for row_number, row in enumerate(reader, start=2):
                document_id, record = _decode_row(row, row_number)
                identity = (document_id, record["sentence_id"])
                if identity in identities:
                    raise PackageCompileError(
                        f"CSV row {row_number}: duplicate sentence_id "
                        f"{record['sentence_id']} for {document_id}."
                    )
                identities.add(identity)
                grouped.setdefault(document_id, []).append(record)
    except OSError as error:
        raise PackageCompileError(f"Cannot read CSV {path}: {error}") from error
    if not grouped:
        raise PackageCompileError("CSV contains no annotation rows.")
    for records in grouped.values():
        records.sort(key=lambda item: (item["page"], item["sentence_id"]))
    return grouped


def compile_csv_packages(
    project_root: str | Path,
    csv_path: str | Path,
) -> dict[str, int]:
    """Compile a release-shaped CSV after a complete project and mapping preflight."""

    root = Path(project_root).resolve()
    grouped = load_compilation_rows(csv_path)
    try:
        registry = ProjectRegistry.model_validate_json(
            (root / DEFAULT_REGISTRY_PATH).read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as error:
        raise PackageCompileError(f"Cannot load project registry: {error}") from error
    entries = {entry.document_id: entry for entry in registry.documents}
    for document_id in grouped:
        entry = entries.get(document_id)
        if entry is None:
            raise PackageCompileError(f"Document {document_id} is not registered.")
        if entry.source_state != "present":
            raise PackageCompileError(
                f"Document {document_id} source is {entry.source_state}; synchronize first."
            )
        try:
            load_confirmed_color_mapping(root, document_id)
        except ColorMappingError as error:
            raise PackageCompileError(
                f"Document {document_id} needs a confirmed color map: {error}"
            ) from error

    protected_paths = [root / DEFAULT_REGISTRY_PATH]
    for document_id in grouped:
        package = root / entries[document_id].package_path
        workspace = document_workspace_directory(root, document_id)
        protected_paths.extend(
            (
                package / "annotations.json",
                package / "metadata.json",
                workspace / "review-state.json",
                workspace / "extraction-session.json",
            )
        )
    backups = {
        path: path.read_bytes() if path.exists() else None for path in protected_paths
    }

    counts: dict[str, int] = {}
    try:
        for document_id in sorted(grouped):
            result = persist_extraction_results(
                root,
                document_id,
                grouped[document_id],
                extraction_method="manual",
                extractor="HEVA CSV compiler",
                extractor_version="0.1.0",
            )
            counts[document_id] = result.record_count
    except (ExtractionSessionError, OSError, ValueError) as error:
        for path, content in backups.items():
            if content is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(content)
        raise PackageCompileError(
            f"Compilation was rolled back without changing packages: {error}"
        ) from error
    return counts


def main(argv: Iterable[str] | None = None) -> int:
    """Compile edited CSV through the command-line interoperability surface."""

    parser = argparse.ArgumentParser(
        description="Compile edited HEVA CSV rows into registered document packages."
    )
    parser.add_argument("project_root", nargs="?", default=".")
    parser.add_argument("--csv", required=True)
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        counts = compile_csv_packages(args.project_root, args.csv)
    except PackageCompileError as error:
        print(f"COMPILE ERROR: {error}")
        return 1
    print(
        f"Compiled {sum(counts.values())} records into {len(counts)} document package(s)."
    )
    for document_id, count in counts.items():
        print(f"  {document_id}: {count} records; sentence review refreshed")
    print("Next: run HEVA project validation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
