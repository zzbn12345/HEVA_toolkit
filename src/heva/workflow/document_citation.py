"""Document citation proposals, edits, and explicit human confirmation."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile
import xml.etree.ElementTree as ET

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from heva.workflow.document_metadata import (
    MetadataError,
    PackageMetadata,
    SourceMetadata,
    save_package_metadata,
)
from heva.workflow.project_registry import DEFAULT_REGISTRY_PATH, ProjectRegistry


class CitationDraft(BaseModel):
    """Editable citation fields; completeness is enforced only at confirmation."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, title="Document title")
    creators: list[str] = Field(
        default_factory=list,
        title="Source authors",
        description="One source author or creator per entry.",
    )
    citation: str | None = Field(
        default=None,
        title="Citation",
        description="Human-readable citation for this source.",
    )
    reference: str | None = Field(
        default=None,
        title="DOI or public URL",
        description="Persistent identifier or public location when available.",
    )
    not_findable_reason: str | None = Field(
        default=None,
        title="Why the source is not publicly findable",
    )


class CitationRecord(BaseModel):
    """Citation data plus proposal and confirmation evidence for the interface."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    data: CitationDraft
    human_confirmed: bool
    confirmed_by: str | None
    confirmed_at: datetime | None
    proposal_method: str | None = None
    proposed_fields: list[str] = Field(default_factory=list)


class CitationError(ValueError):
    """Raised when citation state cannot be loaded, saved, or confirmed."""


def _context(project_root: str | Path, document_id: str):
    root = Path(project_root).resolve()
    try:
        registry = ProjectRegistry.model_validate_json(
            (root / DEFAULT_REGISTRY_PATH).read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as error:
        raise CitationError("The project registry cannot be read.") from error
    entry = next(
        (item for item in registry.documents if item.document_id == document_id),
        None,
    )
    if entry is None:
        raise CitationError("The selected document is not registered.")
    try:
        metadata = PackageMetadata.model_validate_json(
            (root / (entry.metadata_path or f"{entry.package_path}/metadata.json")).read_text(
                encoding="utf-8"
            )
        )
    except (OSError, ValidationError) as error:
        raise CitationError("The document package metadata cannot be read.") from error
    return root, entry, metadata


def _docx_properties(path: Path) -> tuple[str | None, list[str]]:
    try:
        with ZipFile(path) as archive:
            xml = archive.read("docProps/core.xml")
    except (OSError, KeyError, BadZipFile):
        return None, []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return None, []
    namespaces = {
        "dc": "http://purl.org/dc/elements/1.1/",
    }
    title = root.findtext("dc:title", namespaces=namespaces)
    creator = root.findtext("dc:creator", namespaces=namespaces)
    return (
        title.strip() if title and title.strip() else None,
        [creator.strip()] if creator and creator.strip() else [],
    )


def _pdf_properties(path: Path) -> tuple[str | None, list[str]]:
    try:
        import fitz
    except ImportError:
        return None, []
    try:
        with fitz.open(path) as document:
            properties: dict[str, Any] = document.metadata or {}
    except (OSError, RuntimeError, ValueError):
        return None, []
    title = properties.get("title")
    author = properties.get("author")
    creators = [
        item.strip()
        for item in str(author or "").replace(";", ",").split(",")
        if item.strip()
    ]
    return (
        str(title).strip() if title and str(title).strip() else None,
        creators,
    )


def propose_document_citation(source_path: str | Path) -> tuple[CitationDraft, str]:
    """Read embedded source properties and fall back to a readable filename."""

    source = Path(source_path)
    if source.suffix.lower() == ".docx":
        title, creators = _docx_properties(source)
        method = "DOCX core properties"
    elif source.suffix.lower() == ".pdf":
        title, creators = _pdf_properties(source)
        method = "PDF document properties"
    else:
        title, creators = None, []
        method = "source filename"
    if not title:
        title = source.stem.replace("_", " ").strip()
        method = f"{method} and source filename"
    citation = f"{'; '.join(creators)}. {title}." if creators else None
    return CitationDraft(title=title, creators=creators, citation=citation), method


def load_document_citation(
    project_root: str | Path,
    document_id: str,
) -> CitationRecord:
    """Load persisted citation data, filling only blank fields with proposals."""

    root, entry, metadata = _context(project_root, document_id)
    source = metadata.source
    data = CitationDraft(
        title=source.title,
        creators=source.creators,
        citation=source.citation,
        reference=source.reference,
        not_findable_reason=source.not_findable_reason,
    )
    proposal_method = None
    proposed_fields: list[str] = []
    if not source.human_confirmed:
        proposal, proposal_method = propose_document_citation(root / entry.source_path)
        updates = data.model_dump()
        for field in ("title", "creators", "citation"):
            if not updates[field] and getattr(proposal, field):
                updates[field] = getattr(proposal, field)
                proposed_fields.append(field)
        data = CitationDraft.model_validate(updates)
    return CitationRecord(
        document_id=document_id,
        data=data,
        human_confirmed=source.human_confirmed,
        confirmed_by=source.confirmed_by,
        confirmed_at=source.confirmed_at,
        proposal_method=proposal_method if proposed_fields else None,
        proposed_fields=proposed_fields,
    )


def save_document_citation(
    project_root: str | Path,
    document_id: str,
    draft: CitationDraft,
) -> CitationRecord:
    """Save a draft and reset confirmation because a human decision is pending."""

    _, _, metadata = _context(project_root, document_id)
    metadata.source = SourceMetadata(
        **draft.model_dump(),
        human_confirmed=False,
        confirmed_by=None,
        confirmed_at=None,
    )
    try:
        save_package_metadata(project_root, metadata)
    except MetadataError as error:
        raise CitationError(str(error)) from error
    return load_document_citation(project_root, document_id)


def confirm_document_citation(
    project_root: str | Path,
    document_id: str,
    draft: CitationDraft,
    *,
    confirmed_by: str,
) -> CitationRecord:
    """Persist citation values only after all required evidence is present."""

    if not draft.title:
        raise CitationError("Enter the document title.")
    if not draft.creators:
        raise CitationError("Add at least one source author or creator.")
    if not draft.citation:
        raise CitationError("Enter a human-readable citation.")
    if not draft.reference and not draft.not_findable_reason:
        raise CitationError(
            "Provide a DOI/public URL or explain why the source is not findable."
        )
    if not confirmed_by.strip():
        raise CitationError("Select an active project annotator before confirmation.")
    _, _, metadata = _context(project_root, document_id)
    metadata.source = SourceMetadata(
        **draft.model_dump(),
        human_confirmed=True,
        confirmed_by=confirmed_by.strip(),
        confirmed_at=datetime.now(timezone.utc),
    )
    try:
        save_package_metadata(project_root, metadata)
    except MetadataError as error:
        raise CitationError(str(error)) from error
    return load_document_citation(project_root, document_id)
