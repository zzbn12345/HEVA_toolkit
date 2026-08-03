"""Acceptance tests for deterministic private Wiki documentation builds."""

from __future__ import annotations

from pathlib import Path

from heva.wiki import build_wiki, discover_pages


def test_wiki_builder_flattens_pages_and_rewrites_document_links(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    guides = docs / "guides"
    guides.mkdir(parents=True)
    (docs / "index.md").write_text(
        "# Home\n\n[Start](guides/get-started.md)\n", encoding="utf-8"
    )
    (guides / "get-started.md").write_text(
        "# Get started\n\n[Home](../index.md#top)\n", encoding="utf-8"
    )

    written = build_wiki(docs, tmp_path / "wiki")

    assert {path.name for path in written} == {
        "Home.md",
        "Guides-Get-Started.md",
        "_Sidebar.md",
        "_Footer.md",
    }
    assert "[Start](Guides-Get-Started)" in (tmp_path / "wiki/Home.md").read_text()
    assert "[Home](Home#top)" in (
        tmp_path / "wiki/Guides-Get-Started.md"
    ).read_text()


def test_repository_documentation_has_unique_wiki_page_names() -> None:
    docs = Path(__file__).parents[2] / "docs"

    pages = discover_pages(docs)

    assert pages
    assert pages[next(path for path in pages if path.as_posix() == "index.md")] == "Home"
