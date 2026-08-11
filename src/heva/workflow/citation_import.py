"""Validate structured citation rows and apply them to registered documents."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from heva.workflow.document_citation import CitationError, _context
from heva.workflow.document_metadata import SourceMetadata, save_package_metadata
from heva.workflow.project_registry import DEFAULT_REGISTRY_PATH, ProjectRegistry


class CitationImportRow(BaseModel):
    """Minimum citation profile for a findable, attributable source document."""

    model_config = ConfigDict(extra="forbid")

    source_filename: str = Field(min_length=1)
    title: str = Field(min_length=1)
    creators: list[str] = Field(min_length=1)
    item_type: Literal["article", "book", "chapter", "paper-conference", "report", "webpage"]
    issued_year: int | None = Field(default=None, ge=1000, le=9999)
    undated: bool = False
    citation: str = Field(min_length=1)
    reference: str | None = None
    not_findable_reason: str | None = None

    @field_validator("creators", mode="before")
    @classmethod
    def split_creators(cls, value: object) -> object:
        """Accept spreadsheet authors separated by semicolons."""

        if isinstance(value, str):
            return [item.strip() for item in value.split(";") if item.strip()]
        return value

    @model_validator(mode="after")
    def complete_citation(self) -> "CitationImportRow":
        """Require an issued year or explicit undated state and findability evidence."""

        if self.issued_year is None and not self.undated:
            raise ValueError("Provide issued_year or mark the source undated.")
        if self.issued_year is not None and self.undated:
            raise ValueError("A source cannot be both dated and undated.")
        if not self.reference and not self.not_findable_reason:
            raise ValueError("Provide a DOI/URL or a not-findable reason.")
        return self


class CitationImportError(CitationError):
    """Raised when imported citation rows are invalid or ambiguously matched."""


def import_citation_row(
    project_root: str | Path,
    row: CitationImportRow | dict[str, object],
    *,
    validated_by: str,
) -> str:
    """Apply one validated row by exact unique source filename and return its document ID."""

    root = Path(project_root).resolve()
    citation = CitationImportRow.model_validate(row)
    registry = ProjectRegistry.model_validate_json(
        (root / DEFAULT_REGISTRY_PATH).read_text(encoding="utf-8")
    )
    matches = [
        entry for entry in registry.documents
        if Path(entry.source_path).name == citation.source_filename
        or entry.source_path == citation.source_filename
    ]
    if len(matches) != 1:
        raise CitationImportError(
            f"Expected one exact source match for {citation.source_filename!r}; found {len(matches)}."
        )
    if not validated_by.strip():
        raise CitationImportError("Record the program or person responsible for validation.")
    _, _, metadata = _context(root, matches[0].document_id)
    metadata.source = SourceMetadata(
        title=citation.title,
        creators=citation.creators,
        citation=citation.citation,
        item_type=citation.item_type,
        issued_year=citation.issued_year,
        undated=citation.undated,
        source_filename=citation.source_filename,
        reference=citation.reference,
        not_findable_reason=citation.not_findable_reason,
        validation_method="programmatic",
        validated_by=validated_by.strip(),
        validated_at=datetime.now(timezone.utc),
    )
    save_package_metadata(root, metadata)
    return matches[0].document_id


def import_citation_csv(
    project_root: str | Path,
    csv_path: str | Path,
    *,
    validated_by: str,
) -> list[str]:
    """Import citation rows from a UTF-8 CSV using the same strict row contract."""

    with Path(csv_path).open(encoding="utf-8", newline="") as stream:
        rows = []
        for raw in csv.DictReader(stream):
            decoded = dict(raw)
            decoded["issued_year"] = int(raw["issued_year"]) if raw.get("issued_year") else None
            decoded["undated"] = str(raw.get("undated", "")).lower() in {"true", "1", "yes"}
            rows.append(CitationImportRow.model_validate(decoded))
    return [import_citation_row(project_root, row, validated_by=validated_by) for row in rows]
