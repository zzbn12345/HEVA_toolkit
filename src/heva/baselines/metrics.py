"""Evaluation for T1 (multi-label F1) and T2 (exact-match span F1)."""

from __future__ import annotations

from collections.abc import Sequence

from .labels import VALUES

THRESHOLD_GRID = tuple(round(0.05 * step, 2) for step in range(1, 20))


def _prf(tp: int, fp: int, fn: int) -> dict[str, float]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def _summarize(counts: dict[str, list[int]]) -> dict:
    """Per-class, micro and macro scores from {class: [tp, fp, fn]}.

    Macro averages only classes present in the gold data; absent classes are listed so
    a missing value is visible instead of silently scoring 0.
    """
    per_class = {
        name: {**_prf(tp, fp, fn), "support": tp + fn} for name, (tp, fp, fn) in counts.items()
    }
    totals = [sum(column) for column in zip(*counts.values())] if counts else [0, 0, 0]
    present = [name for name, scores in per_class.items() if scores["support"] > 0]
    macro = (
        {key: sum(per_class[name][key] for name in present) / len(present)
         for key in ("precision", "recall", "f1")}
        if present
        else {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    )
    return {
        "micro": _prf(*totals),
        "macro": macro,
        "per_class": per_class,
        "classes_without_support": [name for name in counts if name not in present],
    }


# --- T1 -------------------------------------------------------------------------------


def multilabel_scores(gold: Sequence[Sequence[int]], predicted: Sequence[Sequence[int]]) -> dict:
    """Score 0/1 label vectors in VALUES order.

    Besides F1, reports Hamming loss (share of wrong value decisions) and example-based
    Jaccard similarity (mean |gold ∩ predicted| / |gold ∪ predicted|; 1.0 when both are
    empty, since predicting "no value" for a text without values is fully correct).
    """
    counts = {value: [0, 0, 0] for value in VALUES}
    wrong_decisions, jaccard_total = 0, 0.0
    for gold_row, predicted_row in zip(gold, predicted, strict=True):
        for value, g, p in zip(VALUES, gold_row, predicted_row, strict=True):
            if g and p:
                counts[value][0] += 1
            elif p:
                counts[value][1] += 1
            elif g:
                counts[value][2] += 1
            wrong_decisions += bool(g) != bool(p)
        union = sum(1 for g, p in zip(gold_row, predicted_row) if g or p)
        both = sum(1 for g, p in zip(gold_row, predicted_row) if g and p)
        jaccard_total += both / union if union else 1.0
    rows = len(gold)
    return {
        **_summarize(counts),
        "hamming_loss": wrong_decisions / (rows * len(VALUES)) if rows else 0.0,
        "jaccard_samples": jaccard_total / rows if rows else 0.0,
    }


def apply_thresholds(probabilities: Sequence[Sequence[float]], thresholds: Sequence[float]):
    return [
        [1 if p >= t else 0 for p, t in zip(row, thresholds, strict=True)]
        for row in probabilities
    ]


def tune_thresholds(
    gold: Sequence[Sequence[int]],
    probabilities: Sequence[Sequence[float]],
    grid: Sequence[float] = THRESHOLD_GRID,
    default: float = 0.5,
) -> list[float]:
    """Pick, per class, the threshold maximizing that class's F1 on validation data.

    Classes without validation positives keep ``default``; ties keep the threshold
    closest to ``default``.
    """
    thresholds = []
    for column in range(len(VALUES)):
        gold_column = [row[column] for row in gold]
        if not any(gold_column):
            thresholds.append(default)
            continue
        scores = [column_row[column] for column_row in probabilities]
        best = max(
            grid,
            key=lambda threshold: (
                _f1_at(gold_column, scores, threshold),
                -abs(threshold - default),
            ),
        )
        thresholds.append(best)
    return thresholds


def _f1_at(gold: Sequence[int], scores: Sequence[float], threshold: float) -> float:
    tp = sum(1 for g, s in zip(gold, scores) if g and s >= threshold)
    fp = sum(1 for g, s in zip(gold, scores) if not g and s >= threshold)
    fn = sum(1 for g, s in zip(gold, scores) if g and s < threshold)
    return _prf(tp, fp, fn)["f1"]


# --- T2 -------------------------------------------------------------------------------


def bio_spans(tags: Sequence[str]) -> set[tuple[int, int, str]]:
    """Return ``(start, end_exclusive, value)`` spans using conlleval chunking rules.

    An ``I-x`` that does not continue a span of ``x`` starts a new span, so predictions
    with a missing ``B-`` are still scored rather than dropped.
    """
    spans = set()
    start, current = None, None
    for index, tag in enumerate([*tags, "O"]):
        prefix, _, value = tag.partition("-")
        continues = prefix == "I" and value == current
        if current is not None and not continues:
            spans.add((start, index, current))
            start, current = None, None
        if prefix in ("B", "I") and not continues:
            start, current = index, value
    return spans


def span_scores(
    gold: Sequence[Sequence[str]], predicted: Sequence[Sequence[str]]
) -> dict:
    """Exact-match span precision/recall/F1: boundaries and value must both match."""
    counts = {value: [0, 0, 0] for value in VALUES}
    for gold_tags, predicted_tags in zip(gold, predicted, strict=True):
        gold_spans, predicted_spans = bio_spans(gold_tags), bio_spans(predicted_tags)
        for *_, value in gold_spans & predicted_spans:
            counts[value][0] += 1
        for *_, value in predicted_spans - gold_spans:
            counts[value][1] += 1
        for *_, value in gold_spans - predicted_spans:
            counts[value][2] += 1
    return _summarize(counts)
