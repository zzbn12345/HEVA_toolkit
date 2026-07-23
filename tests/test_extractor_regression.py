"""Golden pass-to-pass tests for the existing PDF and DOCX extractors."""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from docx_extractor import extract_docx_highlights  # noqa: E402
from pdf_extractor import extract_colored_highlights  # noqa: E402


def expected_records(filename: str) -> list[dict[str, object]]:
    """Load the committed golden output for an extraction sample."""

    return json.loads((ROOT / "data" / filename).read_text(encoding="utf-8"))


def legacy_document_mapping(filename: str) -> dict[str, str]:
    """Load a sample's historical mapping explicitly as regression evidence."""

    sidecar = json.loads((ROOT / "data" / filename).read_text(encoding="utf-8"))
    return {color: details["category"] for color, details in sidecar.items()}


def test_pdf_extractor_matches_committed_galle_records() -> None:
    actual = extract_colored_highlights(
        ROOT / "data" / "Galle_P127.pdf",
        color_label_map=legacy_document_mapping("Galle_P127_color_map.json"),
    )

    assert actual == expected_records("Galle_P127_extracted.json")


def test_docx_extractor_matches_committed_eop_records() -> None:
    actual = extract_docx_highlights(
        ROOT / "data" / "Deel_1_EOP_Chapter_4_Analysis_p2.docx",
        color_label_map=legacy_document_mapping(
            "Deel_1_EOP_Chapter_4_Analysis_p2_color_map.json"
        ),
    )

    assert actual == expected_records("Deel_1_EOP_Chapter_4_Analysis_p2_extracted.json")


def test_docx_without_mapping_preserves_its_custom_font_colors() -> None:
    actual = extract_docx_highlights(
        ROOT / "data" / "Deel_1_EOP_Chapter_4_Analysis_p2.docx"
    )
    labels = {
        entity["label"]
        for record in actual
        for entity in record["entities"]
    }

    assert labels == {"#7030A0", "#92D050", "#CCCC00", "#FF66CC", "#FFC000"}
