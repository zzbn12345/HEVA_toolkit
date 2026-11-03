"""Exporting the released files and loading the benchmark splits from them (no torch needed)."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from heva.baselines.cli import main
from heva.baselines.corpus import load_t1_dataset, load_t2_dataset
from heva.baselines.labels import VALUES
from heva.baselines.release import (
    RELEASED_SPLIT_SEED,
    ReleaseError,
    export_release,
    has_released_split,
    load_released_split,
    split_path,
)
from heva.baselines.splits import PARTITIONS, split_examples
from tests.baselines.package_fixture import PACKAGE_RECORDS, write_package_json

ROOT = Path(__file__).parents[2]
COLLECTION = "1_P_2020_XX"


@pytest.fixture()
def release(tmp_path: Path) -> dict[str, Path]:
    """Raw inputs and published split files for a small dataset."""
    data = tmp_path / "data"
    write_package_json(data / "heva" / COLLECTION)
    results = tmp_path / "results"
    for task, loader in (("t1", load_t1_dataset), ("t2", load_t2_dataset)):
        examples, _ = loader(data)
        parts = split_examples(examples, RELEASED_SPLIT_SEED)
        for run in ("run-a", "run-b"):
            (results / task / run).mkdir(parents=True)
            (results / task / run / "split.json").write_text(
                json.dumps({name: [e.example_id for e in part] for name, part in parts.items()})
            )
    return {"data": data, "results": results, "benchmark": tmp_path / "benchmark"}


def export(release: dict[str, Path]) -> dict:
    return export_release(release["data"], release["results"], release["benchmark"])


def test_export_writes_the_split_files(release: dict[str, Path]) -> None:
    written = export(release)

    assert sum(written["t1"].values()) == sum(written["t2"].values()) == PACKAGE_RECORDS
    assert has_released_split(release["benchmark"], "t1")
    assert has_released_split(release["benchmark"], "t2")


@pytest.mark.parametrize("task,loader", [("t1", load_t1_dataset), ("t2", load_t2_dataset)])
def test_released_split_round_trips_the_published_split(release, task, loader) -> None:
    export(release)
    examples, _ = loader(release["data"])

    parts, report = load_released_split(release["benchmark"], task)

    assert has_released_split(release["benchmark"], task)
    assert parts == split_examples(examples, RELEASED_SPLIT_SEED)
    assert len(report.files) == len(PARTITIONS)


def test_export_refuses_a_split_that_does_not_match_the_inputs(release) -> None:
    for path in (release["results"] / "t2").glob("*/split.json"):
        split = json.loads(path.read_text())
        split["test"].append("heva:UNKNOWN:1")
        path.write_text(json.dumps(split))

    with pytest.raises(ReleaseError, match="do not match the published split"):
        export(release)
    assert not (release["benchmark"] / "t1").exists()


def test_export_refuses_runs_with_different_splits(release) -> None:
    path = release["results"] / "t1" / "run-b" / "split.json"
    split = json.loads(path.read_text())
    split["train"], split["test"] = split["test"], split["train"]
    path.write_text(json.dumps(split))

    with pytest.raises(ReleaseError, match="different splits"):
        export(release)


def test_training_without_a_released_split_asks_for_data(tmp_path: Path, capsys) -> None:
    assert main(["t2", "--benchmark-dir", str(tmp_path / "missing")]) == 1
    assert "No released T2 split" in capsys.readouterr().err


def test_inspect_reads_the_released_split(release, capsys) -> None:
    export(release)

    assert main(["inspect", "--benchmark-dir", str(release["benchmark"])]) == 0

    assert '"examples"' in capsys.readouterr().out


def read_table(name: str) -> list[dict]:
    with (ROOT / "data" / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_published_reference_tables_agree() -> None:
    collections = read_table("collections.csv")
    documents = read_table("documents.csv")

    assert sum(int(row["units"]) for row in collections) == 6324
    assert sum(int(row["sources"]) for row in collections) == len(documents) == 197
    for row in collections:
        listed = [document for document in documents if document["collection"] == row["id"]]
        assert len(listed) == int(row["sources"])
        assert sum(int(document["units"]) for document in listed) == int(row["units"])
        assert all(document["document_id"] for document in listed) == (row["format"] == "P")


@pytest.mark.parametrize(
    "task,sizes",
    [("t1", {"train": 3696, "validation": 521, "test": 1063}),
     ("t2", {"train": 680, "validation": 92, "test": 189})],
)
def test_released_splits_match_the_published_runs(task: str, sizes: dict[str, int]) -> None:
    benchmark = ROOT / "benchmark"
    if not has_released_split(benchmark, task):
        pytest.skip("The split files are not in this checkout.")

    parts, _ = load_released_split(benchmark, task)

    assert {name: len(part) for name, part in parts.items()} == sizes
    for path in (benchmark / "results" / task).glob("*/split.json"):
        published = json.loads(path.read_text(encoding="utf-8"))
        assert {name: [e.example_id for e in part] for name, part in parts.items()} == published


def test_released_data_packages_match_their_manifests_and_reference_tables() -> None:
    packages = sorted((ROOT / "data" / "heva").glob("*/datapackage.json"))
    if not packages:
        pytest.skip("The Data Packages are not in this checkout.")
    documents = {row["document_id"]: row for row in read_table("documents.csv") if row["document_id"]}

    records = 0
    for manifest_path in packages:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for resource in manifest["resources"]:
            content = (manifest_path.parent / resource["path"]).read_bytes()
            assert len(content) == resource["bytes"], resource["path"]
            assert f"sha256:{hashlib.sha256(content).hexdigest()}" == resource["hash"], resource["path"]
        package = json.loads(
            (manifest_path.parent / "heva-annotations.json").read_text(encoding="utf-8")
        )
        for document in package["documents"]:
            listed = documents[document["document_id"]]
            assert listed["collection"] == manifest_path.parent.name
            assert int(listed["units"]) == len(document["records"])
            records += len(document["records"])

    assert len(packages) == 3
    assert records == 1017


def test_export_from_released_data_reproduces_the_split_files(tmp_path: Path) -> None:
    pytest.importorskip("openpyxl")
    benchmark = ROOT / "benchmark"
    if not list((ROOT / "data" / "heva").glob("*/heva-annotations.json")):
        pytest.skip("The Data Packages are not in this checkout.")

    export_release(ROOT / "data", benchmark / "results", tmp_path)

    for task in ("t1", "t2"):
        for name in PARTITIONS:
            written = split_path(tmp_path, task, name).read_text(encoding="utf-8")
            assert written == split_path(benchmark, task, name).read_text(encoding="utf-8")
