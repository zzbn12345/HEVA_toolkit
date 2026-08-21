"""Benchmark aligning DOCX run colors with token offsets."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
import tracemalloc

from heva.extraction.docx_extractor import RunColorIndex


COLORS = (None, "#7030A0", "#92D050")


def build_fixture(run_count: int, characters_per_run: int, token_width: int):
    """Create deterministic colored runs and fixed-width token intervals."""
    runs = [
        ("x" * characters_per_run, COLORS[index % len(COLORS)])
        for index in range(run_count)
    ]
    total_characters = run_count * characters_per_run
    tokens = [
        (start, min(start + token_width, total_characters))
        for start in range(0, total_characters, token_width)
    ]
    return runs, tokens


def align_with_characters(runs, tokens):
    """Reproduce expanding run colors to one value per character."""
    character_colors = []
    for text, color in runs:
        character_colors.extend([color] * len(text))

    token_colors = []
    for start, end in tokens:
        colors = [
            color for color in character_colors[start:end] if color is not None
        ]
        token_colors.append(max(set(colors), key=colors.count) if colors else None)
    return token_colors


def align_with_intervals(runs, tokens):
    """Align through the production compact run representation."""
    intervals = []
    cursor = 0
    for text, color in runs:
        intervals.append((cursor, cursor + len(text), color))
        cursor += len(text)
    return RunColorIndex(intervals).dominant_colors(tokens)


def measure(function, runs, tokens, repeats: int):
    """Return median runtime, peak traced memory, checksum, and output."""
    durations = []
    peaks = []
    checksums = set()
    output = None
    for _ in range(repeats):
        tracemalloc.start()
        started = time.perf_counter()
        output = function(runs, tokens)
        durations.append(time.perf_counter() - started)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peaks.append(peak)
        checksums.add(hashlib.sha256(json.dumps(output).encode()).hexdigest())
    if len(checksums) != 1:
        raise RuntimeError("DOCX color alignment changed between repetitions")
    return statistics.median(durations), max(peaks), checksums.pop(), output


def main() -> None:
    """Measure character-level color expansion and token alignment."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=2_000)
    parser.add_argument("--characters-per-run", type=int, default=100)
    parser.add_argument("--token-width", type=int, default=10)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()

    runs, tokens = build_fixture(
        args.runs, args.characters_per_run, args.token_width
    )
    character_seconds, character_peak, character_checksum, character_output = measure(
        align_with_characters, runs, tokens, args.repeats
    )
    interval_seconds, interval_peak, interval_checksum, interval_output = measure(
        align_with_intervals, runs, tokens, args.repeats
    )
    if character_output != interval_output:
        raise RuntimeError("Run intervals changed dominant token colors")

    print(
        f"runs={len(runs)} characters={args.runs * args.characters_per_run} "
        f"tokens={len(tokens)} repeats={args.repeats}"
    )
    print(f"character_median_seconds={character_seconds:.6f}")
    print(f"interval_median_seconds={interval_seconds:.6f}")
    print(f"speedup={character_seconds / interval_seconds:.2f}x")
    print(f"character_peak_bytes={character_peak}")
    print(f"interval_peak_bytes={interval_peak}")
    print(f"memory_reduction={character_peak / interval_peak:.2f}x")
    print(f"output_sha256={interval_checksum}")
    if character_checksum != interval_checksum:
        raise RuntimeError("Run intervals changed the output checksum")


if __name__ == "__main__":
    main()
