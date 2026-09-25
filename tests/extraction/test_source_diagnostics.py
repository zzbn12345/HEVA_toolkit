"""Acceptance tests for diagnostics offered after source extraction fails."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import fitz
import pytest

from heva.curation.extraction_draft import ExtractionDraftError, run_registered_raw_extraction
from heva.extraction.pdf_extractor import PDFTextExtractionError, extract_colored_highlights
from heva.curation.review_queue import list_review_queue
from heva.extraction.ocr_assistance import _records_from_words


FIXTURE = Path(__file__).parents[1] / "fixtures/pdf/broken-type3-font.pdf"
EXAMPLE = Path(__file__).parents[2] / "examples/source-diagnostics-dummy-project"


def ignore_generated_example_state(directory: str, names: list[str]) -> set[str]:
    ignored = {"annotations.json"} & set(names)
    if Path(directory).name == ".heva":
        ignored |= {"documents"} & set(names)
    return ignored


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_ocr_groups_detected_table_cells_without_splitting_surrounding_prose() -> None:
    """Table cells are separate review units; ordinary prose retains paragraph grouping."""

    def word(text: str, x: int, y: int, number: int) -> dict:
        return {
            "text": text,
            "confidence": 95.0,
            "block": 1,
            "paragraph": 1,
            "line": 1,
            "word": number,
            "bbox": fitz.Rect(x, y, x + 35, y + 10),
        }

    words = [
        word("Quotation", 5, 5, 1),
        word("Argument", 105, 5, 2),
        word("Normal", 5, 40, 3),
        word("prose", 45, 40, 4),
    ]
    records = _records_from_words(
        words,
        page_number=1,
        colored_spans=[
            (fitz.Rect(5, 5, 40, 15), "#FFD300"),
            (fitz.Rect(5, 40, 40, 50), "#FFD300"),
        ],
        table_cells=[fitz.Rect(0, 0, 100, 20), fitz.Rect(100, 0, 200, 20)],
        first_sentence_id=1,
    )

    assert [record["sentence"] for record in records] == ["Quotation", "Normal prose"]


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


def test_source_diagnostics_example_is_prepared_up_to_extraction(tmp_path: Path) -> None:
    """The manual fixture must isolate extraction as its first incomplete workflow gate."""

    project = tmp_path / "source-diagnostics-dummy-project"
    shutil.copytree(
        EXAMPLE,
        project,
        ignore=ignore_generated_example_state,
    )
    [document] = list_review_queue(project)

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
            project
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
