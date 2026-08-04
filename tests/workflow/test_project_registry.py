"""Acceptance tests for HEVA project initialization and registry synchronization."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from heva.workflow.project_registry import (
    REGISTRY_VERSION,
    RegistryError,
    load_project_registry,
    relocate_project_root_to_sources,
    sync_registry,
)


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
    registry = json.loads((tmp_path / ".heva" / "project.json").read_text())

    assert report.added == 2
    assert pdf.exists() and docx.exists()
    assert registry["registry_version"] == REGISTRY_VERSION
    assert [item["source_path"] for item in registry["documents"]] == [
        "documents/Galle report.pdf",
        "documents/notes/Analysis.docx",
    ]
    assert all(item["document_id"].startswith("HEVA-") for item in registry["documents"])
    assert all(
        item["package_path"] == f"documents/{item['document_id']}"
        for item in registry["documents"]
    )
    assert all(
        (tmp_path / item["package_path"]).is_dir() for item in registry["documents"]
    )
    assert all(
        item["metadata_path"] == f"{item['package_path']}/metadata.json"
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
    registry_path = tmp_path / ".heva" / "project.json"
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
    registry = json.loads((tmp_path / ".heva" / "project.json").read_text())
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
    registry = json.loads((tmp_path / ".heva" / "project.json").read_text())
    assert len(
        [path for path in (tmp_path / "documents").iterdir() if path.name.startswith("HEVA-")]
    ) == len(registry["documents"])


def test_resync_reports_changed_and_missing_sources_without_replacing_ids(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "documents"
    changed = add_source(source_dir, "changed.pdf", b"original")
    missing = add_source(source_dir, "missing.docx", b"present")
    sync_registry(tmp_path, source_dir="documents")
    registry_path = tmp_path / ".heva" / "project.json"
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
    assert summary["registry_path"] == ".heva/project.json"
    assert summary["unchanged"] == 1


def test_opening_legacy_project_separates_data_from_hidden_workflow_state(
    tmp_path: Path,
) -> None:
    """Existing projects migrate without losing analytical or audit JSON."""

    document_id = "HEVA-LEGACY001"
    legacy_directory = tmp_path / "data/packages" / document_id
    legacy_directory.mkdir(parents=True)
    (legacy_directory / "package-metadata.json").write_text('{"kind":"metadata"}')
    (legacy_directory / "annotations.json").write_text('[{"kind":"annotation"}]')
    for filename in (
        "extraction-session.json",
        "review-state.json",
        "curation-state.json",
    ):
        (legacy_directory / filename).write_text(json.dumps({"kind": filename}))
    legacy_registry = {
        "registry_version": REGISTRY_VERSION,
        "source_directory": "documents",
        "documents": [
            {
                "document_id": document_id,
                "source_path": "documents/source.pdf",
                "package_path": f"data/packages/{document_id}",
                "metadata_path": f"data/packages/{document_id}/package-metadata.json",
                "checksum_sha256": "a" * 64,
                "status": "in_progress",
                "source_state": "present",
            }
        ],
        "summary": {
            "total": 1,
            "backlog": 0,
            "in_progress": 1,
            "in_review": 0,
            "done": 0,
            "changed": 0,
            "missing": 0,
        },
    }
    (tmp_path / "data/project-registry.json").write_text(json.dumps(legacy_registry))

    registry = load_project_registry(tmp_path)

    entry = registry.documents[0]
    assert entry.package_path == f"documents/{document_id}"
    assert entry.metadata_path == f"documents/{document_id}/metadata.json"
    assert (tmp_path / entry.metadata_path).read_text() == '{"kind":"metadata"}'
    data_directory = tmp_path / entry.package_path
    assert (data_directory / "annotations.json").is_file()
    assert {path.name for path in data_directory.iterdir()} == {
        "metadata.json",
        "annotations.json",
    }
    workspace = tmp_path / ".heva/documents" / document_id
    assert {path.name for path in workspace.iterdir()} == {
        "extraction-session.json",
        "review-state.json",
        "curation-state.json",
    }
    assert not (tmp_path / "data/project-registry.json").exists()
    assert not (tmp_path / "data/packages").exists()


def test_legacy_migration_refuses_conflicts_before_moving_any_file(tmp_path: Path) -> None:
    document_id = "HEVA-CONFLICT001"
    legacy_directory = tmp_path / "data/packages" / document_id
    legacy_directory.mkdir(parents=True)
    legacy_metadata = legacy_directory / "package-metadata.json"
    legacy_metadata.write_text('{"legacy":true}')
    legacy_annotations = legacy_directory / "annotations.json"
    legacy_annotations.write_text("[]")
    current_directory = tmp_path / "documents" / document_id
    current_directory.mkdir(parents=True)
    (current_directory / "metadata.json").write_text('{"current":true}')
    registry = {
        "registry_version": REGISTRY_VERSION,
        "source_directory": "documents",
        "documents": [{
            "document_id": document_id,
            "source_path": "documents/source.pdf",
            "package_path": f"data/packages/{document_id}",
            "metadata_path": f"data/packages/{document_id}/package-metadata.json",
            "checksum_sha256": "a" * 64,
            "status": "backlog",
            "source_state": "present",
        }],
        "summary": {
            "total": 1, "backlog": 1, "in_progress": 0, "in_review": 0,
            "done": 0, "changed": 0, "missing": 0,
        },
    }
    legacy_registry = tmp_path / "data/project-registry.json"
    legacy_registry.write_text(json.dumps(registry))

    with pytest.raises(RegistryError, match="metadata.json already exists"):
        load_project_registry(tmp_path)

    assert legacy_metadata.is_file()
    assert legacy_annotations.is_file()
    assert legacy_registry.is_file()
    assert not (tmp_path / ".heva/project.json").exists()


def test_git_tracks_durable_workspace_json_but_ignores_local_runtime_state() -> None:
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "\n/.heva/\n" not in ignore
    assert "\n/data/documents/\n" not in ignore
    assert "**/.heva/cache/" in ignore
    assert "**/.heva/locks/" in ignore
    assert "**/.heva/session.json" in ignore
    assert "**/exports/" in ignore


def test_source_folder_relocation_refuses_workspace_conflict_without_moving(
    tmp_path: Path,
) -> None:
    sources = tmp_path / "sources"
    add_source(sources, "source.pdf", b"source")
    sync_registry(tmp_path, source_dir="sources")
    conflicting_workspace = sources / ".heva"
    conflicting_workspace.mkdir()
    (conflicting_workspace / "project.json").write_text("conflict")

    with pytest.raises(RegistryError, match="already exists"):
        relocate_project_root_to_sources(tmp_path, "sources")

    assert (tmp_path / ".heva/project.json").is_file()
    assert (sources / "source.pdf").is_file()
