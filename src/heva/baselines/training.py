"""Shared fine-tuning utilities for the T1 and T2 mBERT baselines (requires torch)."""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import torch
from transformers import get_linear_schedule_with_warmup


@dataclass
class TrainingConfig:
    model_name: str = "bert-base-multilingual-cased"
    epochs: int = 20  # upper bound; early stopping usually ends training sooner
    patience: int = 3  # stop after this many epochs without a validation improvement
    batch_size: int = 16
    learning_rate: float = 2e-5
    weight_decay: float = 0.01
    warmup_ratio: float = 0.1
    max_length: int = 512  # BERT's position-embedding limit
    seed: int = 13
    device: str = "auto"

    def as_dict(self) -> dict:
        return asdict(self)


class EarlyStopping:
    """Track the best validation score and keep that epoch's weights."""

    def __init__(self, patience: int) -> None:
        self.patience = patience
        self.best_score = float("-inf")
        self.best_epoch = 0
        self.best_state = None
        self.epochs_without_improvement = 0

    def update(self, epoch: int, score: float, model) -> bool:
        """Record an epoch; return True when training should stop."""
        if score > self.best_score:
            self.best_score, self.best_epoch = score, epoch
            self.best_state = snapshot(model)
            self.epochs_without_improvement = 0
        else:
            self.epochs_without_improvement += 1
        return self.epochs_without_improvement >= self.patience


def effective_max_length(tokenizer, requested: int) -> int:
    """Never exceed what the model's position embeddings support (512 for mBERT)."""
    return min(requested, tokenizer.model_max_length)


def resolve_device(name: str) -> torch.device:
    if name != "auto":
        return torch.device(name)
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def set_seed(seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)


def batches(items: list, size: int, rng: random.Random | None = None):
    order = list(range(len(items)))
    if rng is not None:
        rng.shuffle(order)
    for start in range(0, len(order), size):
        yield [items[index] for index in order[start : start + size]]


def optimizer_and_scheduler(model, config: TrainingConfig, steps: int):
    no_decay = ("bias", "LayerNorm.weight")
    groups = [
        {
            "params": [p for n, p in model.named_parameters() if not any(k in n for k in no_decay)],
            "weight_decay": config.weight_decay,
        },
        {
            "params": [p for n, p in model.named_parameters() if any(k in n for k in no_decay)],
            "weight_decay": 0.0,
        },
    ]
    optimizer = torch.optim.AdamW(groups, lr=config.learning_rate)
    scheduler = get_linear_schedule_with_warmup(
        optimizer, int(steps * config.warmup_ratio), steps
    )
    return optimizer, scheduler


def snapshot(model) -> dict:
    """Copy weights to CPU so the best epoch survives later updates."""
    return {key: value.detach().to("cpu", copy=True) for key, value in model.state_dict().items()}


def new_run_dir(output_dir: Path, task: str) -> Path:
    run_dir = output_dir / task / datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
