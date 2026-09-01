# Tutorial: inspect and repair an example

This tutorial uses three examples:

- `examples/dummy-data-package/` is a finished distribution to inspect.
- `examples/complete-dummy-project/` is a complete workspace for validation and selected export.
- `examples/incomplete-dummy-project/` is working project state to open and validate.

Complete [Install and run HEVA](INSTALLATION.md) before continuing.

## 1. Inspect the intended result

Open `examples/dummy-data-package/`. Read `datapackage.json` first, then compare the canonical
`heva-annotations.json` with the flat `heva-annotations.csv` derivative.

## 2. Open the incomplete project

1. Start HEVA with `python -m heva.app`.
2. Open <http://127.0.0.1:8000>.
3. Choose **Open existing project**.
4. Select `examples/incomplete-dummy-project/`.

The example is deliberately incomplete. It lets validation explain what is absent without
modifying research data.

## 3. Run validation

Choose **Validate project**. The missing source and incomplete document records are expected
in this teaching example.

Run the same check from a terminal with:

```bash
python -m heva.workflow.package_validator examples/incomplete-dummy-project validate
```

## 4. Repeat with your documents

Return home, choose **Create from source folder**, and select a small folder of authorized PDF
or DOCX files. For each document:

1. review its citation;
2. discover its colors and assign HEVA labels;
3. extract the annotated sentences;
4. approve, correct, or exclude every sentence.

Run validation again. Resolve the reported findings before generating the Data Package.

## 5. Add a document to an existing project

Choose **Add document** from the project review queue. In the document setup screen, choose
one of the following source options:

- **Choose PDF (.pdf) or DOCX (.docx)** registers an external source without copying it into
	the project.
- **Import PDF into this project** copies the PDF into the project's managed `sources/`
	directory and updates the project registry. HEVA verifies the copy, reuses an already
	imported identical PDF, and gives a same-named but different PDF a distinct filename.

Both source choices are recorded in the project and remain available after restarting HEVA.
Managed source PDFs, like external sources, are never included in the generated Data Package.

## 6. Compare the result

Compare the generated files with `examples/dummy-data-package/`. Confirm that JSON preserves
the full structure, CSV provides the flat analytical view, and source documents or `.heva/`
working files are not included.

During alpha testing, record installation problems, extraction time, missed colors or text,
unclear validation findings, and whether the result is understandable without assistance.

If a PDF is scanned, contains a complex table, produces text in the wrong order, or is rejected
as unreadable, follow [Limitations and extraction troubleshooting](LIMITATIONS_AND_TROUBLESHOOTING.md).
