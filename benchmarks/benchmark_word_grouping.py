"""Benchmark grouping reconstructed PDF words by text block."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time

from heva.extraction.pdf_extractor import group_words_by_block


def build_fixture(block_count: int, words_per_block: int):
    """Create deterministic words ordered by block, line, and word number."""
    words = []
    for block_number in range(block_count):
        for word_number in range(words_per_block):
            words.append({
                "text": f"b{block_number}-w{word_number}",
                "block_no": block_number,
                "line_no": word_number // 10,
                "word_no": word_number,
            })
    return words


def group_repeatedly(words, block_numbers):
    """Reproduce filtering the complete word list for every block."""
    return {
        block_number: [
            word["text"] for word in words if word["block_no"] == block_number
        ]
        for block_number in block_numbers
    }


def group_once(words, block_numbers):
    """Use the production single-pass grouping implementation."""
    grouped = group_words_by_block(words)
    return {
        block_number: [word["text"] for word in grouped.get(block_number, [])]
        for block_number in block_numbers
    }


def main() -> None:
    """Measure repeated grouping and checksum word order within every block."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--blocks", type=int, default=500)
    parser.add_argument("--words-per-block", type=int, default=20)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()

    words = build_fixture(args.blocks, args.words_per_block)
    block_numbers = list(range(args.blocks))
    results = {}
    for name, grouper in (("repeated", group_repeatedly), ("single_pass", group_once)):
        durations = []
        checksums = set()
        for _ in range(args.repeats):
            started = time.perf_counter()
            grouped = grouper(words, block_numbers)
            durations.append(time.perf_counter() - started)
            checksums.add(
                hashlib.sha256(json.dumps(grouped, sort_keys=True).encode()).hexdigest()
            )
        if len(checksums) != 1:
            raise RuntimeError(f"{name} word grouping is not deterministic")
        results[name] = (statistics.median(durations), checksums.pop(), grouped)

    if results["repeated"][2] != results["single_pass"][2]:
        raise RuntimeError("Single-pass grouping changed block word order")

    print(f"blocks={args.blocks} words={len(words)} repeats={args.repeats}")
    print(f"repeated_median_seconds={results['repeated'][0]:.6f}")
    print(f"single_pass_median_seconds={results['single_pass'][0]:.6f}")
    print(f"speedup={results['repeated'][0] / results['single_pass'][0]:.2f}x")
    print(f"output_sha256={results['single_pass'][1]}")


if __name__ == "__main__":
    main()
