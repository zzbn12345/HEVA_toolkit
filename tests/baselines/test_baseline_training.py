"""End-to-end T1/T2 runs with a tiny randomly initialized BERT (skipped without torch)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

pytest.importorskip("torch")
transformers = pytest.importorskip("transformers")

from heva.baselines.cli import main  # noqa: E402
from heva.baselines.labels import BIO_TAGS, VALUES  # noqa: E402

DUMMY_PACKAGE = Path(__file__).parents[2] / "examples/dummy-data-package"


@pytest.fixture(scope="module")
def tiny_bert(tmp_path_factory) -> Path:
    """A 2-layer BERT whose vocabulary is the dummy package's own tokens."""
    directory = tmp_path_factory.mktemp("tiny-bert")
    package = json.loads((DUMMY_PACKAGE / "heva-annotations.json").read_text(encoding="utf-8"))
    words = sorted({token for document in package["documents"]
                    for record in document["records"] for token in record["tokens"]})
    vocab = ["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]", *words]
    (directory / "vocab.txt").write_text("\n".join(vocab) + "\n", encoding="utf-8")
    tokenizer = transformers.BertTokenizerFast(
        vocab_file=str(directory / "vocab.txt"), do_lower_case=False
    )
    config = transformers.BertConfig(
        vocab_size=len(vocab), hidden_size=32, num_hidden_layers=2,
        num_attention_heads=2, intermediate_size=64, max_position_embeddings=512,
    )
    transformers.BertModel(config).save_pretrained(directory)
    tokenizer.save_pretrained(directory)
    return directory


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    shutil.copytree(DUMMY_PACKAGE, tmp_path / "data" / "heva" / "release-1")
    return tmp_path / "data"


@pytest.mark.parametrize("task", ["t1", "t2"])
def test_baseline_run_writes_metrics_thresholds_and_predictions(
    task: str, tiny_bert: Path, data_dir: Path, tmp_path: Path
) -> None:
    output = tmp_path / "runs"

    exit_code = main([
        task, "--data-dir", str(data_dir), "--output-dir", str(output),
        "--model", str(tiny_bert), "--epochs", "2", "--batch-size", "8", "--device", "cpu",
    ])

    assert exit_code == 0
    (run_dir,) = (output / task).iterdir()
    metrics = json.loads((run_dir / "metrics.json").read_text())
    thresholds = json.loads((run_dir / "thresholds.json").read_text())
    split = json.loads((run_dir / "split.json").read_text())
    predictions = (run_dir / "test_predictions.jsonl").read_text().splitlines()

    assert [row["epoch"] for row in metrics["history"]] == [1, 2]
    assert set(metrics["test_tuned"]["per_class"]) == set(VALUES)
    assert set(thresholds) == set(VALUES)
    assert sum(len(ids) for ids in split.values()) == 92
    assert len(predictions) == len(split["test"])
    if task == "t2":
        first = json.loads(predictions[0])
        assert len(first["predicted"]) == len(first["tokens"])
        assert set(first["predicted"]) <= set(BIO_TAGS)


def test_training_reports_missing_data(tmp_path: Path, capsys) -> None:
    assert main(["t1", "--data-dir", str(tmp_path / "empty")]) == 1
    assert "No T1 examples found" in capsys.readouterr().err


def test_early_stopping_keeps_best_epoch_and_stops_after_patience() -> None:
    import torch

    from heva.baselines.training import EarlyStopping

    model = torch.nn.Linear(1, 1)
    stopper = EarlyStopping(patience=3)
    scores = [0.2, 0.5, 0.4, 0.5, 0.3]

    stops = [stopper.update(epoch, score, model) for epoch, score in enumerate(scores, start=1)]

    assert stops == [False, False, False, False, True]
    assert stopper.best_epoch == 2
    assert stopper.best_score == 0.5
