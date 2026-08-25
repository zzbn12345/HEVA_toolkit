"""Persist raw color extraction evidence before semantic labels are resolved."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Callable, Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from heva.extraction.errors import ExtractionCancelled
from heva.workflow.color_configuration_registry import selected_color_configuration
from heva.workflow.contract import CURRENT_SCHEMA_VERSION, HEX_COLOR, validate_record
from heva.workflow.people_registry import load_people_registry
from heva.workflow.project_registry import (
    DEFAULT_REGISTRY_PATH,
    ProjectRegistry,
    document_workspace_directory,
    require_current_document_source,
)


DRAFT_FILENAME = "extraction-draft.json"
RAW_BIO_TAG = re.compile(r"^(B|I)-(#[0-9A-Fa-f]{6})$")


class RawEntity(BaseModel):
    """One character span whose color is known but meaning remains unresolved."""

    model_config = ConfigDict(extra="forbid")

    start: int = Field(ge=0)
    end: int = Field(gt=0)
    text: str = Field(min_length=1)
    color: str = Field(pattern=r"^#[0-9A-F]{6}$")
    label: None = None
    mapping_status: str = Field(default="unresolved", pattern="^unresolved$")


class RawSentence(BaseModel):
    """One extracted sentence with raw hex BIO tags and unresolved entities."""

    model_config = ConfigDict(extra="forbid")

    sentence_id: int = Field(ge=1)
    page: int = Field(ge=1)
    sentence: str
    tokens: list[str]
    entities: list[RawEntity] = Field(min_length=1)
    ner_tags: list[str]

    @model_validator(mode="after")
    def validate_evidence(self) -> "RawSentence":
        """Ensure offsets, entity text, and raw BIO tags remain internally coherent."""

        if len(self.tokens) != len(self.ner_tags):
            raise ValueError("Raw token and BIO-tag counts must match.")
        for entity in self.entities:
            if entity.end <= entity.start or entity.end > len(self.sentence):
                raise ValueError("Raw entity offsets are outside the sentence.")
            if self.sentence[entity.start : entity.end] != entity.text:
                raise ValueError("Raw entity text does not match its sentence offsets.")
        for tag in self.ner_tags:
            if tag != "O" and RAW_BIO_TAG.fullmatch(tag) is None:
                raise ValueError("Raw BIO tags must contain a six-digit hex color.")
        return self


class ExtractionScope(BaseModel):
    """Record whether extraction covered the full source or selected PDF pages."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["full_source", "selected_pages"] = "full_source"
    selected_pages: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_scope(self) -> "ExtractionScope":
        """Require a sorted, unique, positive page list only for scoped runs."""

        if self.mode == "full_source" and self.selected_pages:
            raise ValueError("Full-source extraction cannot list selected pages.")
        if self.mode == "selected_pages" and (
            not self.selected_pages
            or self.selected_pages != sorted(set(self.selected_pages))
            or any(page < 1 for page in self.selected_pages)
        ):
            raise ValueError("Selected pages must be sorted, unique, positive integers.")
        return self


