"""T1: sentence-level multi-label classification of the eight CVF values with mBERT."""

from __future__ import annotations

import random
from pathlib import Path

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from .corpus import LoadReport, T1Example
from .labels import VALUES, encode_values
from .metrics import apply_thresholds, multilabel_scores, tune_thresholds
from .splits import split_examples, split_summary
from .training import (
    EarlyStopping,
    TrainingConfig,
    batches,
    effective_max_length,
    new_run_dir,
    optimizer_and_scheduler,
    resolve_device,
    set_seed,
    write_json,
    write_jsonl,
)


def positive_weights(examples: list[T1Example]) -> list[float]:
    """BCE ``pos_weight`` = negatives / positives per value; 1.0 for unseen values."""
    total = len(examples)
    weights = []
    for index in range(len(VALUES)):
        positives = sum(encode_values(example.values)[index] for example in examples)
        weights.append((total - positives) / positives if positives else 1.0)
    return weights


def predict_probabilities(model, tokenizer, examples, config, device) -> list[list[float]]:
    model.eval()
    probabilities = []
    with torch.no_grad():
        for batch in batches(examples, config.batch_size):
            inputs = tokenizer(
                [example.text for example in batch],
                truncation=True,
                max_length=config.max_length,
                padding=True,
                return_tensors="pt",
            ).to(device)
            probabilities.extend(torch.sigmoid(model(**inputs).logits).cpu().tolist())
    return probabilities


def run_t1(
    examples: list[T1Example],
    report: LoadReport,
    config: TrainingConfig,
    output_dir: Path,
    save_model: bool = False,
) -> Path:
    """Fine-tune, select the best epoch on validation, tune thresholds, score test."""
    set_seed(config.seed)
    device = resolve_device(config.device)
    parts = split_examples(examples, config.seed)
    train, validation, test = parts["train"], parts["validation"], parts["test"]

    tokenizer = AutoTokenizer.from_pretrained(config.model_name)
    config.max_length = effective_max_length(tokenizer, config.max_length)
    model = AutoModelForSequenceClassification.from_pretrained(
        config.model_name,
        num_labels=len(VALUES),
        problem_type="multi_label_classification",
        id2label=dict(enumerate(VALUES)),
        label2id={value: index for index, value in enumerate(VALUES)},
    ).to(device)

    pos_weight = positive_weights(train)
    loss_fn = torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor(pos_weight, device=device))
    steps = config.epochs * -(-len(train) // config.batch_size)
    optimizer, scheduler = optimizer_and_scheduler(model, config, steps)
    rng = random.Random(config.seed)
    validation_gold = [encode_values(example.values) for example in validation]

    history, stopper = [], EarlyStopping(config.patience)
    for epoch in range(1, config.epochs + 1):
        model.train()
        total_loss = 0.0
        for batch in batches(train, config.batch_size, rng):
            inputs = tokenizer(
                [example.text for example in batch],
                truncation=True,
                max_length=config.max_length,
                padding=True,
                return_tensors="pt",
            ).to(device)
            targets = torch.tensor(
                [encode_values(example.values) for example in batch],
                dtype=torch.float,
                device=device,
            )
            loss = loss_fn(model(**inputs).logits, targets)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()
            total_loss += loss.item() * len(batch)

        probabilities = predict_probabilities(model, tokenizer, validation, config, device)
        f1 = multilabel_scores(
            validation_gold, apply_thresholds(probabilities, [0.5] * len(VALUES))
        )["micro"]["f1"]
        history.append({"epoch": epoch, "train_loss": total_loss / len(train), "validation_micro_f1": f1})
        print(f"[T1] epoch {epoch}: train loss {total_loss / len(train):.4f}, validation micro-F1 {f1:.4f}")
        if stopper.update(epoch, f1, model):
            print(f"[T1] no improvement for {config.patience} epochs; stopping")
            break

    model.load_state_dict(stopper.best_state)
    validation_probabilities = predict_probabilities(model, tokenizer, validation, config, device)
    thresholds = tune_thresholds(validation_gold, validation_probabilities)
    test_probabilities = predict_probabilities(model, tokenizer, test, config, device)
    test_gold = [encode_values(example.values) for example in test]
    test_predicted = apply_thresholds(test_probabilities, thresholds)

    metrics = {
        "best_epoch": stopper.best_epoch,
        "epochs_trained": len(history),
        "history": history,
        "validation_tuned": multilabel_scores(
            validation_gold, apply_thresholds(validation_probabilities, thresholds)
        ),
        "test_default_0.5": multilabel_scores(
            test_gold, apply_thresholds(test_probabilities, [0.5] * len(VALUES))
        ),
        "test_tuned": multilabel_scores(test_gold, test_predicted),
        "truncated_texts": {
            name: sum(
                len(tokenizer(example.text)["input_ids"]) > config.max_length for example in part
            )
            for name, part in parts.items()
        },
    }

    run_dir = new_run_dir(output_dir, "t1")
    write_json(run_dir / "config.json", {**config.as_dict(), "device": str(device)})
    write_json(run_dir / "data.json", {"load_report": report.as_dict(), "split": split_summary(parts)})
    write_json(
        run_dir / "split.json",
        {name: [example.example_id for example in part] for name, part in parts.items()},
    )
    write_json(run_dir / "thresholds.json", dict(zip(VALUES, thresholds)))
    write_json(run_dir / "class_weights.json", dict(zip(VALUES, pos_weight)))
    write_json(run_dir / "metrics.json", metrics)
    write_jsonl(
        run_dir / "test_predictions.jsonl",
        (
            {
                "id": example.example_id,
                "source": example.source,
                "text": example.text,
                "gold": list(example.values),
                "predicted": [value for value, flag in zip(VALUES, predicted) if flag],
                "probabilities": dict(zip(VALUES, (round(p, 4) for p in probabilities))),
            }
            for example, predicted, probabilities in zip(test, test_predicted, test_probabilities)
        ),
    )
    if save_model:
        model.save_pretrained(run_dir / "model")
        tokenizer.save_pretrained(run_dir / "model")
    return run_dir
