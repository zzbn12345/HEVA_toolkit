"""Benchmark aligning DOCX run colors with token offsets."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
import tracemalloc


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
    seconds, peak_bytes, checksum, _ = measure(
        align_with_characters, runs, tokens, args.repeats
    )

    print(
        f"runs={len(runs)} characters={args.runs * args.characters_per_run} "
        f"tokens={len(tokens)} repeats={args.repeats}"
    )
    print(f"median_seconds={seconds:.6f}")
    print(f"peak_bytes={peak_bytes}")
    print(f"output_sha256={checksum}")


if __name__ == "__main__":
    main()
