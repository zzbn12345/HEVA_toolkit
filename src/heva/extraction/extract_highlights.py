"""Command-line interoperability adapter for raw HEVA extraction."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Iterable
from pathlib import Path

from heva.extraction.docx_extractor import extract_docx_highlights
from heva.extraction.pdf_extractor import extract_colored_highlights


SUPPORTED_SUFFIXES = {".pdf", ".docx"}


def discover_sources(inputs: Iterable[Path]) -> list[Path]:
    """Return supported files from explicit files or immediate directories."""
    discovered: dict[Path, None] = {}
    for supplied in inputs:
        path = supplied.expanduser().resolve()
        candidates = path.iterdir() if path.is_dir() else (path,)
        for candidate in candidates:
            if (
                candidate.is_file()
                and candidate.suffix.lower() in SUPPORTED_SUFFIXES
                and not candidate.name.startswith("~$")
            ):
                discovered[candidate.resolve()] = None
    return sorted(discovered, key=lambda path: str(path).lower())


def load_color_map(path: Path | None) -> dict[str, str] | None:
    """Load a flat hexadecimal-color-to-label JSON object."""
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not all(
        isinstance(color, str) and isinstance(label, str)
        for color, label in payload.items()
    ):
        raise ValueError("Color map must be a JSON object of string colors and labels.")
    return payload


def extract_source(
    source: Path,
    color_map: dict[str, str] | None,
    progress_callback: Callable[[int, int], None] | None = None,
    page_numbers: list[int] | None = None,
):
    """Run the shared adapter and optionally report completed source units."""
    if source.suffix.lower() == ".pdf":
        return extract_colored_highlights(
            source,
            color_label_map=color_map,
            progress_callback=progress_callback,
            page_numbers=page_numbers,
        )
    if source.suffix.lower() == ".docx":
        if page_numbers is not None:
            raise ValueError("--pages is supported for PDF sources only.")
        return extract_docx_highlights(source, color_label_map=color_map)
    raise ValueError(f"Unsupported source format: {source.suffix or '(none)'}")


def output_path_for(
    source: Path,
    *,
    explicit_output: Path | None,
    output_directory: Path | None,
) -> Path:
    """Resolve a deterministic JSON output path for one source."""
    if explicit_output is not None:
        return explicit_output.expanduser().resolve()
    filename = f"{source.stem}_extracted.json"
    if output_directory is not None:
        return output_directory.expanduser().resolve() / filename
    return source.with_name(filename)


def build_parser() -> argparse.ArgumentParser:
    """Build the raw extraction command-line parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Extract colored HEVA evidence from PDF or DOCX files using the same "
            "optimized adapters as the web application."
        )
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        type=Path,
        help="One or more PDF/DOCX files or folders containing them.",
    )
    destination = parser.add_mutually_exclusive_group()
    destination.add_argument(
        "-o", "--output", type=Path, help="Output JSON path for one input file."
    )
    destination.add_argument(
        "--output-dir", type=Path, help="Directory for one or more JSON outputs."
    )
    parser.add_argument(
        "--color-map",
        type=Path,
        help='Flat JSON mapping such as {"#FFFF00": "political"}.',
    )
    parser.add_argument(
        "--pages",
        help="PDF pages such as 1-10 or 1,3,7-9. Omit to analyze the full source.",
    )
    return parser


def parse_page_numbers(value: str | None) -> list[int] | None:
    """Parse inclusive one-based PDF pages from comma-separated values and ranges."""

    if value is None:
        return None
    pages: set[int] = set()
    try:
        for part in value.split(","):
            item = part.strip()
            if not item:
                raise ValueError
            if "-" in item:
                start_text, end_text = item.split("-", 1)
                start, end = int(start_text), int(end_text)
                if start < 1 or end < start:
                    raise ValueError
                pages.update(range(start, end + 1))
            else:
                page = int(item)
                if page < 1:
                    raise ValueError
                pages.add(page)
    except ValueError as error:
        raise ValueError(
            "Pages must use positive one-based values such as 1-10 or 1,3,7-9."
        ) from error
    if not pages:
        raise ValueError("Select at least one PDF page.")
    return sorted(pages)


def main(argv: Iterable[str] | None = None) -> int:
    """Extract every selected source and return a process-style status code."""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    sources = discover_sources(args.inputs)
    if not sources:
        parser.error("No supported PDF or DOCX files were found.")
    if args.output is not None and len(sources) != 1:
        parser.error("--output can only be used when exactly one source is selected.")

    try:
        color_map = load_color_map(args.color_map)
        page_numbers = parse_page_numbers(args.pages)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        parser.error(str(error))

    if args.output_dir is not None:
        args.output_dir.expanduser().resolve().mkdir(parents=True, exist_ok=True)

    failed = False
    for source in sources:
        try:
            records = extract_source(
                source,
                color_map,
                page_numbers=page_numbers,
                progress_callback=lambda completed, total: print(
                    f"{source.name}: page {completed}/{total}",
                    file=sys.stderr,
                ),
            )
            destination = output_path_for(
                source,
                explicit_output=args.output,
                output_directory=args.output_dir,
            )
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(
                json.dumps(records, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            print(f"{source.name}: {len(records)} records -> {destination}")
        except Exception as error:
            failed = True
            print(f"{source.name}: ERROR {error}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
