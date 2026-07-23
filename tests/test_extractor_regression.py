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


def mapping_from_aligned_records(
    raw_records: list[dict[str, object]],
    golden_records: list[dict[str, object]],
) -> dict[str, str]:
    """Recover a sample mapping without making legacy sidecars runtime fixtures."""

    mapping: dict[str, str] = {}
    assert len(raw_records) == len(golden_records)
    for raw_record, golden_record in zip(raw_records, golden_records, strict=True):
        assert raw_record["sentence"] == golden_record["sentence"]
        raw_entities = raw_record["entities"]
        golden_entities = golden_record["entities"]
        assert len(raw_entities) == len(golden_entities)
        for raw_entity, golden_entity in zip(raw_entities, golden_entities, strict=True):
            assert raw_entity["text"] == golden_entity["text"]
            assert raw_entity["start"] == golden_entity["start"]
            assert raw_entity["end"] == golden_entity["end"]
            color = raw_entity["label"]
            label = golden_entity["label"]
            assert color.startswith("#")
            if color in mapping:
                assert mapping[color] == label
            mapping[color] = label
    return mapping


def without_color_evidence(records: list[dict[str, object]]) -> list[dict[str, object]]:
    """Compare new records with legacy goldens without discarding runtime evidence."""

    comparable = json.loads(json.dumps(records))
    for record in comparable:
        for entity in record["entities"]:
            entity.pop("color", None)
    return comparable


def test_pdf_extractor_matches_committed_galle_records() -> None:
    source = ROOT / "data" / "Galle_P127.pdf"
    expected = expected_records("Galle_P127_extracted.json")
    raw = extract_colored_highlights(source)
    actual = extract_colored_highlights(
        source,
        color_label_map=mapping_from_aligned_records(raw, expected),
    )

    assert without_color_evidence(actual) == expected
    assert all(
        entity["color"].startswith("#")
        for record in actual
        for entity in record["entities"]
    )


def test_docx_extractor_matches_committed_eop_records() -> None:
    source = ROOT / "data" / "Deel_1_EOP_Chapter_4_Analysis_p2.docx"
    expected = expected_records("Deel_1_EOP_Chapter_4_Analysis_p2_extracted.json")
    raw = extract_docx_highlights(source)
    actual = extract_docx_highlights(
        source,
        color_label_map=mapping_from_aligned_records(raw, expected),
    )

    assert without_color_evidence(actual) == expected
    assert all(
        entity["color"].startswith("#")
        for record in actual
        for entity in record["entities"]
    )


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
