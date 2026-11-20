"""Render trusted HEVA Markdown as sanitized in-app documentation."""

from __future__ import annotations

from html import escape
from pathlib import Path, PurePosixPath
import posixpath
import re
import sysconfig
from typing import Callable
from urllib.parse import quote, unquote, urlsplit
from xml.etree.ElementTree import Element

import bleach
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
import markdown
from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor


_MARKDOWN_LINK = re.compile(r"(\]\()([^)#]+\.md)(#[^)]+)?(\))")
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
    "img",
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

GUIDE_ASSET_ROUTE = "/guide-assets"
_ASSET_MEDIA_TYPES = {
    ".gif": "image/gif",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
}
# An SVG is a document that may carry scripts; this policy lets it draw with
# inline styles but never execute code or fetch anything when opened directly.
_SVG_CONTENT_SECURITY_POLICY = "default-src 'none'; style-src 'unsafe-inline'"


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


def _asset_source(source: str, current_relative: str) -> str:
    """Point one relative image path at the read-only guide asset route.

    Paths are resolved against the folder of the current page, as a static
    site would. External URLs, absolute paths, fragments, and paths that
    climb above the documentation root are returned unchanged.
    """

    parts = urlsplit(source)
    if parts.scheme or parts.netloc or not parts.path or source.startswith(("/", "#")):
        return source
    current_parent = PurePosixPath(current_relative).parent
    normalized = posixpath.normpath(
        (current_parent / PurePosixPath(unquote(parts.path))).as_posix()
    )
    if normalized == ".." or normalized.startswith("../"):
        return source
    return f"{GUIDE_ASSET_ROUTE}/{quote(normalized)}"


class _ImageSourceTreeprocessor(Treeprocessor):
    """Rewrite image sources in the parsed page before it is serialized."""

    def __init__(self, md: markdown.Markdown, current_relative: str) -> None:
        super().__init__(md)
        self.current_relative = current_relative

    def run(self, root: Element) -> None:
        for image in root.iter("img"):
            source = image.get("src")
            if source:
                image.set("src", _asset_source(source, self.current_relative))


class _ImageSourceExtension(Extension):
    """Register image rewriting for one page; covers inline and reference images."""

    def __init__(self, current_relative: str) -> None:
        super().__init__()
        self.current_relative = current_relative

    def extendMarkdown(self, md: markdown.Markdown) -> None:
        # Below "unescape" (priority 0) so each source is final before rewriting.
        md.treeprocessors.register(
            _ImageSourceTreeprocessor(md, self.current_relative), "heva_image_sources", -1
        )


def resolve_asset(asset_path: str) -> Path:
    """Return one allow-listed image file that lies inside the documentation root."""

    relative = PurePosixPath(asset_path)
    if (
        not asset_path
        or relative.is_absolute()
        or ".." in relative.parts
        or "\\" in asset_path
        or "\x00" in asset_path
        or relative.suffix.lower() not in _ASSET_MEDIA_TYPES
    ):
        raise DocumentationError("Documentation asset path is not allowed.")
    root = documentation_root().resolve()
    target = (root / Path(*relative.parts)).resolve()
    try:
        target.relative_to(root)
    except ValueError as error:
        raise DocumentationError("Documentation asset leaves the bundled guide.") from error
    if target.suffix.lower() not in _ASSET_MEDIA_TYPES or not target.is_file():
        raise DocumentationError("Documentation asset was not found.")
    return target


def render_document(slug: str) -> tuple[str, str]:
    """Render one bundled Markdown page and return its title plus sanitized HTML."""

    target, relative = _document_path(slug)
    source = target.read_text(encoding="utf-8")
    title_match = re.search(r"^#\s+(.+)$", source, flags=re.MULTILINE)
    title = title_match.group(1).strip() if title_match else target.stem
    rendered = markdown.markdown(
        _rewrite_links(source, relative),
        extensions=("fenced_code", "tables", "toc", _ImageSourceExtension(relative)),
        output_format="html",
    )
    sanitized = bleach.clean(
        rendered,
        tags=_ALLOWED_TAGS,
        attributes={"a": ["href", "title"], "code": ["class"], "h1": ["id"],
                    "img": ["src", "alt", "title"],
                    "h2": ["id"], "h3": ["id"], "h4": ["id"], "h5": ["id"],
                    "h6": ["id"]},
        protocols={"http", "https", "mailto"},
        strip=True,
    )
    return title, sanitized


def create_documentation_router(template: Callable[[str], str]) -> APIRouter:
    """Create public read-only routes for the bundled HEVA guide and its images."""

    router = APIRouter()

    @router.get(GUIDE_ASSET_ROUTE + "/{asset_path:path}")
    def guide_asset(asset_path: str) -> FileResponse:
        try:
            target = resolve_asset(asset_path)
        except (DocumentationError, OSError) as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        headers = {"X-Content-Type-Options": "nosniff"}
        if target.suffix.lower() == ".svg":
            headers["Content-Security-Policy"] = _SVG_CONTENT_SECURITY_POLICY
        return FileResponse(
            target, media_type=_ASSET_MEDIA_TYPES[target.suffix.lower()], headers=headers
        )

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
            .replace("DOCUMENTATION_CONTENT", content)
        )

    return router
