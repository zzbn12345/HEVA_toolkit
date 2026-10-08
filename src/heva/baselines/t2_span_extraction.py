"""T2: BIO tagging of value-bearing spans with mBERT, scored with exact-match span F1."""

from __future__ import annotations

import random
from pathlib import Path

import torch
from transformers import AutoModelForTokenClassification, AutoTokenizer

from .corpus import LoadReport, T2Example
from .labels import BIO_TAGS, TAG_TO_ID, VALUES
from .metrics import (
    THRESHOLD_GRID,
    overlap_span_scores,
    scores_by_collection,
    span_scores,
    t2_all_scores,
    token_scores,
)
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

IGNORE = -100


def tag_weights(examples: list[T2Example]) -> list[float]:
    """Balanced cross-entropy weights ``total / (present_tags * count)``; 1.0 if unseen."""
    counts = [0] * len(BIO_TAGS)
    for example in examples:
        for tag in example.tags:
            counts[TAG_TO_ID[tag]] += 1
    total, present = sum(counts), sum(1 for count in counts if count)
    return [total / (present * count) if count else 1.0 for count in counts]


def encode(tokenizer, batch: list[T2Example], max_length: int):
    """Tokenize pre-split words; only each word's first subtoken carries its tag.

    Returns the encoding, the label tensor and, per example, the subtoken position of
    each word (None when the word was truncated away).
    """
    words = [
        [token if token.strip() else tokenizer.unk_token for token in example.tokens]
        for example in batch
    ]
    encoding = tokenizer(
        words,
        is_split_into_words=True,
        truncation=True,
        max_length=max_length,
        padding=True,
        return_tensors="pt",
    )
    labels, positions = [], []
    for row, example in enumerate(batch):
        word_ids = encoding.word_ids(row)
        row_labels = [IGNORE] * len(word_ids)
        first = [None] * len(example.tokens)
        for position, word in enumerate(word_ids):
            if word is not None and first[word] is None:
                first[word] = position
                row_labels[position] = TAG_TO_ID[example.tags[word]]
        labels.append(row_labels)
        positions.append(first)
    return encoding, torch.tensor(labels), positions


def predict_word_probabilities(model, tokenizer, examples, config, device):
    """Per example, one tag-probability vector per word (None if truncated)."""
    model.eval()
    results = []
    with torch.no_grad():
        for batch in batches(examples, config.batch_size):
            encoding, _, positions = encode(tokenizer, batch, config.max_length)
            probabilities = torch.softmax(model(**encoding.to(device)).logits, dim=-1).cpu()
            for row, first in enumerate(positions):
                results.append(
                    [probabilities[row, p].tolist() if p is not None else None for p in first]
                )
    return results


def decode_argmax(word_probabilities) -> list[list[str]]:
    return [
        [BIO_TAGS[max(range(len(p)), key=p.__getitem__)] if p else "O" for p in sentence]
        for sentence in word_probabilities
    ]


def best_value_tags(word_probabilities):
    """Per word, the most probable non-``O`` tag and its probability (None if truncated)."""
    best = []
    for sentence in word_probabilities:
        row = []
        for p in sentence:
            if p is None:
                row.append(None)
                continue
            index = max(range(1, len(BIO_TAGS)), key=p.__getitem__)
            row.append((BIO_TAGS[index], p[index]))
        best.append(row)
    return best


def decode_with_thresholds(word_probabilities, thresholds: dict[str, float], best=None):
    """Tag a word with its most probable value tag when that probability reaches the
    value's threshold, otherwise ``O``."""
    best = best if best is not None else best_value_tags(word_probabilities)
    decoded = []
    for sentence in best:
        tags = []
        for candidate in sentence:
            if candidate is not None and candidate[1] >= thresholds[candidate[0][2:]]:
                tags.append(candidate[0])
            else:
                tags.append("O")
        decoded.append(tags)
    return decoded


def tune_span_thresholds(gold, word_probabilities, default: float = 0.5) -> dict[str, float]:
    """Per value, the threshold maximizing that value's validation span F1.

    Values are independent: a value's threshold only changes words whose most
    probable value tag is that value.
    """
    best = best_value_tags(word_probabilities)
    thresholds = {value: default for value in VALUES}
    for value in VALUES:
        if not any(tag.endswith(f"-{value}") for tags in gold for tag in tags):
            continue

        def f1_at(threshold: float) -> float:
            trial = {**thresholds, value: threshold}
            predicted = decode_with_thresholds(word_probabilities, trial, best)
            return span_scores(gold, predicted)["per_class"][value]["f1"]

        thresholds[value] = max(
            THRESHOLD_GRID, key=lambda threshold: (f1_at(threshold), -abs(threshold - default))
        )
    return thresholds


