# HEVA: a dataset, toolkit and benchmark for heritage value extraction

HEVA (HEritage Value extraction and Annotation) is an open resource for finding the values that
people attach to cultural heritage in text. It brings together expert annotations made under the
eight categories of the Cultural Value Framework (CVF): social, economic, political, historic,
aesthetical, scientific, age and ecological.

It accompanies the paper *HEVA: A Dataset, Toolkit and Benchmark for Heritage Value Extraction*
(submitted to ECIR 2027). This repository has three parts:

| Part | What it is | Start here |
|---|---|---|
| **1. Dataset** | 6,324 text units from 8 collections and 197 sources in English, Dutch and Chinese; 1,017 sentences also have token-level value spans | To be added |
| **2. Benchmark** | Value classification (T1) and value span extraction (T2), with mBERT baselines and results | [`benchmark/`](benchmark/README.md) |
| **3. Annotation app** | Local software that turns colour-highlighted PDF and Word documents into validated, provenance-preserving Data Packages | [`app/`](app/README.md) |

## Quick start

Start the app:

```bash
conda env create -f environment.yml
conda activate heva-toolkit
python -m heva.app
```

See [`benchmark/`](benchmark/README.md) for how to run the baselines.

## Repository layout

```
benchmark/  tasks and baseline results
app/        guide to the annotation app
src/heva/   code: app, curation, extraction, baselines
docs/       toolkit documentation          schemas/   JSON schemas
examples/   dummy projects and packages    tests/     test suite
```

## Citation and licences

See [`CITATION.cff`](CITATION.cff). The code is released under the [MIT licence](LICENSE).

## Acknowledgments

We acknowledge the support of the TU Delft Digital Competence Center in advancing this project.
