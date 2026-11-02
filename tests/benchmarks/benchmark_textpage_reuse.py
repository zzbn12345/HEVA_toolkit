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


def extract_with_shared_textpage(document):
    """Derive all three text views from one parsed representation per page."""
    result = []
    for page in document:
        text_page = page.get_textpage(flags=fitz.TEXTFLAGS_DICT)
        result.append(
            summarize_views(
                page.get_text("dict", textpage=text_page),
                page.get_text("words", textpage=text_page),
                page.get_text("blocks", textpage=text_page),
            )
        )
    return result


def main() -> None:
    """Measure independent text-page creation and checksum all derived views."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()

    document = fitz.open(args.source)
    results = {}
    try:
        for name, extractor in (
            ("fresh", extract_with_fresh_textpages),
            ("shared", extract_with_shared_textpage),
        ):
            durations = []
            checksums = set()
            for _ in range(args.repeats):
                started = time.perf_counter()
                result = extractor(document)
                durations.append(time.perf_counter() - started)
                checksums.add(
                    hashlib.sha256(
                        json.dumps(result, sort_keys=True).encode()
                    ).hexdigest()
                )
            if len(checksums) != 1:
                raise RuntimeError(f"{name} PDF text views are not deterministic")
            results[name] = (statistics.median(durations), checksums.pop(), result)
    finally:
        document.close()

    if results["fresh"][2] != results["shared"][2]:
        raise RuntimeError("Shared text pages changed the derived PDF views")

    print(f"source={args.source} repeats={args.repeats}")
    print(f"fresh_median_seconds={results['fresh'][0]:.6f}")
    print(f"shared_median_seconds={results['shared'][0]:.6f}")
    print(f"speedup={results['fresh'][0] / results['shared'][0]:.2f}x")
    print(f"output_sha256={results['shared'][1]}")


if __name__ == "__main__":
    main()
