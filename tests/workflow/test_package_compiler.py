"""Acceptance tests for safe CSV-to-package compilation."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from heva.workflow import package_compiler
from heva.workflow.extraction_session import ExtractionSessionError
from heva.workflow.package_compiler import (
    CSV_FIELDS,
    PackageCompileError,
    compile_csv_packages,
)
from tests.workflow.test_package_validator import project, record


def write_csv(path: Path, document_id: str, item: dict[str, object]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerow(
            {
                "document_id": document_id,
                **{
                    key: (
                        json.dumps(item[key], ensure_ascii=False)
                        if key in {"values", "tokens", "entities", "ner_tags"}
                        else item.get(key, "")
                    )
                    for key in CSV_FIELDS[1:]
                },
            }
        )


def test_compile_updates_package_and_invalidates_changed_sentence_review(
    tmp_path: Path,
) -> None:
    document_id, package, registry_path = project(tmp_path)
    registry = json.loads(registry_path.read_text())
    registry["documents"][0]["status"] = "in_progress"
    registry["summary"]["in_review"] = 0
    registry["summary"]["in_progress"] = 1
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    changed = record()
    changed["sentence"] = "The historic harbour remains visible."
    changed["tokens"] = ["The", "historic", "harbour", "remains", "visible", "."]
    changed["ner_tags"] = ["O", "B-historic", "I-historic", "O", "O", "O"]
    csv_path = tmp_path / "edited.csv"
    write_csv(csv_path, document_id, changed)

    counts = compile_csv_packages(tmp_path, csv_path)

    assert counts == {document_id: 1}
    annotations = json.loads((package / "annotations.json").read_text())
    assert annotations[0]["sentence"].endswith("visible.")
    review = json.loads((tmp_path / ".heva/documents" / document_id / "review-state.json").read_text())
    assert review["sentences"][0]["status"] == "pending"
    assert review["sentences"][0]["audit"][0]["event"] == "source_record_changed"
    metadata = json.loads((package / "metadata.json").read_text())
    assert metadata["annotation_process"]["extractor"] == "HEVA CSV compiler"


def test_invalid_csv_is_rejected_before_existing_annotations_change(
    tmp_path: Path,
) -> None:
    document_id, package, registry_path = project(tmp_path)
    registry = json.loads(registry_path.read_text())
    registry["documents"][0]["status"] = "in_progress"
    registry["summary"]["in_review"] = 0
    registry["summary"]["in_progress"] = 1
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    before = (package / "annotations.json").read_bytes()
    invalid = record()
    invalid["entities"][0]["text"] = "wrong"
    csv_path = tmp_path / "invalid.csv"
    write_csv(csv_path, document_id, invalid)

    with pytest.raises(PackageCompileError, match="entity_text_mismatch"):
        compile_csv_packages(tmp_path, csv_path)

    assert (package / "annotations.json").read_bytes() == before


def test_legacy_submission_status_does_not_lock_csv_interoperability(tmp_path: Path) -> None:
    document_id, package, _ = project(tmp_path)
    csv_path = tmp_path / "edited.csv"
    changed = record()
    changed["sentence"] = "Editable legacy project."
    changed["tokens"] = ["Editable", "legacy", "project", "."]
    changed["entities"] = []
    changed["values"] = []
    changed["ner_tags"] = ["O", "O", "O", "O"]
    write_csv(csv_path, document_id, changed)

    compile_csv_packages(tmp_path, csv_path)

    annotations = json.loads((package / "annotations.json").read_text())
    assert annotations[0]["sentence"] == "Editable legacy project."


def test_runtime_failure_rolls_back_package_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document_id, package, registry_path = project(tmp_path)
    registry = json.loads(registry_path.read_text())
    registry["documents"][0]["status"] = "in_progress"
    registry["summary"]["in_review"] = 0
    registry["summary"]["in_progress"] = 1
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    csv_path = tmp_path / "edited.csv"
    write_csv(csv_path, document_id, record())
    before_annotations = (package / "annotations.json").read_bytes()
    before_registry = registry_path.read_bytes()

    def failing_persistence(*args, **kwargs):
        (package / "annotations.json").write_text("partially changed", encoding="utf-8")
        registry_path.write_text("partially changed", encoding="utf-8")
        raise ExtractionSessionError("simulated disk failure")

    monkeypatch.setattr(
        package_compiler,
        "persist_extraction_results",
        failing_persistence,
    )

    with pytest.raises(PackageCompileError, match="rolled back"):
        compile_csv_packages(tmp_path, csv_path)

    assert (package / "annotations.json").read_bytes() == before_annotations
    assert registry_path.read_bytes() == before_registry
