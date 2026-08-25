"""Command-line acceptance tests for the shared extraction adapters."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import fitz

from heva.extraction.pdf_extractor import extract_colored_highlights
from heva.extraction.extract_highlights import parse_page_numbers


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def create_highlighted_pdf(path: Path) -> None:
    """Create a searchable PDF containing a yellow highlighted phrase."""
    document = fitz.open()
    page = document.new_page()
    page.insert_text((100, 100), "Historic harbour remains visible.", fontsize=12)
    highlighted = page.search_for("Historic harbour")[0]
    page.draw_rect(highlighted, fill=(1, 1, 0), color=None, overlay=False)
    document.save(path)
    document.close()


def test_raw_extraction_runs_through_python_module_command(tmp_path: Path) -> None:
    """A shell caller can use the optimized extractor and an explicit color map."""
    source = tmp_path / "source.pdf"
    output = tmp_path / "annotations.json"
    mapping = tmp_path / "color-map.json"
    create_highlighted_pdf(source)
    mapping.write_text(json.dumps({"#FFFF00": "historic"}), encoding="utf-8")
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        filter(None, (str(REPOSITORY_ROOT / "src"), environment.get("PYTHONPATH")))
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "heva.extraction.extract_highlights",
            str(source),
            "--color-map",
            str(mapping),
            "--output",
            str(output),
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    records = json.loads(output.read_text(encoding="utf-8"))
    expected = extract_colored_highlights(
        source, color_label_map={"#FFFF00": "historic"}
    )
    assert records == expected
    assert records[0]["entities"][0]["label"] == "historic"
    assert records[0]["entities"][0]["color"] == "#FFFF00"
    assert "1 records" in completed.stdout
    assert "source.pdf: page 1/1" in completed.stderr


def test_cli_page_selection_parser_supports_ranges_and_lists() -> None:
    assert parse_page_numbers("1,3,7-9") == [1, 3, 7, 8, 9]
    assert parse_page_numbers(None) is None
