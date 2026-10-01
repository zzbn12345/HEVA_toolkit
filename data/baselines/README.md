# Baseline training data

`python -m heva.baselines` reads its training data from this folder by default
(`--data-dir` points it elsewhere).

```
data/baselines/
├── heva/      HEVA Data Packages, one folder per package
│   └── <package>/heva-annotations.json   (heva-annotations.csv is used only if the JSON is missing)
└── atlasti/   Atlas.ti quotation exports (*.csv)
```

| Source | T1 sentence values | T2 BIO spans |
|---|---|---|
| HEVA Data Packages | yes (`values`, or `curated_sentence` text when set) | yes (`tokens`, `ner_tags`) |
| Atlas.ti CSV exports | yes (whole quotation) | no: quotations have no token spans |

## Atlas.ti exports

- Labels are read from the `Codes` column (`Value: Economic - Before` becomes
  `economic`). The per-value 0/1 columns of processed exports are ignored because
  they are 0 for quotations coded both Before and After.
- Quotations without any `Value:` code are kept as examples with no values.
- Identical quotations across several exports of one project are merged; their values
  are combined.
- Semicolon, comma or tab separated; UTF-8 or Windows-1252. A Quotation Manager export
  whose header row is unreadable (`????`) is read by Atlas.ti's column order.

## Commands

```bash
pip install -e ".[baselines]"
python -m heva.baselines inspect   # what was loaded, skipped, merged, and the 70/10/20 split
python -m heva.baselines t1        # sentence-level value classification
python -m heva.baselines t2        # value span extraction
```

Each run writes `runs/baselines/<task>/<timestamp>/` with `metrics.json`,
`thresholds.json`, `split.json`, `data.json`, `class_weights.json`, `config.json` and
`test_predictions.jsonl`.
