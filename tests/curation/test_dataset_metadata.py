"""Tests for validated project-level release metadata persistence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from heva.curation.dataset_metadata import (
    DatasetMetadataError,
    load_dataset_metadata,
    save_dataset_metadata,
)
from heva.curation.package_validator import DatasetReleaseMetadata


def example_metadata() -> DatasetReleaseMetadata:
    """Return a minimal, explicit citable dataset description."""

    return DatasetReleaseMetadata(
        name="heritage-value-annotations",
        title="Heritage value annotations",
        description="Reviewed annotations for heritage-value research.",
        creators=["Research team"],
        contributors=["Example annotator"],
        license="CC-BY-4.0",
        rights="Only annotation derivatives are distributed.",
        known_limitations=["The sample is not representative of all heritage contexts."],
    )


def test_dataset_metadata_round_trips_as_stable_project_json(tmp_path: Path) -> None:
    saved = save_dataset_metadata(tmp_path, example_metadata())

    loaded = load_dataset_metadata(tmp_path)
    raw = json.loads((tmp_path / "dataset-metadata.json").read_text(encoding="utf-8"))

    assert loaded == saved
    assert raw["name"] == "heritage-value-annotations"
    assert not (tmp_path / "dataset-metadata.json.tmp").exists()


def test_invalid_existing_dataset_metadata_is_not_silently_replaced(tmp_path: Path) -> None:
    (tmp_path / "dataset-metadata.json").write_text('{"name":"broken"}', encoding="utf-8")

    with pytest.raises(DatasetMetadataError, match="Cannot load dataset metadata"):
        load_dataset_metadata(tmp_path)
