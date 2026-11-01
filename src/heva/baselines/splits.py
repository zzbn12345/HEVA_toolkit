"""Iterative stratification for multi-label data (Sechidis, Tsoumakas & Vlahavas, 2011)."""

from __future__ import annotations

import random
from collections.abc import Sequence

DEFAULT_PARTITIONS = (("train", 0.7), ("validation", 0.1), ("test", 0.2))
PARTITIONS = tuple(name for name, _ in DEFAULT_PARTITIONS)


def iterative_stratification(
    items: Sequence[tuple[str, Sequence[str]]],
    partitions: Sequence[tuple[str, float]] = DEFAULT_PARTITIONS,
    seed: int = 13,
) -> dict[str, str]:
    """Assign each ``(item_id, labels)`` pair to a partition name.

    Rarest labels are distributed first, each example going to the partition that still
    needs most examples of that label. Items without labels fill the remaining capacity.
    """
    rng = random.Random(seed)
    names = [name for name, _ in partitions]
    ratios = [ratio for _, ratio in partitions]
    total = sum(ratios)
    ratios = [ratio / total for ratio in ratios]

    remaining = {item_id: set(labels) for item_id, labels in items}
    if len(remaining) != len(items):
        raise ValueError("Item ids must be unique.")

    label_counts: dict[str, int] = {}
    for labels in remaining.values():
        for label in labels:
            label_counts[label] = label_counts.get(label, 0) + 1

    wanted = [len(remaining) * ratio for ratio in ratios]
    wanted_per_label = [
        {label: count * ratio for label, count in label_counts.items()} for ratio in ratios
    ]
    assignment: dict[str, str] = {}

    def assign(item_id: str, index: int) -> None:
        for label in remaining.pop(item_id):
            wanted_per_label[index][label] -= 1
            label_counts[label] -= 1
        wanted[index] -= 1
        assignment[item_id] = names[index]

    def best_partition(scores: Sequence[float]) -> int:
        top = max(scores)
        candidates = [index for index, score in enumerate(scores) if score == top]
        if len(candidates) > 1:
            best_size = max(wanted[index] for index in candidates)
            candidates = [index for index in candidates if wanted[index] == best_size]
        return rng.choice(candidates)

    while any(count > 0 for count in label_counts.values()):
        fewest = min(count for count in label_counts.values() if count > 0)
        label = rng.choice(
            sorted(name for name, count in label_counts.items() if count == fewest)
        )
        with_label = sorted(item_id for item_id, labels in remaining.items() if label in labels)
        rng.shuffle(with_label)
        for item_id in with_label:
            assign(item_id, best_partition([per_label[label] for per_label in wanted_per_label]))

    unlabeled = sorted(remaining)
    rng.shuffle(unlabeled)
    for item_id in unlabeled:
        assign(item_id, best_partition(wanted))
    return assignment


def split_examples(examples, seed: int) -> dict[str, list]:
    """70/10/20 iterative stratification over each example's value set, per collection.

    Each collection is split on its own, so that every collection is represented in each
    partition in proportion to its size, however dominant other collections are.
    """
    collections: dict[str, list] = {}
    for example in examples:
        collections.setdefault(getattr(example, "collection", ""), []).append(example)
    assignment: dict[str, str] = {}
    for name in sorted(collections):
        assignment.update(
            iterative_stratification(
                [(example.example_id, example.values) for example in collections[name]], seed=seed
            )
        )
    parts = {name: [e for e in examples if assignment[e.example_id] == name] for name in PARTITIONS}
    empty = [name for name, part in parts.items() if not part]
    if empty:
        raise ValueError(
            f"{len(examples)} examples are too few for a 70/10/20 split: "
            f"{', '.join(empty)} would be empty."
        )
    return parts


def split_summary(parts: dict[str, list]) -> dict:
    return {
        name: {
            "examples": len(part),
            "without_values": sum(1 for example in part if not example.values),
            "collections": _collection_counts(part),
            "values": {
                value: count
                for value, count in sorted(
                    _value_counts(part).items(), key=lambda item: (-item[1], item[0])
                )
            },
        }
        for name, part in parts.items()
    }


def _collection_counts(examples) -> dict[str, int]:
    counts: dict[str, int] = {}
    for example in examples:
        name = getattr(example, "collection", "")
        counts[name] = counts.get(name, 0) + 1
    return dict(sorted(counts.items()))


def _value_counts(examples) -> dict[str, int]:
    counts: dict[str, int] = {}
    for example in examples:
        for value in example.values:
            counts[value] = counts.get(value, 0) + 1
    return counts
