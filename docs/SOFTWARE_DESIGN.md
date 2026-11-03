# Software design

HEVA separates the research workflow from the user interface. Validation and extraction can
therefore run without opening the web app.

## Repository structure

```text
HEVA_toolkit/
├── data/           the released dataset
├── benchmark/      T1 and T2 split files, baseline results and their guide
├── app/            guide to the annotation app
├── src/heva/       source code
├── schemas/        machine-readable HEVA rules and vocabulary
├── examples/       finished and incomplete teaching datasets
├── docs/           the annotation app's documentation
├── tests/          automated checks of expected behaviour
└── environment.yml Conda installation definition
```

Most development happens under `src/heva/`:

```text
src/heva/
├── extraction/   reads PDF/DOCX text, highlights, and colors
├── curation/     stores curation state, validates it, and builds Data Packages
├── app/          presents the curation workflow through FastAPI and the browser
├── baselines/    trains and evaluates the T1 and T2 benchmark models
└── doctor.py     checks whether the installation is ready
```

## Extraction layer

Extraction records what the source contains: text, locations, and colors. It does not decide
that a color has a universal HEVA meaning. A researcher reviews that mapping.

## Curation and validation layer

This is the core of HEVA. It manages durable project records, validates them against the
schemas and HEVA relationships, and builds the distributable Data Package.

## Command-line access

The curation modules can be used from a terminal without the browser. For example:

```bash
python -m heva.curation.package_validator /path/to/project validate
```

This is currently script interoperability rather than a large standalone CLI utility.

## App layer

The optional FastAPI app guides a user through the same services and shows source documents
beside their records. It does not implement a second data model.

In short: **extraction observes, curation validates and packages, and the app guides the
user**. This separation keeps the HEVA specification useful even if the interface changes.
