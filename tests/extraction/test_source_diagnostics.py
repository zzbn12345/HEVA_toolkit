"""Acceptance tests for diagnostics offered after source extraction fails."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from heva.curation.extraction_draft import ExtractionDraftError, run_registered_raw_extraction
from heva.extraction.pdf_extractor import PDFTextExtractionError, extract_colored_highlights
from heva.curation.review_queue import list_review_queue


FIXTURE = Path(__file__).parents[1] / "fixtures/pdf/broken-type3-font.pdf"
EXAMPLE = Path(__file__).parents[2] / "examples/source-diagnostics-dummy-project"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_rejected_broken_unicode_pdf_offers_read_only_source_diagnostics() -> None:
    """Diagnose the known font-map failure without silently starting OCR or changing input."""

    from heva.extraction.source_diagnostics import diagnose_pdf_source

    source_sha256 = file_sha256(FIXTURE)
    with pytest.raises(PDFTextExtractionError) as failure:
        extract_colored_highlights(FIXTURE)

    report = diagnose_pdf_source(FIXTURE, trigger_code=failure.value.code)

    assert report.status == "assisted_extraction_recommended"
    assert report.trigger_code == "pdf_text_unreadable"
    assert report.source_sha256 == source_sha256
    assert report.affected_pages == [1, 2, 3, 4]
    assert "broken_unicode_mapping" in {issue.code for issue in report.issues}
    broken_mapping = next(
        issue for issue in report.issues if issue.code == "broken_unicode_mapping"
    )
    assert broken_mapping.evidence["font_type"] == "Type3"
    assert broken_mapping.evidence["has_to_unicode"] is False
    assert report.recommended_strategy == "ocr_span_alignment"
    assert report.assistance_started is False
    assert file_sha256(FIXTURE) == source_sha256


def test_source_diagnostics_example_is_prepared_up_to_extraction() -> None:
    """The manual fixture must isolate extraction as its first incomplete workflow gate."""

    [document] = list_review_queue(EXAMPLE)

    assert document.readiness_gates == {
        "curator": True,
        "original_annotator": True,
        "citation": True,
        "color_configuration": True,
        "extraction": False,
        "sentence_review": False,
    }
    assert document.blocking_reasons == [
        "Run extraction and persist a non-empty sentence inventory.",
        "Approve or exclude every extracted sentence.",
    ]

    metadata = json.loads(
        (
            EXAMPLE
            / "documents/HEVA-DEMO-BROKEN-FONT/metadata.json"
        ).read_text(encoding="utf-8")
    )
    assert {
        color["hex"]: color["label"]
        for color in metadata["color_configuration"]["colors"]
    } == {
        "#00D5FF": "aesthetical",
        "#A8D200": "ecological",
        "#D7AEFF": "economic",
        "#FF40FF": "historic",
        "#FFD300": "social",
        "#FFFC00": "political",
    }


def test_registered_broken_pdf_failure_remains_an_actionable_domain_error() -> None:
    """The unreadable source must not crash the job wrapper while handling its failure."""

    with pytest.raises(ExtractionDraftError) as failure:
        run_registered_raw_extraction(EXAMPLE, "HEVA-DEMO-BROKEN-FONT")

    assert failure.value.code == "pdf_text_unreadable"
    assert "searchable Unicode text or apply OCR" in str(failure.value)
