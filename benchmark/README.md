# The HEVA benchmark

Two tasks over the eight CVF values, with fixed splits, mBERT baselines and their results.

## 1. Tasks and data

**T1, value classification.** Assign a text unit the subset of the eight values it expresses, which
may be empty (multi-label classification).

**T2, value span extraction.** Label each token of a sentence with one of 17 BIO tags: `O`, or `B-`
or `I-` for each value. T2 uses only the highlighted sentences, the only units with spans.

Each collection is split 70/10/20 with iterative stratification (split seed 13). Identical texts are
merged, so that none appears in both training and test data.

| Task | Train | Validation | Test | Total |
|---|---:|---:|---:|---:|
| T1 texts | 3,696 | 521 | 1,063 | 5,280 |
| T2 sentences | 680 | 92 | 189 | 961 |

The two tasks are split separately, so a highlighted sentence can be in T1's training set and T2's
test set, so don't combine the two tasks' splits when training one model on both.

**Loading a split:**

```python
from datasets import load_dataset  # pip install datasets

t1 = load_dataset("json", data_files={
    "train": "benchmark/t1/train.jsonl",
    "validation": "benchmark/t1/validation.jsonl",
    "test": "benchmark/t1/test.jsonl",
})
```

Or without any dependency:

```python
import json

def load_split(task, split):
    with open(f"benchmark/{task}/{split}.jsonl", encoding="utf-8") as lines:
        return [json.loads(line) for line in lines]

test = load_split("t2", "test")
```

**Fields:**

- T1: `{"id", "text", "values", "source", "document", "collection"}`, where `values` may be `[]`.
- T2: `{"id", "tokens", "tags", "document", "collection"}`, with one tag per token.

## 2. Metrics and models

**T1:** micro- and macro-F1, per-value F1, Hamming loss and example-based Jaccard index.
**T2:** exact-match span F1, overlap span F1 (a predicted span overlapping a gold span of the same
value counts) and token F1. Each baseline is trained with seeds 13, 14 and 15 on the same split.

**Model:** multilingual BERT (`bert-base-multilingual-cased`) with a linear layer: one sigmoid output
per value on `[CLS]` for T1, and a 17-way softmax per subword for T2. AdamW, learning rate 2e-5,
weight decay 0.01, batch size 8, at most 20 epochs, stopping after three epochs without validation
improvement, inputs of up to 512 subwords. T1 predicts a value at probability 0.5; T2 takes the most
probable tag.

```bash
pip install -e ".[baselines]"
python -m heva.baselines t1 --seed 13 --save-model
python -m heva.baselines t2 --seed 13 --save-model
```

Training on Apple's MPS backend isn't bit-for-bit reproducible, so rerunning gives slightly different
scores. Use the trained models below to reproduce the reported ones exactly. See the
[baselines guide](../src/heva/baselines/README.md) for all options.

**Trained models.** The six trained models are on
[Hugging Face](https://huggingface.co/ValantisAndreas/heva-baselines) (about 700 MB each), in the same
folders as their runs here. This folder keeps each run's tokenizer and model configuration, but not
the weights.

```python
from transformers import AutoModelForSequenceClassification, AutoTokenizer

repo = "ValantisAndreas/heva-baselines"
folder = "t1/20261102-144928/model"
tokenizer = AutoTokenizer.from_pretrained(repo, subfolder=folder)
model = AutoModelForSequenceClassification.from_pretrained(repo, subfolder=folder)
```

For T2, use `AutoModelForTokenClassification` with a `t2/...` folder.

| Task | Seed | Run (the model is in `<run>/model`) |
|---|---|---|
| T1 | 13 | `results/t1/20261102-144928` |
| T1 | 14 | `results/t1/20261102-152545` |
| T1 | 15 | `results/t1/20261102-160931` |
| T2 | 13 | `results/t2/20261102-134010` |
| T2 | 14 | `results/t2/20261102-135455` |
| T2 | 15 | `results/t2/20261102-140246` |

## 3. Results

Mean ± standard deviation over the three seeds. Higher is better, except for Hamming loss.

| T1 | Micro-F1 | Macro-F1 | Hamming loss | Jaccard index |
|---|---|---|---|---|
| Test | .747 ± .010 | .727 ± .010 | .087 ± .004 | .741 ± .008 |
| Validation | .766 ± .004 | .753 ± .005 | .081 ± .003 | .759 ± .005 |

| T2 | Span micro-F1 | Span macro-F1 | Overlap F1 | Token F1 |
|---|---|---|---|---|
| Test | .285 ± .016 | .229 ± .019 | .551 ± .024 | .542 ± .002 |
| Validation | .284 ± .017 | .228 ± .019 | .528 ± .019 | .532 ± .005 |

Per-value test F1 (T2: exact span F1):

| | Soc | Eco | Pol | His | Aes | Sci | Age | Ecol |
|---|---|---|---|---|---|---|---|---|
| T1 | .70 | .72 | .63 | .75 | .67 | .75 | .70 | .90 |
| T2 | .34 | .47 | .12 | .20 | .19 | .02 | .28 | .20 |

**Each run folder in `results/` contains:** `config.json`, `data.json`, `split.json`, `thresholds.json`,
`class_weights.json`, `metrics.json` (scores overall and per collection, for test and validation),
`significance.json` and `significance_validation.json` (bootstrap confidence intervals, and paired
tests against tuned thresholds on test), and `test_predictions.jsonl` and `validation_predictions.jsonl`.
