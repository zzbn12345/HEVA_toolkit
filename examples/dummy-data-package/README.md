# Dummy HEVA Data Package

This fictional two-document package shows the files researchers receive after a HEVA project
is validated and exported. It contains no research PDFs and no personal data.

Start with:

- `datapackage.json` for the dataset description, resources and the value sets the labels
  come from;
- `heva-annotations.json` for document metadata and canonical annotations;
- `heva-annotations.csv` for a flat analytical view;
- `build-log.json` for reproducibility and exclusions.

The same annotations appear in JSON and CSV. JSON is canonical; CSV is a generated
derivative. The [user guide](../../docs/USER_GUIDE.md#11-what-is-inside-the-data-package)
explains every file and field, and [`docs/TUTORIAL.md`](../../docs/TUTORIAL.md) shows how to
create this shape with new documents.

## How this package was made

It is the real exporter's output for [`examples/complete-dummy-project/`](../complete-dummy-project/).
To regenerate it after the export format changes, export a copy of that project, so the
example project itself stays unchanged:

```bash
cp -R examples/complete-dummy-project /tmp/complete-dummy-project
python -m heva.curation.package_validator /tmp/complete-dummy-project release
cp /tmp/complete-dummy-project/exports/heva-data-package/* examples/dummy-data-package/
```
