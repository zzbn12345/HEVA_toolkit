"""Acceptance tests for schema-validated programmatic citation entry."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from heva.workflow.citation_import import (
    CitationImportError,
    CitationImportRow,
    import_citation_csv,
    import_citation_row,
)
from heva.workflow.document_metadata import PackageMetadata, citation_is_valid
from heva.workflow.project_registry import sync_registry


def _project(tmp_path: Path, names: tuple[str, ...] = ("harbour.pdf",)) -> None:
    sources = tmp_path / "sources"
    sources.mkdir()
    for name in names:
        (sources / name).write_bytes(b"source")
    sync_registry(tmp_path, source_dir="sources")


def _row(filename: str = "harbour.pdf") -> dict[str, object]:
    return {
        "source_filename": filename,
        "title": "Historic harbour",
        "creators": "Doe, Jane; Example Institute",
        "item_type": "report",
        "issued_year": 2024,
        "undated": False,
        "citation": "Doe, Jane. Historic harbour. 2024.",
        "reference": "https://example.org/harbour",
    }


def test_programmatic_valid_citation_does_not_require_human_confirmation(tmp_path: Path) -> None:
    """Validated imports satisfy the citation gate with machine provenance."""

    _project(tmp_path)
    document_id = import_citation_row(tmp_path, _row(), validated_by="citation-import/1.0")
    registry = json.loads((tmp_path / ".heva/project.json").read_text())
    entry = next(item for item in registry["documents"] if item["document_id"] == document_id)
    metadata = PackageMetadata.model_validate_json(
        (tmp_path / entry["metadata_path"]).read_text()
    )

    assert citation_is_valid(metadata.source)
    assert metadata.source.human_confirmed is False
    assert metadata.source.validation_method == "programmatic"
    assert metadata.source.item_type == "report"
    assert metadata.source.source_filename == "harbour.pdf"
    assert metadata.source.creators == ["Doe, Jane", "Example Institute"]


def test_minimum_profile_requires_date_or_explicit_undated_state() -> None:
    """Unknown dates must be deliberate rather than blank spreadsheet accidents."""

    row = _row()
    row["issued_year"] = None

    with pytest.raises(ValueError, match="issued_year"):
        CitationImportRow.model_validate(row)


def test_filename_matching_is_exact_and_unambiguous(tmp_path: Path) -> None:
    """An import never guesses which similarly named document a row describes."""

    _project(tmp_path, ("harbour.pdf", "other.pdf"))

    with pytest.raises(CitationImportError, match="found 0"):
        import_citation_row(tmp_path, _row("Harbour.pdf"), validated_by="test")


def test_documented_csv_fixture_uses_the_same_validation_contract(tmp_path: Path) -> None:
    """The spreadsheet example remains an executable adapter acceptance fixture."""

    _project(tmp_path)
    fixture = Path(__file__).parents[1] / "fixtures/citations.csv"

    imported = import_citation_csv(tmp_path, fixture, validated_by="fixture-test/1.0")

    assert len(imported) == 1
