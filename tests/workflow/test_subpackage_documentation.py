"""Acceptance checks for developer documentation at package boundaries."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).parents[2]


def test_every_main_subpackage_has_usage_and_boundary_documentation() -> None:
    expected = {
        "app": ["## Install and start", "## Persistence boundary", "## Tests"],
        "extraction": ["## Install", "## Known boundaries", "## Tests"],
        "workflow": ["## Install", "## Package ownership", "## Tests"],
    }

    for package, headings in expected.items():
        content = (ROOT / "src" / "heva" / package / "README.md").read_text(
            encoding="utf-8"
        )
        assert content.startswith("# HEVA")
        assert all(heading in content for heading in headings)
