"""The released benchmark splits: export them, and load them for training.

``export_release`` writes the six ``benchmark/{t1,t2}/{train,validation,test}.jsonl`` files from
``data/``. The split is read from the ``split.json`` of the published runs, not recomputed, so
the released files are exactly the examples behind the reported results.
"""

from __future__ import annotations

import json
from pathlib import Path

from .corpus import LoadReport, T1Example, T2Example, load_t1_dataset, load_t2_dataset
from .splits import PARTITIONS, split_examples

RELEASED_SPLIT_SEED = 13
TASKS = {"t1": T1Example, "t2": T2Example}

class ReleaseError(ValueError):
    """The working inputs do not add up to the release they should produce."""


# --- Loading the released splits --------------------------------------------------------


def split_path(benchmark_dir: Path, task: str, partition: str) -> Path:
    return Path(benchmark_dir) / task / f"{partition}.jsonl"


def has_released_split(benchmark_dir: Path, task: str) -> bool:
    return all(split_path(benchmark_dir, task, name).is_file() for name in PARTITIONS)


def _example_from_row(task: str, row: dict) -> T1Example | T2Example:
    if task == "t1":
        return T1Example(
            row["id"], row["text"], tuple(row["values"]), row["source"], row["document"],
            row["collection"],
        )
    return T2Example(
        row["id"], tuple(row["tokens"]), tuple(row["tags"]), row["document"], row["collection"]
    )


def _row_from_example(task: str, example: T1Example | T2Example) -> dict:
    if task == "t1":
        return {
            "id": example.example_id, "text": example.text, "values": list(example.values),
            "source": example.source, "document": example.document,
            "collection": example.collection,
        }
    return {
        "id": example.example_id, "tokens": list(example.tokens), "tags": list(example.tags),
        "document": example.document, "collection": example.collection,
    }


def load_released_split(benchmark_dir: Path, task: str) -> tuple[dict[str, list], LoadReport]:
    """Read one task's released train, validation and test examples, in file order."""
    report = LoadReport()
    parts = {}
    for name in PARTITIONS:
        path = split_path(benchmark_dir, task, name)
        report.files.append(str(path))
        with path.open(encoding="utf-8") as lines:
            parts[name] = [_example_from_row(task, json.loads(line)) for line in lines if line.strip()]
    return parts, report


# --- Exporting --------------------------------------------------------------------------


def _read_published_split(results_dir: Path, task: str) -> dict[str, list[str]]:
    """The one split shared by all published runs of a task."""
    files = sorted((Path(results_dir) / task).glob("*/split.json"))
    if not files:
        raise ReleaseError(f"No published {task} run with a split.json under {results_dir}.")
    splits = [json.loads(path.read_text(encoding="utf-8")) for path in files]
    if any(split != splits[0] for split in splits):
        raise ReleaseError(f"The published {task} runs under {results_dir} use different splits.")
    return splits[0]


def _assign(examples: list, split: dict[str, list[str]], task: str) -> dict[str, list]:
    by_id = {example.example_id: example for example in examples}
    named = [identifier for name in PARTITIONS for identifier in split[name]]
    if sorted(named) != sorted(by_id):
        missing = len(set(named) - set(by_id))
        extra = len(set(by_id) - set(named))
        raise ReleaseError(
            f"{task}: the inputs do not match the published split "
            f"({missing} split ids have no example, {extra} examples are not in the split)."
        )
    return {name: [by_id[identifier] for identifier in split[name]] for name in PARTITIONS}


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def export_release(data_dir: Path, results_dir: Path, benchmark_dir: Path) -> dict:
    """Write the split files and return their sizes. Nothing is written on a mismatch."""
    data_dir = Path(data_dir)
    splits = {}
    for task, loader in (("t1", load_t1_dataset), ("t2", load_t2_dataset)):
        examples, _ = loader(data_dir)
        split = _read_published_split(results_dir, task)
        parts = _assign(examples, split, task)
        recomputed = split_examples(examples, RELEASED_SPLIT_SEED)
        if {name: [e.example_id for e in recomputed[name]] for name in PARTITIONS} != {
            name: split[name] for name in PARTITIONS
        }:
            raise ReleaseError(
                f"{task}: split seed {RELEASED_SPLIT_SEED} does not reproduce the published split."
            )
        splits[task] = parts

    for task, parts in splits.items():
        for name, part in parts.items():
            _write_jsonl(
                split_path(benchmark_dir, task, name),
                [_row_from_example(task, example) for example in part],
            )
    return {task: {name: len(part) for name, part in parts.items()} for task, parts in splits.items()}
