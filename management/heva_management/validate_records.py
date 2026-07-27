"""Command-line validator for HEVA extracted records.

Usage examples:
- python -m management.heva_management.validate_records --file data/Galle_P127_extracted.json
- python -m management.heva_management.validate_records --all
- python -m management.heva_management.validate_records --glob "data/*_extracted.json"
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

from management.heva_management.contract import ContractParseError, load_records


def _iter_targets(file_path: str | None, all_files: bool, glob_pattern: str | None) -> list[Path]:
    if file_path:
        return [Path(file_path)]
    if glob_pattern:
        return sorted(Path().glob(glob_pattern))
    if all_files:
        return sorted(Path("data").glob("*_extracted.json"))
    return []


def _validate_one(path: Path, max_issues: int) -> tuple[bool, bool]:
    """Validate one file.

    Returns a tuple:
    - invalid_or_parse_error: True if file is invalid or malformed.
    - parse_error: True only when JSON parsing failed.
    """

    try:
        results = load_records(path)
    except ContractParseError as error:
        print(f"PARSE ERROR: {error}")
        return True, True
    except (OSError, UnicodeError) as error:
        print(f"INPUT ERROR: {path}: {error}")
        return True, True

    issues = [issue for result in results for issue in result.issues]
    if issues:
        print(f"INVALID: {path}: {len(results)} records, {len(issues)} issues")
        for issue in issues[:max_issues]:
            print(f"- {issue.code} {issue.path}: {issue.message}")
        if len(issues) > max_issues:
            print(f"... and {len(issues) - max_issues} more issues")
        return True, False

    print(f"VALID:   {path}: {len(results)} records, 0 issues")
    return False, False


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate HEVA extracted JSON records.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", help="Validate one JSON file.")
    group.add_argument("--all", action="store_true", help="Validate data/*_extracted.json.")
    group.add_argument("--glob", help='Validate files matching a glob pattern, e.g. "data/*_extracted.json".')
    parser.add_argument(
        "--max-issues",
        type=int,
        default=20,
        help="Maximum number of issues printed per file (default: 20).",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    targets = _iter_targets(args.file, args.all, args.glob)
    if not targets:
        print("No files matched the requested validation target.")
        return 1

    invalid = False
    parse_error = False
    for path in targets:
        failed, was_parse_error = _validate_one(path, max_issues=args.max_issues)
        invalid = invalid or failed
        parse_error = parse_error or was_parse_error

    if parse_error:
        return 2
    if invalid:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
