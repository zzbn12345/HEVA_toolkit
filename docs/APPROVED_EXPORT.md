# Package validation and approved export

HEVA uses one layered validator as the gate between working annotation packages and
release files. A successful record-contract check alone is not enough: the package must
also refer to the current source, use an approved color mapping, contain complete sentence
decisions, and state its provenance and distribution rights.

Validate one document:

```bash
./venv/bin/python -m heva.workflow.package_validator . validate \
  --document-id HEVA-EXAMPLE
```

Validate the whole project:

```bash
./venv/bin/python -m heva.workflow.package_validator . validate \
  --report data/validation-report.json
```

The command exits with status `1` if it finds a blocking error. Each issue has a stable
code, severity, document ID, JSON path, plain-language explanation, and suggested action.
Warnings remain visible but do not block approval.

## Approval and release

After an annotator submits a fully decided document, its registry status is `in_review`.
A curator can approve it only if every validation layer passes:

```bash
./venv/bin/python -m heva.workflow.package_validator . approve \
  --document-id HEVA-EXAMPLE
```

Approval changes the status to `done`. Build the release representations with:

```bash
./venv/bin/python -m heva.workflow.package_validator . release
```

This creates:

```text
data/release/
├── datapackage.json
├── heva-annotations.json
└── heva-annotations.csv
```

Only sentences explicitly marked `approved` are exported. Excluded sentences remain in
the canonical working package and its audit history but do not enter the release. Source
PDFs, credentials, `review-state.json`, quality reports, and other working files are never
copied into the release directory.

The build has no timestamps or random identifiers. Documents, records, JSON keys, and CSV
line endings have stable ordering, so unchanged approved inputs produce identical bytes.
