"""Read-only diagnostics for PDF sources rejected by normal extraction."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fitz


@dataclass(frozen=True)
class SourceDiagnosticIssue:
    """One source-level condition that can explain an extraction failure."""

    code: str
    pages: list[int]
    evidence: dict[str, Any]


@dataclass(frozen=True)
class SourceDiagnosticReport:
    """Evidence and next-step guidance produced without changing the source."""

    status: str
    trigger_code: str
    source_sha256: str
    affected_pages: list[int]
    issues: list[SourceDiagnosticIssue]
    recommended_strategy: str | None
    assistance_started: bool = False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _has_to_unicode(document: fitz.Document, xref: int) -> bool:
    value_type, value = document.xref_get_key(xref, "ToUnicode")
    return value_type != "null" and value not in {"null", ""}


def diagnose_pdf_source(
    source: str | Path,
    *,
    trigger_code: str,
) -> SourceDiagnosticReport:
    """Inspect PDF font metadata after rejection and recommend a safe next step.

    This function performs no OCR and writes neither the PDF nor project state. The
    caller must expose any assisted extraction as a separate, explicit action.
    """

    source_path = Path(source)
    source_sha256 = _sha256(source_path)
    affected_pages: list[int] = []
    broken_font_xrefs: set[int] = set()

    with fitz.open(source_path) as document:
        for page_number, page in enumerate(document, start=1):
            page_has_broken_mapping = False
            for font in page.get_fonts(full=True):
                xref, _, font_type = font[:3]
                if font_type == "Type3" and not _has_to_unicode(document, xref):
                    page_has_broken_mapping = True
                    broken_font_xrefs.add(xref)
            if page_has_broken_mapping:
                affected_pages.append(page_number)

    issues: list[SourceDiagnosticIssue] = []
    if affected_pages:
        issues.append(
            SourceDiagnosticIssue(
                code="broken_unicode_mapping",
                pages=affected_pages,
                evidence={
                    "font_type": "Type3",
                    "has_to_unicode": False,
                    "font_xrefs": sorted(broken_font_xrefs),
                },
            )
        )

    assisted_extraction_recommended = bool(issues)
    return SourceDiagnosticReport(
        status=(
            "assisted_extraction_recommended"
            if assisted_extraction_recommended
            else "no_known_source_issue"
        ),
        trigger_code=trigger_code,
        source_sha256=source_sha256,
        affected_pages=affected_pages,
        issues=issues,
        recommended_strategy=(
            "ocr_span_alignment" if assisted_extraction_recommended else None
        ),
    )
