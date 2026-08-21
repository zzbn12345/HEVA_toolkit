"""Benchmark deriving PDF text views from PyMuPDF text pages."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from pathlib import Path

import fitz


DEFAULT_SOURCE = Path("tests/2011 EC Galle part 1(Appendix IV) - Copy.pdf")


def summarize_views(text_dict, words, blocks):
    """Normalize relevant view content into a deterministic checksum payload."""
    span_text = []
    for block in text_dict["blocks"]:
        for line in block.get("lines", []):
            span_text.extend(span["text"] for span in line["spans"])
    return {
        "spans": span_text,
        "words": [list(word[4:]) for word in words],
        "blocks": [list(block[4:]) for block in blocks],
    }


def extract_with_fresh_textpages(document):
    """Reproduce three independent page text-view requests."""
    return [
        summarize_views(
            page.get_text("dict"),
            page.get_text("words"),
            page.get_text("blocks"),
        )
        for page in document
    ]


def main() -> None:
    """Measure independent text-page creation and checksum all derived views."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()

    document = fitz.open(args.source)
    durations = []
    checksums = set()
    try:
        for _ in range(args.repeats):
            started = time.perf_counter()
            result = extract_with_fresh_textpages(document)
            durations.append(time.perf_counter() - started)
            checksums.add(
                hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
            )
    finally:
        document.close()

    if len(checksums) != 1:
        raise RuntimeError("PDF text views changed between repetitions")

    print(f"source={args.source} repeats={args.repeats}")
    print(f"median_seconds={statistics.median(durations):.6f}")
    print(f"output_sha256={checksums.pop()}")


if __name__ == "__main__":
    main()
