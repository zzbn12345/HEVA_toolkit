"""Bootstrap confidence intervals and paired significance tests for saved baseline runs.

Works from a run folder's ``test_predictions.jsonl`` (or ``validation_predictions.jsonl``),
so no model is needed. Texts are resampled with replacement (Efron & Tibshirani, 1993);
every metric is recomputed on each resample, which gives 95% percentile confidence
intervals. On test, the two decision rules of a run (T1: threshold 0.5 vs. tuned
thresholds; T2: most probable tag vs. tuned thresholds) are compared with the paired
bootstrap test (Berg-Kirkpatrick, Burkett & Klein, 2012), and p-values within a family of
tests are adjusted with Holm (1979). On validation, where the thresholds were tuned, only
confidence intervals are computed.
"""

from __future__ import annotations

import json
import random
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path

from .labels import VALUES, encode_values
from .metrics import (
    add_counts,
    multilabel_example_counts,
    overlap_example_counts,
    span_example_counts,
    summarize_counts,
    summarize_multilabel,
    token_example_counts,
)

DEFAULT_RESAMPLES = 1000
# Metrics where a lower value is better; differences are reported as tuned minus untuned.
LOWER_IS_BETTER = {"hamming_loss"}


# --- Per-example statistics ------------------------------------------------------------


def _t1_rows(predictions: list[dict]) -> dict[str, list]:
    """Per text and decision rule, the counts T1 metrics are computed from."""
    rules = {"default_0.5": [], "tuned": []}
    for row in predictions:
        gold = encode_values(row["gold"])
        default = encode_values(
            [value for value, probability in row["probabilities"].items() if probability >= 0.5]
        )
        rules["default_0.5"].append(multilabel_example_counts(gold, default))
        rules["tuned"].append(multilabel_example_counts(gold, encode_values(row["predicted"])))
    return rules


def _t1_metrics(rows: Sequence) -> dict[str, float]:
    scores = summarize_multilabel(rows)
    metrics = {
        "micro_f1": scores["micro"]["f1"],
        "macro_f1": scores["macro"]["f1"],
        "hamming_loss": scores["hamming_loss"],
        "jaccard": scores["jaccard_samples"],
    }
    metrics.update({f"f1/{value}": scores["per_class"][value]["f1"] for value in VALUES})
    return metrics


T2_COUNTERS = {
    "exact": span_example_counts,
    "overlap": overlap_example_counts,
    "token": token_example_counts,
}


def _t2_rows(predictions: list[dict]) -> dict[str, list]:
    rules = {"tuned": "predicted", "argmax": "predicted_argmax"}
    available = {name: key for name, key in rules.items() if all(key in row for row in predictions)}
    return {
        name: [
            {kind: counter(row["gold"], row[key]) for kind, counter in T2_COUNTERS.items()}
            for row in predictions
        ]
        for name, key in available.items()
    }


def _t2_metrics(rows: Sequence[dict]) -> dict[str, float]:
    metrics = {}
    for kind in T2_COUNTERS:
        scores = summarize_counts(add_counts(row[kind] for row in rows))
        metrics[f"{kind}/micro_f1"] = scores["micro"]["f1"]
        metrics[f"{kind}/macro_f1"] = scores["macro"]["f1"]
        if kind == "exact":
            metrics.update({f"exact/f1/{value}": scores["per_class"][value]["f1"] for value in VALUES})
    return metrics


# --- Bootstrap -------------------------------------------------------------------------


def _expand(rows: Sequence, weights: Counter) -> list:
    return [rows[index] for index, count in weights.items() for _ in range(count)]


def _percentile(sorted_values: list[float], fraction: float) -> float:
    position = fraction * (len(sorted_values) - 1)
    low = int(position)
    high = min(low + 1, len(sorted_values) - 1)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (position - low)


def holm(p_values: dict[str, float]) -> dict[str, float]:
    """Holm-Bonferroni adjusted p-values (monotone, capped at 1)."""
    ordered = sorted(p_values.items(), key=lambda item: item[1])
    adjusted, running = {}, 0.0
    for rank, (name, p) in enumerate(ordered):
        running = max(running, min(1.0, (len(ordered) - rank) * p))
        adjusted[name] = running
    return adjusted


