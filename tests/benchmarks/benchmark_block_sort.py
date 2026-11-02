"""Benchmark PDF page-block ordering on a deterministic dense layout."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time

import fitz

from heva.extraction.pdf_extractor import sort_page_blocks


def build_blocks(block_count: int):
    """Create repeatable headings and three-column blocks on one synthetic page."""
    blocks = []
    for index in range(block_count):
        row = index // 3
        column = index % 3
        if index % 75 == 0:
            x0, x1 = 20.0, 580.0
        else:
            x0 = 20.0 + column * 190.0
            x1 = x0 + 170.0
        y0 = 20.0 + row * 8.0
        blocks.append((x0, y0, x1, y0 + 6.0, f"block-{index}", index, 0))
    return blocks


def main() -> None:
    """Measure repeated block sorting and verify stable ordering and metadata."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--blocks", type=int, default=600)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()

    blocks = build_blocks(args.blocks)
    page_rect = fitz.Rect(0.0, 0.0, 600.0, 1800.0)
    durations = []
    checksums = set()
    for _ in range(args.repeats):
        started = time.perf_counter()
        ordered, metadata = sort_page_blocks(blocks, page_rect, rotation=0)
        durations.append(time.perf_counter() - started)
        payload = {
            "order": [block[5] for block in ordered],
            "metadata": sorted(metadata.items()),
        }
        checksums.add(
            hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        )

    if len(checksums) != 1:
        raise RuntimeError("Block sorting changed between repetitions")

    print(f"blocks={len(blocks)} repeats={args.repeats}")
    print(f"median_seconds={statistics.median(durations):.6f}")
    print(f"output_sha256={checksums.pop()}")


if __name__ == "__main__":
    main()
