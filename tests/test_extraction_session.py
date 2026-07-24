"""Acceptance tests for persisting one registered document extraction."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.color_mapping import (
    confirm_color_configuration,
    propose_color_configuration,
    resolve_color,
    save_color_configuration,
)
from src.extraction_session import ExtractionValidationError, persist_extraction_results
from src.project_registry import sync_registry


def record() -> dict[str, object]:
    return {
        "sentence_id": 1,
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
        "mapping_provenance": {
            "method": "human_reviewed", "status": "approved", "config_id": "test-map",
        },
    }


def project(tmp_path: Path) -> str:
    sources = tmp_path / "documents"
    sources.mkdir()
    (sources / "source.pdf").write_bytes(b"source")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / "data/project-registry.json").read_text())
    document_id = registry["documents"][0]["document_id"]
    config = propose_color_configuration(
        ["#FF40FF"], legend_mapping={"#FF40FF": "historic"}
    )
    config = resolve_color(config, "#FF40FF", label="historic")
    config = confirm_color_configuration(config, confirmed_by="Annotator")
    save_color_configuration(tmp_path, document_id, config)
    return document_id


def test_valid_results_enter_registered_package_with_provenance(tmp_path: Path) -> None:
    document_id = project(tmp_path)

    result = persist_extraction_results(
        tmp_path, document_id, [record()],
        extraction_method="automatic", extractor="HEVA PDF extractor",
        extractor_version="0.1.0",
    )

    assert json.loads(result.annotations_path.read_text())[0]["entities"][0]["color"] == "#FF40FF"
    metadata = json.loads((result.annotations_path.parent / "package-metadata.json").read_text())
    assert metadata["resources"][0]["record_count"] == 1
    assert metadata["annotation_process"]["extractor_version"] == "0.1.0"
    registry = json.loads((tmp_path / "data/project-registry.json").read_text())
    assert registry["documents"][0]["status"] == "in_progress"


def test_invalid_results_do_not_replace_existing_annotations(tmp_path: Path) -> None:
    document_id = project(tmp_path)
    package = tmp_path / "data/packages" / document_id
    annotations = package / "annotations.json"
    annotations.write_text('[{"preserved": true}]', encoding="utf-8")
    invalid = record()
    invalid["ner_tags"] = ["O"]

    with pytest.raises(ExtractionValidationError):
        persist_extraction_results(
            tmp_path, document_id, [invalid],
            extraction_method="automatic", extractor="test", extractor_version="1",
        )

    assert json.loads(annotations.read_text()) == [{"preserved": True}]