def run_t2(
    examples: list[T2Example],
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
    model = AutoModelForTokenClassification.from_pretrained(
        config.model_name,
        num_labels=len(BIO_TAGS),
        id2label=dict(enumerate(BIO_TAGS)),
        label2id=dict(TAG_TO_ID),
    ).to(device)

    weights = tag_weights(train)
    loss_fn = torch.nn.CrossEntropyLoss(
        weight=torch.tensor(weights, device=device), ignore_index=IGNORE
    )
    steps = config.epochs * -(-len(train) // config.batch_size)
    optimizer, scheduler = optimizer_and_scheduler(model, config, steps)
    rng = random.Random(config.seed)
    validation_gold = [list(example.tags) for example in validation]

    history, stopper = [], EarlyStopping(config.patience)
    for epoch in range(1, config.epochs + 1):
        model.train()
        total_loss = 0.0
        for batch in batches(train, config.batch_size, rng):
            encoding, labels, _ = encode(tokenizer, batch, config.max_length)
            logits = model(**encoding.to(device)).logits
            loss = loss_fn(logits.view(-1, len(BIO_TAGS)), labels.to(device).view(-1))
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()
            total_loss += loss.item() * len(batch)

        probabilities = predict_word_probabilities(model, tokenizer, validation, config, device)
        f1 = span_scores(validation_gold, decode_argmax(probabilities))["micro"]["f1"]
        history.append({"epoch": epoch, "train_loss": total_loss / len(train), "validation_span_f1": f1})
        print(f"[T2] epoch {epoch}: train loss {total_loss / len(train):.4f}, validation span F1 {f1:.4f}")
        if stopper.update(epoch, f1, model):
            print(f"[T2] no improvement for {config.patience} epochs; stopping")
            break

    model.load_state_dict(stopper.best_state)
    validation_probabilities = predict_word_probabilities(model, tokenizer, validation, config, device)
    thresholds = tune_span_thresholds(validation_gold, validation_probabilities)
    test_probabilities = predict_word_probabilities(model, tokenizer, test, config, device)
    test_gold = [list(example.tags) for example in test]
    test_predicted = decode_with_thresholds(test_probabilities, thresholds)
    test_argmax = decode_argmax(test_probabilities)
    truncated_words = sum(p is None for sentence in test_probabilities for p in sentence)

    metrics = {
        "best_epoch": stopper.best_epoch,
        "epochs_trained": len(history),
        "history": history,
        "validation_tuned": span_scores(
            validation_gold, decode_with_thresholds(validation_probabilities, thresholds)
        ),
        "test_argmax": span_scores(test_gold, test_argmax),
        "test_tuned": span_scores(test_gold, test_predicted),
        # Exact match is the main result; overlap and token scores credit predictions
        # whose boundaries differ from the annotators' highlights.
        "test_argmax_overlap": overlap_span_scores(test_gold, test_argmax),
        "test_tuned_overlap": overlap_span_scores(test_gold, test_predicted),
        "test_argmax_token": token_scores(test_gold, test_argmax),
        "test_tuned_token": token_scores(test_gold, test_predicted),
        "test_argmax_by_collection": scores_by_collection(test, test_gold, test_argmax, t2_all_scores),
        "test_tuned_by_collection": scores_by_collection(test, test_gold, test_predicted, t2_all_scores),
        "test_truncated_words": truncated_words,
    }

    run_dir = new_run_dir(output_dir, "t2")
    write_json(run_dir / "config.json", {**config.as_dict(), "device": str(device)})
    write_json(run_dir / "data.json", {"load_report": report.as_dict(), "split": split_summary(parts)})
    write_json(
        run_dir / "split.json",
        {name: [example.example_id for example in part] for name, part in parts.items()},
    )
    write_json(run_dir / "thresholds.json", thresholds)
    write_json(run_dir / "class_weights.json", dict(zip(BIO_TAGS, weights)))
    write_json(run_dir / "metrics.json", metrics)
    write_jsonl(
        run_dir / "test_predictions.jsonl",
        (
            {"id": example.example_id, "collection": example.collection, "tokens": list(example.tokens),
             "gold": gold, "predicted": predicted}
            for example, gold, predicted in zip(test, test_gold, test_predicted)
        ),
    )
    if save_model:
        model.save_pretrained(run_dir / "model")
        tokenizer.save_pretrained(run_dir / "model")
    return run_dir
