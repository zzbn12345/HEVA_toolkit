"""Regression evidence for the app-openable complete workspace example."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from heva.workflow.package_validator import build_release, validate_project


BUILDER_PATH = (
    Path(__file__).parents[2]
    / "examples"
    / "workspace-fixture-builder"
    / "build_complete_workspace.py"
)


def _builder_module():
    """Load the standalone example builder without making examples an installed package."""

    specification = importlib.util.spec_from_file_location("complete_workspace_builder", BUILDER_PATH)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_complete_workspace_validates_and_exports_selected_membership(tmp_path: Path) -> None:
    """Generate two valid documents and export exactly one selected member."""

    workspace = _builder_module().build_complete_workspace(tmp_path / "workspace")
    report = validate_project(workspace)
    selected = report.documents[0].document_id

    release = build_release(workspace, document_ids=[selected])
    payload = json.loads((release / "heva-annotations.json").read_text(encoding="utf-8"))

    assert report.release_ready is True
    assert report.summary.passed == 2
    assert payload["membership"] == [selected]
    assert len(payload["excluded_project_document_ids"]) == 1
    assert not any(path.suffix == ".pdf" for path in release.iterdir())
