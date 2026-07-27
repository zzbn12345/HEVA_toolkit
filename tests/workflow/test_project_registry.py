"""Acceptance tests for HEVA project initialization and registry synchronization."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from heva.workflow.project_registry import REGISTRY_VERSION, sync_registry


ROOT = Path(__file__).parents[2]


def add_source(source_dir: Path, name: str, content: bytes) -> Path:
    path = source_dir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_initialization_creates_registry_without_renaming_sources(tmp_path: Path) -> None:
    source_dir = tmp_path / "documents"
    pdf = add_source(source_dir, "Galle report.pdf", b"pdf-one")
    docx = add_source(source_dir, "notes/Analysis.docx", b"docx-one")

    report = sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / "data" / "project-registry.json").read_text())

    assert report.added == 2
    assert pdf.exists() and docx.exists()
    assert registry["registry_version"] == REGISTRY_VERSION
    assert [item["source_path"] for item in registry["documents"]] == [
        "documents/Galle report.pdf",
        "documents/notes/Analysis.docx",
    ]
    assert all(item["document_id"].startswith("HEVA-") for item in registry["documents"])
    assert all(
        item["package_path"] == f"data/packages/{item['document_id']}"
        for item in registry["documents"]
    )
    assert all(
        (tmp_path / item["package_path"]).is_dir() for item in registry["documents"]
    )
    assert all(
        item["metadata_path"] == f"{item['package_path']}/package-metadata.json"
        for item in registry["documents"]
    )
    for item in registry["documents"]:
        metadata = json.loads((tmp_path / item["metadata_path"]).read_text())
        assert metadata["document_id"] == item["document_id"]
        assert metadata["source"]["creators"] == []
        assert metadata["color_configuration"]["colors"] == []
        assert metadata["resources"] == []
    assert registry["summary"] == {
        "total": 2,
        "backlog": 2,
        "in_progress": 0,
        "in_review": 0,
        "done": 0,
        "changed": 0,
        "missing": 0,
    }


def test_resync_preserves_ids_and_existing_state(tmp_path: Path) -> None:
    source_dir = tmp_path / "documents"
    add_source(source_dir, "source.pdf", b"first version")
    sync_registry(tmp_path, source_dir="documents")
    registry_path = tmp_path / "data" / "project-registry.json"
    registry = json.loads(registry_path.read_text())
    original_id = registry["documents"][0]["document_id"]
    registry["documents"][0]["status"] = "in_progress"
    registry_path.write_text(json.dumps(registry), encoding="utf-8")

    report = sync_registry(tmp_path, source_dir="documents")
    updated = json.loads(registry_path.read_text())

    assert report.unchanged == 1
    assert updated["documents"][0]["document_id"] == original_id
    assert updated["documents"][0]["status"] == "in_progress"
    assert updated["summary"]["in_progress"] == 1


def test_resync_does_not_overwrite_existing_package_metadata(tmp_path: Path) -> None:
    source_dir = tmp_path / "documents"
    add_source(source_dir, "source.pdf", b"first version")
    sync_registry(tmp_path, source_dir="documents")
    registry = json.loads((tmp_path / "data" / "project-registry.json").read_text())
    metadata_path = tmp_path / registry["documents"][0]["metadata_path"]
    metadata = json.loads(metadata_path.read_text())
    metadata["source"]["title"] = "Researcher-provided title"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    sync_registry(tmp_path, source_dir="documents")

    preserved = json.loads(metadata_path.read_text())
    assert preserved["source"]["title"] == "Researcher-provided title"


def test_resync_adds_new_document_once(tmp_path: Path) -> None:
    source_dir = tmp_path / "documents"
    add_source(source_dir, "one.pdf", b"one")
    sync_registry(tmp_path, source_dir="documents")
    add_source(source_dir, "two.docx", b"two")

    first = sync_registry(tmp_path, source_dir="documents")
    second = sync_registry(tmp_path, source_dir="documents")

    assert first.added == 1
    assert second.added == 0
    assert second.unchanged == 2
    registry = json.loads((tmp_path / "data" / "project-registry.json").read_text())
    assert len(list((tmp_path / "data" / "packages").iterdir())) == len(
        registry["documents"]
    )


def test_resync_reports_changed_and_missing_sources_without_replacing_ids(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "documents"
    changed = add_source(source_dir, "changed.pdf", b"original")
    missing = add_source(source_dir, "missing.docx", b"present")
    sync_registry(tmp_path, source_dir="documents")
    registry_path = tmp_path / "data" / "project-registry.json"
    before = {
        item["source_path"]: item["document_id"]
        for item in json.loads(registry_path.read_text())["documents"]
    }

    changed.write_bytes(b"revised")
    missing.unlink()
    report = sync_registry(tmp_path, source_dir="documents")
    after = {
        item["source_path"]: item
        for item in json.loads(registry_path.read_text())["documents"]
    }

    assert report.changed == ("documents/changed.pdf",)
    assert report.missing == ("documents/missing.docx",)
    assert after["documents/changed.pdf"]["document_id"] == before["documents/changed.pdf"]
    assert after["documents/missing.docx"]["document_id"] == before["documents/missing.docx"]
    assert after["documents/missing.docx"]["source_state"] == "missing"


def run_registry(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "heva.workflow.project_registry",
            *arguments,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_script_emits_human_and_machine_readable_summaries(tmp_path: Path) -> None:
    add_source(tmp_path / "documents", "source.pdf", b"content")

    human = run_registry(str(tmp_path), "--source-dir", "documents")
    machine = run_registry(str(tmp_path), "--source-dir", "documents", "--json")

    assert human.returncode == 0
    assert "HEVA registry:" in human.stdout
    assert "1 added" in human.stdout
    assert machine.returncode == 0
    summary = json.loads(machine.stdout)
    assert summary["registry_path"] == "data/project-registry.json"
    assert summary["unchanged"] == 1
