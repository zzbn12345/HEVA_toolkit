"""Benchmark matching PDF words to colored highlight drawings."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time

import fitz

from heva.extraction.pdf_extractor import VerticalRectIndex, find_highlight_color


def build_fixture(word_count: int, drawing_count: int):
    """Build deterministic word and drawing rectangles across a long page."""
    words = []
    for index in range(word_count):
        row, column = divmod(index, 10)
        x0 = 10.0 + column * 55.0
        y0 = 10.0 + row * 14.0
        words.append(fitz.Rect(x0, y0, x0 + 45.0, y0 + 10.0))

    drawings = []
    stride = max(1, word_count // drawing_count)
    for index in range(drawing_count):
        word_rect = words[min(index * stride, word_count - 1)]
        drawings.append({
            "rect": fitz.Rect(word_rect),
            "color": f"#{index % 256:02X}FF00",
        })
    return words, drawings


def match_naively(words, drawings):
    """Reproduce the extractor's former all-words-by-all-drawings loop."""
    matches = []
    for word_rect in words:
        highlight_color = None
        max_overlap = 0.0
        for drawing in drawings:
            overlap = (word_rect & drawing["rect"]).get_area()
            if overlap > max_overlap:
                max_overlap = overlap
                highlight_color = drawing["color"]
        if max_overlap < 0.1 * word_rect.get_area():
            highlight_color = None
        matches.append(highlight_color)
    return matches


def match_with_index(words, drawings):
    """Match using the production vertical rectangle index."""
    index = VerticalRectIndex(drawings)
    return [find_highlight_color(word, drawings, index) for word in words]


def main() -> None:
    """Measure the baseline matcher and checksum its selected colors."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--words", type=int, default=1_000)
    parser.add_argument("--drawings", type=int, default=100)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()

    words, drawings = build_fixture(args.words, args.drawings)
    results = {}
    for name, matcher in (("naive", match_naively), ("indexed", match_with_index)):
        durations = []
        checksums = set()
        for _ in range(args.repeats):
            started = time.perf_counter()
            matches = matcher(words, drawings)
            durations.append(time.perf_counter() - started)
            checksums.add(hashlib.sha256(json.dumps(matches).encode()).hexdigest())
        if len(checksums) != 1:
            raise RuntimeError(f"{name} highlight matching is not deterministic")
        results[name] = (statistics.median(durations), checksums.pop(), matches)

    if results["naive"][2] != results["indexed"][2]:
        raise RuntimeError("Indexed highlight matching changed selected colors")

    print(f"words={len(words)} drawings={len(drawings)} repeats={args.repeats}")
    print(f"naive_median_seconds={results['naive'][0]:.6f}")
    print(f"indexed_median_seconds={results['indexed'][0]:.6f}")
    print(f"speedup={results['naive'][0] / results['indexed'][0]:.2f}x")
    print(f"output_sha256={results['indexed'][1]}")


if __name__ == "__main__":
    main()
