"""Generate a synthetic multi-page annotated PDF for extraction scaling benchmarks."""

from __future__ import annotations

import argparse
from pathlib import Path

import fitz


def generate_large_pdf(output: Path, *, pages: int = 87) -> Path:
    """Write one searchable, highlighted sentence per page to a local benchmark PDF."""

    if pages < 1:
        raise ValueError("pages must be positive")
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    document = fitz.open()
    for page_number in range(1, pages + 1):
        page = document.new_page(width=595, height=842)
        sentence = (
            f"Historic harbour page {page_number} demonstrates a synthetic heritage annotation."
        )
        page.insert_text((72, 90), sentence, fontsize=12)
        rectangle = page.search_for("Historic harbour")[0]
        page.draw_rect(rectangle, fill=(1, 1, 0), color=None, overlay=False)
    document.set_metadata(
        {
            "title": f"Synthetic HEVA extraction benchmark ({pages} pages)",
            "author": "HEVA benchmark generator",
        }
    )
    document.save(output, garbage=4, deflate=True)
    document.close()
    return output


def main() -> int:
    """Create the requested synthetic scaling source without committing the PDF."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pages", type=int, default=87)
    arguments = parser.parse_args()
    target = generate_large_pdf(arguments.output, pages=arguments.pages)
    print(f"Synthetic {arguments.pages}-page benchmark written to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
