"""Acceptance tests for the HEVA installation and environment check."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from heva import doctor
from heva.workflow.project_registry import sync_registry


def test_core_environment_check_is_machine_readable() -> None:
    report = doctor.check_environment(require=["core"])

    assert report.ready is True
    assert report.required_capabilities == ["core"]
    assert next(check for check in report.checks if check.code == "python_version").status == "pass"
    assert next(check for check in report.checks if check.code == "core_pydantic").status == "pass"


def test_missing_required_app_dependency_has_install_action(monkeypatch) -> None:
    available = doctor._module_available
    monkeypatch.setattr(
        doctor,
        "_module_available",
        lambda module: False if module == "fastapi" else available(module),
    )

    report = doctor.check_environment(require=["app"])
    missing = next(check for check in report.checks if check.code == "app_fastapi")

    assert report.ready is False
    assert missing.status == "fail"
    assert ".[app]" in missing.action


def test_optional_extraction_dependencies_do_not_fail_core(monkeypatch) -> None:
    available = doctor._module_available
    monkeypatch.setattr(
        doctor,
        "_module_available",
        lambda module: False if module in {"fitz", "docx", "spacy"} else available(module),
    )

    report = doctor.check_environment()

    assert report.ready is True
    assert all(
        check.status == "warning"
        for check in report.checks
        if check.code.startswith("extraction_")
    )


def test_project_check_reports_registered_document_count(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "source.pdf").write_bytes(b"source")
    sync_registry(tmp_path, source_dir="sources")

    report = doctor.check_environment(project_root=tmp_path)
    project = next(check for check in report.checks if check.code == "project_registry")

    assert report.ready is True
    assert project.status == "pass"
    assert "1 document(s)" in project.message


def test_json_command_returns_stable_report() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "heva.doctor", "--json"],
        check=False,
        capture_output=True,
        text=True,
    )

    report = json.loads(completed.stdout)
    assert completed.returncode == 0
    assert report["ready"] is True
    assert report["required_capabilities"] == ["core"]
    assert all({"code", "status", "message", "action"} == set(item) for item in report["checks"])
