"""Benchmark matching PDF words to colored highlight drawings."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time

import fitz


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


def main() -> None:
    """Measure the baseline matcher and checksum its selected colors."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--words", type=int, default=1_000)
    parser.add_argument("--drawings", type=int, default=100)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()

    words, drawings = build_fixture(args.words, args.drawings)
    durations = []
    checksums = set()
    for _ in range(args.repeats):
        started = time.perf_counter()
        matches = match_naively(words, drawings)
        durations.append(time.perf_counter() - started)
        checksums.add(hashlib.sha256(json.dumps(matches).encode()).hexdigest())

    if len(checksums) != 1:
        raise RuntimeError("Highlight matching changed between repetitions")

    print(f"words={len(words)} drawings={len(drawings)} repeats={args.repeats}")
    print(f"median_seconds={statistics.median(durations):.6f}")
    print(f"output_sha256={checksums.pop()}")


if __name__ == "__main__":
    main()
