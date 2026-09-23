"""Validated, citable metadata for one generated HEVA dataset release."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from heva.curation.package_validator import (
    DEFAULT_DATASET_METADATA_PATH,
    DatasetReleaseMetadata,
)


class DatasetMetadataError(ValueError):
    """Raised when dataset metadata cannot be read or persisted safely."""


def load_dataset_metadata(
    project_root: str | Path,
) -> DatasetReleaseMetadata | None:
    """Load validated release metadata, returning ``None`` before first creation."""

    path = Path(project_root).resolve() / DEFAULT_DATASET_METADATA_PATH
    if not path.exists():
        return None
    try:
        return DatasetReleaseMetadata.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as error:
        raise DatasetMetadataError(f"Cannot load dataset metadata: {error}") from error


def save_dataset_metadata(
    project_root: str | Path,
    metadata: DatasetReleaseMetadata,
) -> DatasetReleaseMetadata:
    """Atomically persist schema-validated metadata at the project root."""

    path = Path(project_root).resolve() / DEFAULT_DATASET_METADATA_PATH
    temporary = path.with_suffix(".json.tmp")
    try:
        temporary.write_text(
            json.dumps(
                metadata.model_dump(mode="json"),
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    except OSError as error:
        raise DatasetMetadataError(f"Cannot save dataset metadata: {error}") from error
    return metadata
