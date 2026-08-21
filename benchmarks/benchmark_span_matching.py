"""Benchmark matching PDF words to text-color spans."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time

import fitz

from heva.extraction.pdf_extractor import VerticalRectIndex, find_text_span_color
from heva.extraction.tokenization import is_colorful


def build_fixture(item_count: int):
    """Create one ordered text span around each synthetic word."""
    words = []
    spans = []
    for index in range(item_count):
        row, column = divmod(index, 10)
        x0 = 10.0 + column * 55.0
        y0 = 10.0 + row * 14.0
        rect = fitz.Rect(x0, y0, x0 + 45.0, y0 + 10.0)
        words.append(rect)
        spans.append({
            "rect": fitz.Rect(rect),
            "color": "#7030A0" if index % 2 else "#000000",
        })
    return words, spans


def match_naively(words, spans):
    """Reproduce the extractor's former sequential span search."""
    matches = []
    for word_rect in words:
        center = fitz.Point(
            (word_rect.x0 + word_rect.x1) / 2,
            (word_rect.y0 + word_rect.y1) / 2,
        )
        color = None
        for span in spans:
            if center in span["rect"]:
                if is_colorful(span["color"]):
                    color = span["color"]
                break
        matches.append(color)
    return matches


def match_with_index(words, spans):
    """Match using the production vertical rectangle index."""
    index = VerticalRectIndex(spans)
    return [find_text_span_color(word, spans, index) for word in words]


def main() -> None:
    """Measure sequential span lookup and checksum selected colors."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--items", type=int, default=1_000)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()

    words, spans = build_fixture(args.items)
    results = {}
    for name, matcher in (("naive", match_naively), ("indexed", match_with_index)):
        durations = []
        checksums = set()
        for _ in range(args.repeats):
            started = time.perf_counter()
            matches = matcher(words, spans)
            durations.append(time.perf_counter() - started)
            checksums.add(hashlib.sha256(json.dumps(matches).encode()).hexdigest())
        if len(checksums) != 1:
            raise RuntimeError(f"{name} text-span matching is not deterministic")
        results[name] = (statistics.median(durations), checksums.pop(), matches)

    if results["naive"][2] != results["indexed"][2]:
        raise RuntimeError("Indexed text-span matching changed selected colors")

    print(f"words={len(words)} spans={len(spans)} repeats={args.repeats}")
    print(f"naive_median_seconds={results['naive'][0]:.6f}")
    print(f"indexed_median_seconds={results['indexed'][0]:.6f}")
    print(f"speedup={results['naive'][0] / results['indexed'][0]:.2f}x")
    print(f"output_sha256={results['indexed'][1]}")


if __name__ == "__main__":
    main()
