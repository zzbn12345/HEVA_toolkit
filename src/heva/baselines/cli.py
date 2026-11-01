"""Command line for the T1/T2 baselines.

    python -m heva.baselines inspect            # load data and show the split, no training
    python -m heva.baselines t1 [options]       # sentence-level value classification
    python -m heva.baselines t2 [options]       # value span extraction (BIO)
    python -m heva.baselines significance RUN   # confidence intervals and paired tests
    python -m heva.baselines significance RUN --split validation   # intervals on validation
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .corpus import load_t1_dataset, load_t2_dataset
from .splits import split_examples, split_summary

DEFAULT_DATA_DIR = Path("data/baselines")
DEFAULT_OUTPUT_DIR = Path("runs/baselines")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m heva.baselines", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR,
                        help="Folder with heva/ (Data Packages), structured/ (52-column spreadsheets) "
                             "and atlasti/ (CSV exports). "
                             f"Default: {DEFAULT_DATA_DIR}")
    common.add_argument("--seed", type=int, default=13, help="Seed for the split and training.")

    commands.add_parser("inspect", parents=[common], help="Load both datasets and print the split.")

    significance = commands.add_parser(
        "significance",
        help="Bootstrap confidence intervals and paired tests for saved runs.",
    )
    significance.add_argument("run_dirs", nargs="+", type=Path,
                              help="Run folders containing <split>_predictions.jsonl.")
    significance.add_argument("--split", choices=("test", "validation"), default="test",
                              help="Split to analyse; validation gets intervals only. Default: test")
    significance.add_argument("--resamples", type=int, default=1000,
                              help="Bootstrap resamples. Default: 1000")
    significance.add_argument("--seed", type=int, default=13, help="Seed for resampling.")

    for task, help_text in (("t1", "Sentence-level value classification."),
                            ("t2", "Value span extraction with BIO tags.")):
        sub = commands.add_parser(task, parents=[common], help=help_text)
        sub.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
        sub.add_argument("--model", default="bert-base-multilingual-cased",
                         help="Hugging Face model name or local path.")
        sub.add_argument("--epochs", type=int, default=20,
                         help="Maximum epochs; early stopping usually ends sooner. Default: 20")
        sub.add_argument("--patience", type=int, default=3,
                         help="Stop after this many epochs without validation improvement. Default: 3")
        sub.add_argument("--batch-size", type=int, default=8)
        sub.add_argument("--learning-rate", type=float, default=2e-5)
        sub.add_argument("--max-length", type=int, default=512,
                         help="Subword tokens per text, capped at the model's limit (512 for mBERT).")
        sub.add_argument("--device", default="auto", help="auto, cpu, cuda or mps.")
        sub.add_argument("--save-model", action="store_true",
                         help="Also save the fine-tuned model (about 700 MB for mBERT).")
    return parser


def _inspect(data_dir: Path, seed: int) -> None:
    for name, loader in (("T1", load_t1_dataset), ("T2", load_t2_dataset)):
        examples, report = loader(data_dir)
        print(f"== {name}: {len(examples)} examples")
        print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))
        if not examples:
            continue
        try:
            print(json.dumps(split_summary(split_examples(examples, seed)), indent=2))
        except ValueError as error:
            print(f"split: {error}")


def _significance(run_dirs: list[Path], resamples: int, seed: int, split: str) -> int:
    from .significance import analyse_run, significance_path

    for run_dir in run_dirs:
        try:
            result = analyse_run(run_dir, resamples, seed, split)
        except (OSError, ValueError) as error:
            print(error, file=sys.stderr)
            return 1
        print(f"== {run_dir} ({result['task'].upper()}, {result['examples']} {split} examples)")
        for rule, metrics in result["rules"].items():
            for metric, scores in metrics.items():
                if "f1/" in metric.replace("/micro_f1", "").replace("/macro_f1", ""):
                    continue
                low, high = scores["ci95"]
                print(f"  {rule:<12} {metric:<18} {scores['value']:.3f}  [{low:.3f}, {high:.3f}]")
        if "comparison" in result:
            print(f"  paired test, {result['comparison']['rules']}:")
            for metric, test in result["comparison"]["tests"].items():
                if "f1/" in metric.replace("/micro_f1", "").replace("/macro_f1", ""):
                    continue
                print(f"    {metric:<18} difference {test['difference']:+.3f}  "
                      f"p={test['p_value']:.3f}  p_holm={test['p_holm']:.3f}")
        if "note" in result:
            print(f"  note: {result['note']}")
        print(f"  saved {significance_path(run_dir, split)}")
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "inspect":
        _inspect(args.data_dir, args.seed)
        return 0
    if args.command == "significance":
        return _significance(args.run_dirs, args.resamples, args.seed, args.split)

    loader = load_t1_dataset if args.command == "t1" else load_t2_dataset
    examples, report = loader(args.data_dir)
    if not examples:
        print(f"No {args.command.upper()} examples found under {args.data_dir}. "
              "Put HEVA Data Packages in heva/, structured spreadsheets in structured/ "
              "and Atlas.ti CSVs in atlasti/.", file=sys.stderr)
        return 1

    # Imported here so `inspect` works without torch/transformers installed.
    from .training import TrainingConfig

    config = TrainingConfig(
        model_name=args.model,
        epochs=args.epochs,
        patience=args.patience,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        max_length=args.max_length,
        seed=args.seed,
        device=args.device,
    )
    if args.command == "t1":
        from .t1_classification import run_t1 as run
    else:
        from .t2_span_extraction import run_t2 as run
    try:
        run_dir = run(examples, report, config, args.output_dir, save_model=args.save_model)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    print(f"Results written to {run_dir}")
    return 0
