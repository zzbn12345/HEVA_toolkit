"""Tests for the non-research synthetic large-PDF benchmark source."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from heva.extraction.pdf_extractor import extract_colored_highlights


GENERATOR = Path(__file__).parents[2] / "benchmarks" / "generate_large_pdf.py"
BENCHMARK = Path(__file__).parents[2] / "benchmarks" / "benchmark_extraction.py"


def _generator_module():
    specification = importlib.util.spec_from_file_location("large_pdf_generator", GENERATOR)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _benchmark_module():
    specification = importlib.util.spec_from_file_location("extraction_benchmark", BENCHMARK)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_synthetic_large_pdf_has_one_annotation_record_per_page(tmp_path: Path) -> None:
    """Keep the scaling fixture predictable without treating it as accuracy evidence."""

    source = _generator_module().generate_large_pdf(tmp_path / "large.pdf", pages=7)
    records = extract_colored_highlights(source)

    assert len(records) == 7
    assert [record["page"] for record in records] == list(range(1, 8))


def test_benchmark_reports_page_count_memory_and_stable_output(tmp_path: Path) -> None:
    """Performance evidence must state source scope and process-memory measurement."""

    source = _generator_module().generate_large_pdf(tmp_path / "large.pdf", pages=3)
    result = _benchmark_module().benchmark(source, repeats=2, warmups=0)

    assert result["source_pages"] == 3
    assert result["record_count"] == 3
    assert result["peak_process_rss_bytes"] > 0
    assert len(result["output_sha256"]) == 64
