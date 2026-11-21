"""Checks that the bundled user guide and its images are complete and served in the app."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
import re

from fastapi.testclient import TestClient

from heva.app.main import create_app


DOCS = Path(__file__).resolve().parents[2] / "docs"
IMAGE_LINK = re.compile(r"!\[[^\]]*\]\(([^)\s]+)")


def _local_images(markdown: Path) -> list[PurePosixPath]:
    """Return the docs-root-relative paths of the local images a page embeds."""

    parent = PurePosixPath(markdown.relative_to(DOCS).parent.as_posix())
    return [
        PurePosixPath(*(parent / target).parts)
        for target in IMAGE_LINK.findall(markdown.read_text(encoding="utf-8"))
        if not target.startswith(("http://", "https://"))
    ]


def test_every_image_referenced_in_the_docs_exists() -> None:
    """A missing screenshot or diagram would break the strict documentation build."""

    missing = [
        f"{page.relative_to(DOCS)} -> {image}"
        for page in sorted(DOCS.rglob("*.md"))
        for image in _local_images(page)
        if not (DOCS / image).is_file()
    ]

    assert missing == []


def test_user_guide_is_listed_and_renders_its_images() -> None:
    client = TestClient(create_app())

    page = client.get("/guide/USER_GUIDE")
    images = re.findall(r'<img[^>]+src="([^"]+)"', page.text)

    assert page.status_code == 200
    assert 'href="/guide/USER_GUIDE"' in page.text
    assert images and all(src.startswith("/guide-assets/images/") for src in images)
    assert client.get(images[0]).status_code == 200