class ExtractionDraft(BaseModel):
    """Versionable workspace artifact containing extractor evidence, not HEVA labels."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    document_id: str
    source_checksum_sha256: str
    extractor: str
    extractor_version: str
    generated_by: str
    generated_at: datetime
    extraction_scope: ExtractionScope = Field(default_factory=ExtractionScope)
    sentences: list[RawSentence] = Field(min_length=1)


class ExtractionDraftError(ValueError):
    """Raised when raw evidence cannot safely be saved or resolved."""


def _registered_document(root: Path, document_id: str):
    """Return a present registry document or raise a user-facing draft error."""

    try:
        registry = ProjectRegistry.model_validate_json(
            (root / DEFAULT_REGISTRY_PATH).read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as error:
        raise ExtractionDraftError("The HEVA project registry cannot be read.") from error
    entry = next((item for item in registry.documents if item.document_id == document_id), None)
    if entry is None:
        raise ExtractionDraftError(f"Document {document_id} is not registered.")
    if entry.source_state != "present":
        raise ExtractionDraftError(
            f"Document {document_id} source state is {entry.source_state}; synchronize it first."
        )
    return entry


def _normalize_record(record: dict[str, Any]) -> RawSentence:
    """Remove accidental semantic fields and retain only reproducible raw evidence."""

    entities: list[dict[str, Any]] = []
    for entity in record.get("entities", []):
        color = str(entity.get("color") or entity.get("label") or "").upper()
        if HEX_COLOR.fullmatch(color) is None:
            raise ExtractionDraftError("Every raw entity must contain a six-digit hex color.")
        entities.append(
            {
                "start": entity.get("start"),
                "end": entity.get("end"),
                "text": entity.get("text"),
                "color": color,
                "label": None,
                "mapping_status": "unresolved",
            }
        )
    tags: list[str] = []
    for tag in record.get("ner_tags", []):
        if tag == "O":
            tags.append(tag)
            continue
        match = RAW_BIO_TAG.fullmatch(str(tag))
        if match is None:
            raise ExtractionDraftError("Raw extraction BIO tags must use hex colors, not labels.")
        tags.append(f"{match.group(1)}-{match.group(2).upper()}")
    try:
        return RawSentence(
            sentence_id=record.get("sentence_id"),
            page=record.get("page"),
            sentence=record.get("sentence"),
            tokens=record.get("tokens"),
            entities=entities,
            ner_tags=tags,
        )
    except ValidationError as error:
        raise ExtractionDraftError(f"Raw extraction evidence is invalid: {error}") from error


def persist_extraction_draft(
    project_root: str | Path,
    document_id: str,
    records: Sequence[dict[str, Any]],
    *,
    extractor: str,
    extractor_version: str,
    selected_pages: Sequence[int] | None = None,
) -> Path:
    """Atomically save unresolved evidence without touching canonical annotations."""

    root = Path(project_root).resolve()
    entry = _registered_document(root, document_id)
    curator = load_people_registry(root).active_curator()
    if curator is None:
        raise ExtractionDraftError("Select an active curator before saving extraction evidence.")
    if not records:
        raise ExtractionDraftError(
            "No colored annotations were found; the previous extraction draft was preserved."
        )
    draft = ExtractionDraft(
        document_id=document_id,
        source_checksum_sha256=entry.checksum_sha256,
        extractor=extractor,
        extractor_version=extractor_version,
        generated_by=curator.person_id,
        generated_at=datetime.now(timezone.utc),
        extraction_scope=ExtractionScope(
            mode="selected_pages" if selected_pages is not None else "full_source",
            selected_pages=sorted(selected_pages) if selected_pages is not None else [],
        ),
        sentences=[_normalize_record(record) for record in records],
    )
    path = document_workspace_directory(root, document_id) / DRAFT_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(draft.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def load_extraction_draft(project_root: str | Path, document_id: str) -> ExtractionDraft:
    """Load and validate one document's unresolved extraction draft."""

    path = document_workspace_directory(project_root, document_id) / DRAFT_FILENAME
    try:
        return ExtractionDraft.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as error:
        raise ExtractionDraftError(f"The extraction draft for {document_id} cannot be read.") from error


def synchronize_draft_colors(project_root: str | Path, document_id: str) -> bool:
    """Add newly observed raw hex values to the document's pending color review."""

    from heva.workflow.color_mapping import (
        load_color_configuration,
        propose_color_configuration,
        save_color_configuration,
    )

    root = Path(project_root).resolve()
    draft = load_extraction_draft(root, document_id)
    observed = {
        entity.color
        for sentence in draft.sentences
        for entity in sentence.entities
    }
    configuration = load_color_configuration(root, document_id)
    known = {color.hex for color in configuration.colors}
    missing = observed - known
    if not missing:
        return False
    additions = propose_color_configuration(missing)
    updated = configuration.model_copy(deep=True)
    updated.colors.extend(additions.colors)
    updated.colors.sort(key=lambda color: color.hex)
    updated.human_confirmed = False
    updated.confirmed_by = None
    updated.confirmed_at = None
    updated.use_for_extraction = False
    updated.extraction_authorized_by = None
    updated.extraction_authorized_at = None
    save_color_configuration(root, document_id, updated)
    return True


