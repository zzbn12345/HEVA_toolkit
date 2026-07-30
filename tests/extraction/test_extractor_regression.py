"""Regression tests that generate their binary extraction inputs at runtime."""

from __future__ import annotations

from pathlib import Path

import docx
import fitz
from docx.shared import RGBColor

from heva.extraction.docx_extractor import extract_docx_highlights
from heva.extraction.pdf_extractor import extract_colored_highlights


def create_highlighted_pdf(path: Path) -> None:
    """Create a minimal PDF with a yellow drawing behind two words."""

    document = fitz.open()
    page = document.new_page()
    text = "Historic harbour remains protected."
    page.insert_text((100, 100), text, fontsize=12)
    highlighted = page.search_for("Historic harbour")[0]
    page.draw_rect(highlighted, fill=(1, 1, 0), color=None, overlay=False)
    document.save(path)
    document.close()


def create_colored_docx(path: Path) -> None:
    """Create a minimal Word document with two custom-colored phrases."""

    document = docx.Document()
    paragraph = document.add_paragraph()
    purple = paragraph.add_run("Historic harbour")
    purple.font.color.rgb = RGBColor(0x70, 0x30, 0xA0)
    paragraph.add_run(" remains ")
    green = paragraph.add_run("protected")
    green.font.color.rgb = RGBColor(0x92, 0xD0, 0x50)
    paragraph.add_run(".")
    document.save(path)


def test_pdf_extractor_reads_generated_highlight_and_mapping(tmp_path: Path) -> None:
    source = tmp_path / "highlighted.pdf"
    create_highlighted_pdf(source)

    raw = extract_colored_highlights(source)
    mapped = extract_colored_highlights(source, color_label_map={"#FFFF00": "historic"})

    assert raw[0]["sentence"] == "Historic harbour remains protected."
    assert raw[0]["entities"] == [
        {
            "start": 0,
            "end": 16,
            "text": "Historic harbour",
            "label": "#FFFF00",
            "color": "#FFFF00",
        }
    ]
    assert mapped[0]["entities"][0]["label"] == "historic"


def test_docx_extractor_reads_generated_custom_font_colors(tmp_path: Path) -> None:
    source = tmp_path / "colored.docx"
    create_colored_docx(source)

    actual = extract_docx_highlights(source)

    assert actual[0]["sentence"] == "Historic harbour remains protected."
    assert [entity["text"] for entity in actual[0]["entities"]] == [
        "Historic harbour",
        "protected",
    ]
    assert [entity["color"] for entity in actual[0]["entities"]] == [
        "#7030A0",
        "#92D050",
    ]


def test_docx_extractor_maps_each_generated_color(tmp_path: Path) -> None:
    source = tmp_path / "colored.docx"
    create_colored_docx(source)

    actual = extract_docx_highlights(
        source,
        color_label_map={"#7030A0": "historic", "#92D050": "social"},
    )

    assert actual[0]["values"] == ["historic", "social"]
    assert actual[0]["ner_tags"] == [
        "B-historic",
        "I-historic",
        "O",
        "B-social",
        "O",
    ]
