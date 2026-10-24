"""Bootstrap confidence intervals and paired tests for saved baseline runs (no torch needed)."""

from __future__ import annotations

import json
from pathlib import Path

from heva.baselines.labels import VALUES
from heva.baselines.significance import analyse_run, holm


def write_predictions(run_dir: Path, rows: list[dict]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "test_predictions.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )


def t1_row(gold: list[str], tuned: list[str], above_half: list[str]) -> dict:
    probabilities = {value: (0.9 if value in above_half else 0.1) for value in VALUES}
    return {"id": "x", "text": "t", "gold": gold, "predicted": tuned, "probabilities": probabilities}


def test_holm_adjusts_in_order_and_stays_monotone() -> None:
    adjusted = holm({"a": 0.01, "b": 0.04, "c": 0.03})

    assert adjusted == {"a": 0.03, "c": 0.06, "b": 0.06}


def test_identical_rules_are_not_significantly_different(tmp_path: Path) -> None:
    rows = [t1_row(["social"], ["social"], ["social"]), t1_row(["age"], [], [])] * 20
    write_predictions(tmp_path, rows)

    result = analyse_run(tmp_path, resamples=200)

    test = result["comparison"]["tests"]["micro_f1"]
    assert test["difference"] == 0.0
    assert test["p_value"] == 1.0
    low, high = result["rules"]["tuned"]["micro_f1"]["ci95"]
    assert low <= result["rules"]["tuned"]["micro_f1"]["value"] <= high
    assert (tmp_path / "significance.json").exists()


def test_a_clearly_better_rule_is_significant(tmp_path: Path) -> None:
    rows = [t1_row(["social"], ["social"], []) for _ in range(40)]
    write_predictions(tmp_path, rows)

    result = analyse_run(tmp_path, resamples=200)

    test = result["comparison"]["tests"]["micro_f1"]
    assert result["comparison"]["rules"] == "tuned minus default_0.5"
    assert test["difference"] == 1.0
    assert test["p_value"] < 0.01
    assert "p_holm" in result["comparison"]["tests"]["f1/social"]


def test_t2_runs_without_argmax_predictions_get_intervals_only(tmp_path: Path) -> None:
    row = {"id": "x", "tokens": ["a", "b"], "gold": ["B-age", "O"], "predicted": ["B-age", "O"]}
    write_predictions(tmp_path, [row] * 10)

    result = analyse_run(tmp_path, resamples=50)

    assert result["task"] == "t2"
    assert result["rules"]["tuned"]["exact/micro_f1"]["value"] == 1.0
    assert "comparison" not in result
    assert "re-run T2" in result["note"]


def test_t2_compares_tuned_with_argmax(tmp_path: Path) -> None:
    good = {"gold": ["B-age", "I-age", "O"], "predicted": ["B-age", "I-age", "O"],
            "predicted_argmax": ["B-age", "O", "O"]}
    write_predictions(tmp_path, [{"id": "x", "tokens": ["a", "b", "c"], **good}] * 30)

    result = analyse_run(tmp_path, resamples=100)

    tests = result["comparison"]["tests"]
    assert tests["exact/micro_f1"]["difference"] == 1.0
    assert 0 < tests["overlap/micro_f1"]["p_value"] <= 1
    assert tests["token/micro_f1"]["difference"] > 0
