"""Acceptance tests for deterministic Wiki documentation builds."""

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


def _build_documentation_with_every_group(tmp_path: Path) -> Path:
    docs = tmp_path / "docs"
    (docs / "adr").mkdir(parents=True)
    (docs / "index.md").write_text("# Toolkit\n", encoding="utf-8")
    (docs / "INSTALLATION.md").write_text("# Install and run HEVA\n", encoding="utf-8")
    (docs / "TUTORIAL.md").write_text("# Tutorial: repair an example\n", encoding="utf-8")
    (docs / "DATA_PACKAGE.md").write_text("# What is a Data Package?\n", encoding="utf-8")
    (docs / "NO_HEADING.md").write_text("Text without a heading.\n", encoding="utf-8")
    (docs / "adr" / "ADR-001-choice.md").write_text("# ADR-001: A choice\n", encoding="utf-8")
    build_wiki(docs, tmp_path / "wiki")
    return tmp_path / "wiki"


def test_wiki_sidebar_uses_page_headings_and_omits_empty_groups(tmp_path: Path) -> None:
    sidebar = (_build_documentation_with_every_group(tmp_path) / "_Sidebar.md").read_text()

    assert "- [What is a Data Package?](Data-Package)" in sidebar
    assert "- [No Heading](No-Heading)" in sidebar
    assert "### Guides" not in sidebar
    assert "### Reference" not in sidebar


def test_wiki_sidebar_starts_with_the_tutorial_and_separates_decision_records(
    tmp_path: Path,
) -> None:
    sidebar = (_build_documentation_with_every_group(tmp_path) / "_Sidebar.md").read_text()

    start, rest = sidebar.split("### Concepts")
    concepts, decisions = rest.split("### Decisions")
    assert "(Tutorial)" in start
    assert "(Data-Package)" in concepts
    assert "(Adr-Adr-001-Choice)" in decisions
    assert "(Adr-Adr-001-Choice)" not in concepts


def test_wiki_footer_names_the_public_repository(tmp_path: Path) -> None:
    footer = (_build_documentation_with_every_group(tmp_path) / "_Footer.md").read_text()

    assert "private" not in footer
    assert "https://github.com/zzbn12345/HEVA_toolkit" in footer
