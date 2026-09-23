"""Persist OCR-assisted evidence separately until a researcher reviews it."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Callable, Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from heva.curation.color_mapping import load_color_configuration
from heva.curation.extraction_draft import (
    ExtractionScope,
    RawSentence,
    _normalize_record,
    _registered_document,
    persist_extraction_draft,
    promote_extraction_draft,
)
from heva.curation.people_registry import load_people_registry
from heva.curation.project_registry import document_workspace_directory, require_current_document_source
from heva.extraction.ocr_assistance import OCRCandidateResult, extract_ocr_candidate


OCR_CANDIDATE_FILENAME = "ocr-candidate.json"


class OCRCandidateArtifact(BaseModel):
    """Review-required assisted output that is not canonical extraction evidence."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    document_id: str
    source_checksum_sha256: str
    status: Literal["pending_review", "promoted"] = "pending_review"
    requires_review: bool = True
    generated_by: str
    generated_at: datetime
    engine: str
    engine_version: str
    render_dpi: int
    mean_confidence: float
    processed_pages: list[int]
    extraction_scope: ExtractionScope = Field(default_factory=ExtractionScope)
    accepted_colors: list[str]
    sentences: list[RawSentence]
    promoted_by: str | None = None
    promoted_at: datetime | None = None


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_candidate(path: Path, artifact: OCRCandidateArtifact) -> None:
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(artifact.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def load_ocr_candidate(
    project_root: str | Path,
    document_id: str,
) -> OCRCandidateArtifact:
    """Load one pending or promoted candidate without treating it as annotations."""

    path = document_workspace_directory(project_root, document_id) / OCR_CANDIDATE_FILENAME
    try:
        return OCRCandidateArtifact.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as error:
        raise ValueError(f"The OCR candidate for {document_id} cannot be read.") from error


def run_registered_ocr_candidate(
    project_root: str | Path,
    document_id: str,
    *,
    page_numbers: Sequence[int] | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    cancellation_callback: Callable[[], bool] | None = None,
) -> tuple[Path, OCRCandidateArtifact]:
    """Create a separate OCR candidate without changing drafts or canonical annotations."""

    root = Path(project_root).resolve()
    entry = _registered_document(root, document_id)
    source = require_current_document_source(root, entry)
    curator = load_people_registry(root).active_curator()
    if curator is None:
        raise ValueError("Select an active curator before starting OCR assistance.")
    configuration = load_color_configuration(root, document_id)
    accepted_colors = sorted(
        color.hex for color in configuration.colors if color.status == "approved"
    )
    result: OCRCandidateResult = extract_ocr_candidate(
        source,
        accepted_colors=accepted_colors,
        page_numbers=page_numbers,
        progress_callback=progress_callback,
        cancellation_callback=cancellation_callback,
    )
    artifact = OCRCandidateArtifact(
        document_id=document_id,
        source_checksum_sha256=entry.checksum_sha256,
        status="pending_review",
        generated_by=curator.person_id,
        generated_at=datetime.now(timezone.utc),
        engine=result.engine,
        engine_version=result.engine_version,
        render_dpi=result.render_dpi,
        mean_confidence=result.mean_confidence,
        processed_pages=result.processed_pages,
        extraction_scope=ExtractionScope(
            mode="selected_pages" if page_numbers is not None else "full_source",
            selected_pages=sorted(page_numbers) if page_numbers is not None else [],
        ),
        accepted_colors=accepted_colors,
        sentences=[_normalize_record(record) for record in result.records],
    )
    path = document_workspace_directory(root, document_id) / OCR_CANDIDATE_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_candidate(path, artifact)
    return path, artifact


def promote_ocr_candidate(project_root: str | Path, document_id: str):
    """Explicitly promote a checksum-current candidate into the normal review workflow."""

    root = Path(project_root).resolve()
    entry = _registered_document(root, document_id)
    source = require_current_document_source(root, entry)
    candidate = load_ocr_candidate(root, document_id)
    if candidate.status != "pending_review":
        raise ValueError("This OCR candidate has already been used to create annotations.")
    if _checksum(source) != candidate.source_checksum_sha256:
        raise ValueError(
            "The source PDF changed after OCR; rerun diagnostics and assisted extraction."
        )
    curator = load_people_registry(root).active_curator()
    if curator is None:
        raise ValueError("Select an active curator before accepting OCR evidence.")
    records = [sentence.model_dump(mode="json") for sentence in candidate.sentences]
    selected_pages = (
        candidate.extraction_scope.selected_pages
        if candidate.extraction_scope.mode == "selected_pages"
        else None
    )
    persist_extraction_draft(
        root,
        document_id,
        records,
        extractor=f"{candidate.engine} OCR-assisted span alignment",
        extractor_version=candidate.engine_version,
        selected_pages=selected_pages,
    )
    result = promote_extraction_draft(root, document_id)
    candidate.status = "promoted"
    candidate.promoted_by = curator.person_id
    candidate.promoted_at = datetime.now(timezone.utc)
    path = document_workspace_directory(root, document_id) / OCR_CANDIDATE_FILENAME
    _write_candidate(path, candidate)
    return result, candidate
