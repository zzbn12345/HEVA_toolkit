"""Reproducible wall-clock benchmark for HEVA PDF and DOCX extraction.

Run from the repository root with the extraction environment active::

    python benchmarks/benchmark_extraction.py --source path/to/annotated.pdf

The checksum makes performance comparisons reject accidental output changes.
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import platform
import resource
import statistics
import sys
import time
from typing import Callable


def _extractor(source: Path) -> Callable[[Path], list[dict[str, object]]]:
    """Select the supported extractor without including import time in measured runs."""

    if source.suffix.lower() == ".pdf":
        from heva.extraction.pdf_extractor import extract_colored_highlights

        return extract_colored_highlights
    if source.suffix.lower() == ".docx":
        from heva.extraction.docx_extractor import extract_docx_highlights

        return extract_docx_highlights
    raise ValueError("Benchmark source must be a PDF or DOCX file.")


def _checksum(records: list[dict[str, object]]) -> str:
    """Return a stable semantic-output checksum for regression comparison."""

    encoded = json.dumps(
        records,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _peak_process_rss_bytes() -> int:
    """Return the process peak resident set using the platform's documented unit."""

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(peak if sys.platform == "darwin" else peak * 1024)


def _page_count(source: Path) -> int | None:
    """Report PDF pages without adding page parsing to the measured extraction interval."""

    if source.suffix.lower() != ".pdf":
        return None
    import fitz

    with fitz.open(source) as document:
        return document.page_count


def benchmark(source: Path, *, repeats: int, warmups: int) -> dict[str, object]:
    """Measure extraction repeatedly and assert identical output across every run."""

    extractor = _extractor(source)
    for _ in range(warmups):
        with redirect_stdout(io.StringIO()):
            extractor(source)
    durations: list[float] = []
    checksums: list[str] = []
    records: list[dict[str, object]] = []
    for _ in range(repeats):
        started = time.perf_counter()
        with redirect_stdout(io.StringIO()):
            records = extractor(source)
        durations.append(time.perf_counter() - started)
        checksums.append(_checksum(records))
    if len(set(checksums)) != 1:
        raise RuntimeError("Extractor output changed between benchmark repetitions.")
    return {
        "source": source.as_posix(),
        "source_bytes": source.stat().st_size,
        "source_pages": _page_count(source),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "warmups": warmups,
        "repeats": repeats,
        "durations_seconds": durations,
        "median_seconds": statistics.median(durations),
        "mean_seconds": statistics.mean(durations),
        "min_seconds": min(durations),
        "max_seconds": max(durations),
        "peak_process_rss_bytes": _peak_process_rss_bytes(),
        "record_count": len(records),
        "output_sha256": checksums[0],
    }


def main() -> int:
    """Parse benchmark arguments and emit one machine-readable JSON result."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--warmups", type=int, default=1)
    args = parser.parse_args()
    if args.repeats < 1 or args.warmups < 0:
        parser.error("repeats must be positive and warmups cannot be negative")
    print(
        json.dumps(
            benchmark(args.source.resolve(), repeats=args.repeats, warmups=args.warmups),
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
