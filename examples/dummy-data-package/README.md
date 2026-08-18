# Dummy HEVA Data Package

This fictional two-document package illustrates the files researchers receive after a HEVA
project is validated and exported. It contains no research PDFs and no personal data.

Start with:

- `datapackage.json` for the dataset description and resources;
- `heva-annotations.json` for document metadata and canonical annotations;
- `heva-annotations.csv` for a flat analytical view;
- `build-log.json` for reproducibility and exclusions.

The same annotation appears in JSON and CSV. JSON is canonical; CSV is a generated
derivative. Follow [`docs/TUTORIAL.md`](../../docs/TUTORIAL.md) to recreate this shape with
new documents.
