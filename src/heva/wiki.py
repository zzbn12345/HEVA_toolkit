"""Build deterministic GitHub Wiki pages from HEVA's canonical Markdown docs."""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path, PurePosixPath
from typing import Iterable


MARKDOWN_LINK = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)")


def page_slug(relative_path: PurePosixPath) -> str:
    """Return a flat, URL-safe Wiki page name for one documentation path."""

    if relative_path.as_posix() == "index.md":
        return "Home"
    parts = list(relative_path.with_suffix("").parts)
    if parts and parts[0] in {"guides", "reference"}:
        parts[0] = parts[0].title()
    words = "-".join(parts).replace("_", "-").split("-")
    return "-".join(word.title() for word in words if word)


def discover_pages(docs_root: Path) -> dict[PurePosixPath, str]:
    """Discover Markdown sources and reject ambiguous Wiki page names."""

    pages: dict[PurePosixPath, str] = {}
    seen: dict[str, PurePosixPath] = {}
    for source in sorted(docs_root.rglob("*.md")):
        relative = PurePosixPath(source.relative_to(docs_root).as_posix())
        slug = page_slug(relative)
        if slug in seen:
            raise ValueError(f"Wiki slug {slug!r} is shared by {seen[slug]} and {relative}.")
        pages[relative] = slug
        seen[slug] = relative
    return pages


def rewrite_links(
    markdown: str,
    source_path: PurePosixPath,
    pages: dict[PurePosixPath, str],
) -> str:
    """Rewrite links between source docs to their generated flat Wiki pages."""

    def replace(match: re.Match[str]) -> str:
        label, destination = match.groups()
        if destination.startswith(("http://", "https://", "mailto:", "#")):
            return match.group(0)
        target, separator, anchor = destination.partition("#")
        if not target.endswith(".md"):
            return match.group(0)
        resolved = _normalize_path(source_path.parent / target)
        slug = pages.get(resolved)
        if slug is None:
            return match.group(0)
        suffix = f"#{anchor}" if separator else ""
        return f"[{label}]({slug}{suffix})"

    return MARKDOWN_LINK.sub(replace, markdown)


def _normalize_path(path: PurePosixPath) -> PurePosixPath:
    """Normalize dot segments without resolving against the host filesystem."""

    parts: list[str] = []
    for part in path.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return PurePosixPath(*parts)


def build_wiki(docs_root: str | Path, output_directory: str | Path) -> list[Path]:
    """Build all Wiki pages, navigation, and provenance into a clean directory."""

    source_root = Path(docs_root).resolve()
    output = Path(output_directory).resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    pages = discover_pages(source_root)
    written: list[Path] = []
    for relative, slug in pages.items():
        source = source_root / Path(relative.as_posix())
        content = rewrite_links(source.read_text(encoding="utf-8"), relative, pages)
        destination = output / f"{slug}.md"
        destination.write_text(content.rstrip() + "\n", encoding="utf-8")
        written.append(destination)
    sidebar = output / "_Sidebar.md"
    sidebar.write_text(_sidebar(pages), encoding="utf-8")
    footer = output / "_Footer.md"
    footer.write_text(
        "Generated from the private `heva-toolkit` repository. Edit `docs/`, not the Wiki.\n",
        encoding="utf-8",
    )
    return [*written, sidebar, footer]


def _sidebar(pages: dict[PurePosixPath, str]) -> str:
    """Create compact Wiki navigation grouped by documentation purpose."""

    groups = {"Start": [], "Guides": [], "Reference": [], "Concepts": []}
    for path, slug in pages.items():
        if path.as_posix() in {"index.md", "quickstart.md"}:
            group = "Start"
        elif path.parts[0] == "guides":
            group = "Guides"
        elif path.parts[0] == "reference":
            group = "Reference"
        else:
            group = "Concepts"
        title = _page_title(path, slug)
        groups[group].append((title, slug))
    lines: list[str] = []
    for group, entries in groups.items():
        lines.extend((f"### {group}", ""))
        lines.extend(f"- [{title}]({slug})" for title, slug in sorted(entries))
        lines.append("")
    return "\n".join(lines)


def _page_title(path: PurePosixPath, fallback: str) -> str:
    """Return the canonical home title or a readable page slug."""

    return "HEVA Toolkit documentation" if path.as_posix() == "index.md" else fallback.replace("-", " ")


def main(argv: Iterable[str] | None = None) -> int:
    """Build GitHub Wiki pages from command-line paths."""

    parser = argparse.ArgumentParser(description="Build the HEVA GitHub Wiki.")
    parser.add_argument("docs_root", nargs="?", default="docs")
    parser.add_argument("output_directory", nargs="?", default="wiki-build")
    args = parser.parse_args(list(argv) if argv is not None else None)
    written = build_wiki(args.docs_root, args.output_directory)
    print(f"Built {len(written)} Wiki files in {Path(args.output_directory).resolve()}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