def bootstrap(
    rules: dict[str, list],
    metric_fn: Callable[[Sequence], dict[str, float]],
    compare: tuple[str, str] | None,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = 13,
) -> dict:
    """Confidence intervals per rule and, if ``compare`` is given, a paired test.

    The same resampled texts are used for every rule, which makes the comparison paired.
    The two-sided p-value is the share of resamples whose difference deviates from the
    observed difference by at least the observed difference itself (Berg-Kirkpatrick et
    al., 2012), with add-one smoothing so it is never exactly 0.
    """
    n = len(next(iter(rules.values())))
    rng = random.Random(seed)
    observed = {name: metric_fn(rows) for name, rows in rules.items()}
    samples = {name: {metric: [] for metric in observed[name]} for name in rules}
    for _ in range(resamples):
        weights = Counter(rng.randrange(n) for _ in range(n))
        for name, rows in rules.items():
            for metric, value in metric_fn(_expand(rows, weights)).items():
                samples[name][metric].append(value)

    result = {
        "examples": n,
        "resamples": resamples,
        "seed": seed,
        "rules": {
            name: {
                metric: {
                    "value": observed[name][metric],
                    "ci95": [
                        _percentile(sorted(values), 0.025),
                        _percentile(sorted(values), 0.975),
                    ],
                }
                for metric, values in samples[name].items()
            }
            for name in rules
        },
    }
    if compare and all(name in rules for name in compare):
        first, second = compare
        tests = {}
        for metric in observed[first]:
            delta = observed[first][metric] - observed[second][metric]
            deltas = [a - b for a, b in zip(samples[first][metric], samples[second][metric])]
            extreme = sum(abs(d - delta) >= abs(delta) for d in deltas)
            tests[metric] = {
                "difference": delta,
                "difference_ci95": [_percentile(sorted(deltas), 0.025), _percentile(sorted(deltas), 0.975)],
                "p_value": (extreme + 1) / (resamples + 1),
                "lower_is_better": metric in LOWER_IS_BETTER,
            }
        for family in (
            [m for m in tests if "/f1/" not in m and not m.startswith("f1/")],
            [m for m in tests if "/f1/" in m or m.startswith("f1/")],
        ):
            for metric, p in holm({m: tests[m]["p_value"] for m in family}).items():
                tests[metric]["p_holm"] = p
        result["comparison"] = {"rules": f"{first} minus {second}", "tests": tests}
    return result


SPLITS = ("test", "validation")


def significance_path(run_dir: Path, split: str = "test") -> Path:
    return run_dir / ("significance.json" if split == "test" else f"significance_{split}.json")


def analyse_run(
    run_dir: Path, resamples: int = DEFAULT_RESAMPLES, seed: int = 13, split: str = "test"
) -> dict:
    """Bootstrap one split of a saved T1 or T2 run and write the result into the run.

    The test split is written to ``significance.json`` and includes the paired test of the
    two decision rules; the validation split, on which the thresholds were tuned, gets
    confidence intervals only, in ``significance_validation.json``.
    """
    if split not in SPLITS:
        raise ValueError(f"Unknown split {split!r}; use one of {', '.join(SPLITS)}.")
    path = run_dir / f"{split}_predictions.jsonl"
    if not path.exists():
        raise ValueError(f"{run_dir}: {path.name} not found; re-run the task to save it.")
    predictions = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    if not predictions:
        raise ValueError(f"{run_dir}: {path.name} is empty.")
    if "probabilities" in predictions[0]:
        task, rules, metric_fn, compare = "t1", _t1_rows(predictions), _t1_metrics, ("tuned", "default_0.5")
    else:
        task, rules, metric_fn, compare = "t2", _t2_rows(predictions), _t2_metrics, ("tuned", "argmax")
    result = bootstrap(rules, metric_fn, compare if split == "test" else None, resamples, seed)
    if task == "t2" and "argmax" not in rules:
        result["note"] = (
            "This run saved only tuned predictions; re-run T2 to compare decision rules."
        )
    result = {"task": task, "split": split, **result}
    significance_path(run_dir, split).write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return result
