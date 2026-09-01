# HEVA Toolkit

HEVA turns color-annotated PDF and DOCX documents into a structured, validated heritage
annotation Data Package. It runs locally so research source documents remain under the
user's control.

## Install and run

Install [Miniforge](https://github.com/conda-forge/miniforge), open its prompt or a terminal
in this repository, and run:

```bash
conda env create -f environment.yml
conda activate heva-toolkit
python -m heva.doctor --require app --require extraction
python -m heva.app
```

Open <http://127.0.0.1:8000>. Stop it with **Stop HEVA** in the project header or
**Ctrl+C** in the terminal.

For an existing environment:

```bash
conda env update -f environment.yml --prune
conda activate heva-toolkit
```

See [Install and run HEVA](docs/INSTALLATION.md) for Windows, macOS, Linux, and
troubleshooting details.

For unreadable PDFs, scans, and complex tables, see
[Limitations and extraction troubleshooting](docs/LIMITATIONS_AND_TROUBLESHOOTING.md).

## Alpha workflow

1. Open or create a project from a folder containing PDF/DOCX sources.
2. Review document citation details.
3. Discover each document's hex colors and assign HEVA labels.
4. Extract and review annotated sentences beside the source PDF.
5. Run validation and resolve the reported findings.
6. Generate the Data Package when its configured export gates pass.

The alpha is currently evaluated around extraction, supervised mapping, sentence review,
and validation. Curator approval, data-owner approval, and publication governance remain
future product decisions rather than steps in the main tutorial.

## Run validation

Use **Run validation** in the app, or run:

```bash
python -m heva.workflow.package_validator /path/to/project validate
```

Validation checks structure and HEVA relationships. A passing result means the project
conforms to the current specification; it does not prove scholarly correctness or that the
extractor found every source annotation.

See [HEVA and validation](docs/HEVA_AND_VALIDATION.md).

## What is the result?

A HEVA Data Package contains:

- `datapackage.json` — dataset identity and resource manifest;
- `heva-annotations.json` — canonical metadata and annotations grouped by document;
- `heva-annotations.csv` — flat analytical derivative;
- `build-log.json` — reproducibility and exclusion information.

Source documents and hidden application workspace files are excluded. Read
[What is a HEVA Data Package?](docs/DATA_PACKAGE.md) and inspect the
[dummy Data Package](examples/dummy-data-package/README.md).

## Tutorial

Follow [Create a validated Data Package](docs/TUTORIAL.md) to reproduce the dummy result
with a new authorized set of documents.

## Heritage labels

The current controlled top-level HEVA labels are:

`social`, `economic`, `political`, `historic`, `aesthetical`, `scientific`, `age`, and
`ecological`.

Document colors are evidence, not universal label identifiers. Every hex-to-label mapping
must be reviewed for the annotation protocol being processed.

## Developers

The code is separated into:

- `src/heva/extraction` — PDF/DOCX and NLP adapters;
- `src/heva/workflow` — project state, validation, and Data Package services;
- `src/heva/app` — optional FastAPI interface.

Run the full test suite in the Conda environment:

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

The complete documentation is intentionally limited to six short pages listed in
[`docs/index.md`](docs/index.md).
