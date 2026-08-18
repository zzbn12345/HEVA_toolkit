"""Render trusted HEVA Markdown as sanitized in-app documentation."""

from __future__ import annotations

from html import escape
from pathlib import Path, PurePosixPath
import posixpath
import re
import sysconfig
from typing import Callable

import bleach
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
import markdown


_MARKDOWN_LINK = re.compile(r"(\]\()([^)#]+\.md)(#[^)]+)?(\))")
_NAVIGATION = (
    (
        "HEVA Toolkit",
        (
            ("Start", ""),
            ("Install and run", "INSTALLATION"),
            ("HEVA and validation", "HEVA_AND_VALIDATION"),
            ("What is a Data Package?", "DATA_PACKAGE"),
            ("Tutorial", "TUTORIAL"),
            ("Software design", "SOFTWARE_DESIGN"),
        ),
    ),
)
_ALLOWED_TAGS = {
    "a",
    "blockquote",
    "br",
    "code",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "li",
    "ol",
    "p",
    "pre",
    "strong",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "ul",
}


class DocumentationError(ValueError):
    """Raised when bundled documentation cannot be resolved safely."""


def documentation_root() -> Path:
    """Locate repository Markdown in editable or installed-package environments."""

    repository_docs = Path(__file__).resolve().parents[3] / "docs"
    if repository_docs.is_dir():
        return repository_docs
    installed_docs = (
        Path(sysconfig.get_path("data")).resolve() / "share" / "heva" / "docs"
    )
    if installed_docs.is_dir():
        return installed_docs
    raise DocumentationError("Bundled HEVA documentation is not installed.")


def _document_path(slug: str) -> tuple[Path, str]:
    normalized = slug.strip("/")
    relative = PurePosixPath("index.md" if not normalized else f"{normalized}.md")
    if relative.is_absolute() or ".." in relative.parts:
        raise DocumentationError("Documentation path is not allowed.")
    root = documentation_root().resolve()
    target = (root / Path(*relative.parts)).resolve()
    try:
        target.relative_to(root)
    except ValueError as error:
        raise DocumentationError("Documentation path leaves the bundled guide.") from error
    if not target.is_file():
        raise DocumentationError("Documentation page was not found.")
    return target, relative.as_posix()


def _rewrite_links(source: str, current_relative: str) -> str:
    """Point relative Markdown documentation links at trusted in-app routes."""

    current_parent = PurePosixPath(current_relative).parent

    def replacement(match: re.Match[str]) -> str:
        raw_target = match.group(2)
        normalized = posixpath.normpath(
            (current_parent / PurePosixPath(raw_target)).as_posix()
        )
        if normalized.startswith("../") or normalized == "..":
            return match.group(0)
        slug = normalized.removesuffix(".md")
        suffix = match.group(3) or ""
        return f"](/guide/{slug}{suffix})"

    return _MARKDOWN_LINK.sub(replacement, source)


def render_document(slug: str) -> tuple[str, str]:
    """Render one bundled Markdown page and return its title plus sanitized HTML."""

    target, relative = _document_path(slug)
    source = target.read_text(encoding="utf-8")
    title_match = re.search(r"^#\s+(.+)$", source, flags=re.MULTILINE)
    title = title_match.group(1).strip() if title_match else target.stem
    rendered = markdown.markdown(
        _rewrite_links(source, relative),
        extensions=("fenced_code", "tables", "toc"),
        output_format="html",
    )
    sanitized = bleach.clean(
        rendered,
        tags=_ALLOWED_TAGS,
        attributes={"a": ["href", "title"], "code": ["class"], "h1": ["id"],
                    "h2": ["id"], "h3": ["id"], "h4": ["id"], "h5": ["id"],
                    "h6": ["id"]},
        protocols={"http", "https", "mailto"},
        strip=True,
    )
    return title, sanitized


def _navigation(active_slug: str) -> str:
    groups = []
    for heading, links in _NAVIGATION:
        items = []
        for label, slug in links:
            active = ' aria-current="page" class="active"' if slug == active_slug else ""
            href = "/guide" if not slug else f"/guide/{slug}"
            items.append(
                f'<a href="{escape(href)}"{active}>{escape(label)}</a>'
            )
        groups.append(
            f"<section><strong>{escape(heading)}</strong>{''.join(items)}</section>"
        )
    return "".join(groups)


def create_documentation_router(template: Callable[[str], str]) -> APIRouter:
    """Create public read-only routes for the bundled HEVA guide."""

    router = APIRouter()

    @router.get("/guide", response_class=HTMLResponse)
    @router.get("/guide/{slug:path}", response_class=HTMLResponse)
    def guide_page(slug: str = "") -> str:
        try:
            title, content = render_document(slug)
        except (DocumentationError, OSError, UnicodeError) as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return (
            template("documentation.html")
            .replace("DOCUMENTATION_TITLE", escape(title))
            .replace("DOCUMENTATION_NAVIGATION", _navigation(slug.strip("/")))
            .replace("DOCUMENTATION_CONTENT", content)
        )

    return router
