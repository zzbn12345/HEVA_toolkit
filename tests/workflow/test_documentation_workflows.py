"""Acceptance checks for independent HTML and Wiki documentation workflows."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).parents[2]


def test_html_documentation_is_built_and_packaged_independently() -> None:
    workflow = (ROOT / ".github/workflows/docs-build.yml").read_text(encoding="utf-8")

    assert "mkdocs build --strict --site-dir site" in workflow
    assert "heva-documentation-html.tar.gz" in workflow
    assert "sha256sum heva-documentation-html.tar.gz" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "retention-days: 30" in workflow
    assert "heva.app" not in workflow


def test_wiki_workflow_only_builds_and_publishes_wiki_markdown() -> None:
    workflow = (ROOT / ".github/workflows/docs-wiki.yml").read_text(encoding="utf-8")

    assert "python -m heva.wiki docs wiki-build" in workflow
    assert "mkdocs build" not in workflow
    assert "WIKI_TOKEN" in workflow