def compile_extraction_draft(
    project_root: str | Path,
    document_id: str,
) -> list[dict[str, Any]]:
    """Resolve a raw draft through the selected immutable project configuration."""

    root = Path(project_root).resolve()
    entry = _registered_document(root, document_id)
    draft = load_extraction_draft(root, document_id)
    if draft.source_checksum_sha256 != entry.checksum_sha256:
        raise ExtractionDraftError("The extraction draft is stale because the source changed.")
    configuration = selected_color_configuration(root)
    mapping = configuration.values
    observed = {entity.color for sentence in draft.sentences for entity in sentence.entities}
    missing = sorted(observed - mapping.keys())
    if missing:
        raise ExtractionDraftError(
            "The selected color configuration does not resolve: " + ", ".join(missing)
        )

    canonical: list[dict[str, Any]] = []
    for sentence in draft.sentences:
        entities = [
            {
                "start": entity.start,
                "end": entity.end,
                "text": entity.text,
                "label": mapping[entity.color],
                "color": entity.color,
            }
            for entity in sentence.entities
        ]
        tags = [
            tag
            if tag == "O"
            else f"{tag[0]}-{mapping[tag[2:].upper()]}"
            for tag in sentence.ner_tags
        ]
        record = {
            "schema_version": CURRENT_SCHEMA_VERSION,
            "sentence_id": sentence.sentence_id,
            "page": sentence.page,
            "sentence": sentence.sentence,
            "tokens": sentence.tokens,
            "values": sorted({entity["label"] for entity in entities}),
            "entities": entities,
            "ner_tags": tags,
            "mapping_provenance": {
                "method": "project_configuration",
                "status": "approved",
                "config_id": f"{configuration.configuration_id}@{configuration.version}",
            },
        }
        result = validate_record(record)
        if not result.valid or result.record is None:
            detail = "; ".join(f"{issue.path}: {issue.message}" for issue in result.issues)
            raise ExtractionDraftError(f"Resolved extraction violates the HEVA contract: {detail}")
        canonical.append(result.record.to_dict())
    return canonical


def run_registered_raw_extraction(
    project_root: str | Path,
    document_id: str,
    *,
    extractor: Callable[[Path], Sequence[dict[str, Any]]] | None = None,
    extractor_name: str | None = None,
    extractor_version: str = "0.1.0",
    progress_callback: Callable[[int, int], None] | None = None,
    cancellation_callback: Callable[[], bool] | None = None,
    selected_pages: Sequence[int] | None = None,
) -> Path:
    """Extract raw colors for a registered PDF or DOCX and persist the draft."""

    root = Path(project_root).resolve()
    entry = _registered_document(root, document_id)
    source = require_current_document_source(root, entry)
    if extractor is None:
        try:
            if source.suffix.lower() == ".pdf":
                from heva.extraction.pdf_extractor import extract_colored_highlights

                records = extract_colored_highlights(
                    source,
                    color_label_map=None,
                    progress_callback=progress_callback,
                    cancellation_callback=cancellation_callback,
                    page_numbers=selected_pages,
                )
                name = "HEVA PDF extractor"
            elif source.suffix.lower() == ".docx":
                if selected_pages is not None:
                    raise ExtractionDraftError(
                        "Page-scoped extraction is supported for PDF sources only."
                    )
                from heva.extraction.docx_extractor import extract_docx_highlights

                if cancellation_callback is not None and cancellation_callback():
                    from heva.extraction.errors import ExtractionCancelled

                    raise ExtractionCancelled("Extraction was cancelled before reading DOCX.")
                records = extract_docx_highlights(source, color_label_map=None)
                if progress_callback is not None:
                    progress_callback(1, 1)
                name = "HEVA DOCX extractor"
            else:
                raise ExtractionDraftError(
                    f"Unsupported source format: {source.suffix or '(none)'}"
                )
        except (ModuleNotFoundError, ExtractionCancelled):
            raise
        except ExtractionDraftError:
            raise
        except (OSError, RuntimeError, ValueError) as error:
            raise ExtractionDraftError(
                f"Raw color evidence could not be read from {source.name}: {error}"
            ) from error
    else:
        records = extractor(source)
        if progress_callback is not None:
            progress_callback(1, 1)
        name = extractor_name or getattr(extractor, "__name__", "custom extractor")
    if cancellation_callback is not None and cancellation_callback():
        from heva.extraction.errors import ExtractionCancelled

        raise ExtractionCancelled("Extraction was cancelled before saving raw evidence.")
    path = persist_extraction_draft(
        root,
        document_id,
        records,
        extractor=name,
        extractor_version=extractor_version,
        selected_pages=selected_pages,
    )
    synchronize_draft_colors(root, document_id)
    return path


def promote_extraction_draft(project_root: str | Path, document_id: str):
    """Persist a compiled draft as canonical annotations through existing safeguards."""

    root = Path(project_root).resolve()
    configuration = selected_color_configuration(root)
    from heva.workflow.color_configuration_registry import apply_selected_configuration_to_document
    from heva.workflow.extraction_session import persist_extraction_results

    apply_selected_configuration_to_document(root, document_id)
    draft = load_extraction_draft(root, document_id)
    records = compile_extraction_draft(root, document_id)
    return persist_extraction_results(
        root,
        document_id,
        records,
        extraction_method="automatic",
        extractor="HEVA unresolved-draft compiler",
        extractor_version="0.1.0",
        mapping_status="approved",
        selected_pages=(
            draft.extraction_scope.selected_pages
            if draft.extraction_scope.mode == "selected_pages"
            else None
        ),
    )
