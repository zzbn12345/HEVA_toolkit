"""Build a deterministic HEVA collection from completed document packages."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

from pydantic import ValidationError

from heva.workflow.contract import ContractIssue, validate_record
from heva.workflow.project_registry import DEFAULT_REGISTRY_PATH, ProjectRegistry


DEFAULT_COLLECTION_PATH = Path("exports/heva-collection.json")
COLLECTION_VERSION = "1.0"


class CollectionBuildError(ValueError):
    """Raised when completed packages cannot safely form a collection."""


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def build_collection(
    project_root: str | Path,
    *,
    output_path: str | Path = DEFAULT_COLLECTION_PATH,
) -> Path:
    """Validate and aggregate only registry documents whose review status is done."""

    root = Path(project_root).resolve()
    registry_file = root / DEFAULT_REGISTRY_PATH
    try:
        registry = ProjectRegistry.model_validate_json(registry_file.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as error:
        raise CollectionBuildError(f"Cannot load project registry: {error}") from error

    documents: list[dict[str, Any]] = []
    all_issues: list[str] = []
    completed = sorted(
        (entry for entry in registry.documents if entry.status == "done"),
        key=lambda entry: (entry.source_path, entry.document_id),
    )
    for entry in completed:
        annotations_file = root / entry.package_path / "annotations.json"
        try:
            decoded = json.loads(annotations_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            all_issues.append(f"{entry.document_id}: cannot read annotations: {error}")
            continue
        if not isinstance(decoded, list):
            all_issues.append(f"{entry.document_id}: annotations must be a JSON array")
            continue
        results = [validate_record(record) for record in decoded]
        issues: list[ContractIssue] = [
            issue for result in results for issue in result.issues
        ]
        if issues:
            all_issues.extend(
                f"{entry.document_id}: {issue.code} {issue.path}: {issue.message}"
                for issue in issues
            )
            continue
        records = [
            result.record.to_dict() for result in results if result.record is not None
        ]
        records.sort(key=lambda record: (record["page"], record["sentence_id"]))
        documents.append(
            {
                "document_id": entry.document_id,
                "source_path": entry.source_path,
                "source_checksum_sha256": entry.checksum_sha256,
                "record_count": len(records),
                "records": records,
            }
        )
    if all_issues:
        raise CollectionBuildError(
            "Completed packages contain invalid annotation data:\n- "
            + "\n- ".join(all_issues)
        )
    target = root / Path(output_path)
    _write_json(
        target,
        {
            "collection_version": COLLECTION_VERSION,
            "document_count": len(documents),
            "record_count": sum(document["record_count"] for document in documents),
            "documents": documents,
        },
    )
    return target


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a deterministic collection from completed HEVA packages."
    )
    parser.add_argument("project_root", nargs="?", default=".")
    parser.add_argument("--output", default=DEFAULT_COLLECTION_PATH.as_posix())
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        target = build_collection(args.project_root, output_path=args.output)
    except CollectionBuildError as error:
        print(f"COLLECTION ERROR: {error}")
        return 1
    print(f"HEVA collection written to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
