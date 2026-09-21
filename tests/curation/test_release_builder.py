"""Acceptance tests for deterministic completed-package aggregation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from heva.curation.release_builder import CollectionBuildError, build_collection
from heva.curation.project_registry import sync_registry


def record(sentence_id: int) -> dict[str, object]:
    return {
        "sentence_id": sentence_id,
        "page": 1,
        "sentence": "The historic harbour remains visible.",
        "tokens": ["The", "historic", "harbour", "remains", "visible", "."],
        "values": ["historic"],
        "entities": [{
            "start": 4, "end": 20, "text": "historic harbour",
            "label": "historic", "color": "#FF40FF",
        }],
        "ner_tags": ["O", "B-historic", "I-historic", "O", "O", "O"],
        "schema_version": "1.0",
    }


def test_collection_includes_only_done_packages_in_stable_order(tmp_path: Path) -> None:
    sources = tmp_path / "documents"
    sources.mkdir()
    (sources / "b.pdf").write_bytes(b"b")
    (sources / "a.pdf").write_bytes(b"a")
    sync_registry(tmp_path, source_dir="documents")
    registry_path = tmp_path / ".heva/project.json"
    registry = json.loads(registry_path.read_text())
    for index, entry in enumerate(registry["documents"]):
        entry["status"] = "done" if index == 0 else "in_progress"
        package = tmp_path / entry["package_path"]
        (package / "annotations.json").write_text(
            json.dumps([record(2), record(1)]),
            encoding="utf-8",
        )
    registry_path.write_text(json.dumps(registry), encoding="utf-8")

    first = build_collection(tmp_path)
    first_bytes = first.read_bytes()
    second = build_collection(tmp_path)
    collection = json.loads(second.read_text())

    assert second.read_bytes() == first_bytes
    assert collection["document_count"] == 1
    assert collection["documents"][0]["source_path"] == "documents/a.pdf"
    assert [item["sentence_id"] for item in collection["documents"][0]["records"]] == [1, 2]


def test_invalid_done_package_does_not_replace_existing_collection(tmp_path: Path) -> None:
    sources = tmp_path / "documents"
    sources.mkdir()
    (sources / "source.pdf").write_bytes(b"source")
    sync_registry(tmp_path, source_dir="documents")
    registry_path = tmp_path / ".heva/project.json"
    registry = json.loads(registry_path.read_text())
    registry["documents"][0]["status"] = "done"
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    package = tmp_path / registry["documents"][0]["package_path"]
    (package / "annotations.json").write_text('[{"invalid": true}]', encoding="utf-8")
    collection_path = tmp_path / "exports/heva-collection.json"
    collection_path.parent.mkdir()
    collection_path.write_text('{"preserved": true}', encoding="utf-8")

    with pytest.raises(CollectionBuildError, match="invalid annotation"):
        build_collection(tmp_path)

    assert json.loads(collection_path.read_text()) == {"preserved": True}
