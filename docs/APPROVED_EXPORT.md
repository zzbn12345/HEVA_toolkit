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

## Curator acceptance and release

After an annotator submits a fully decided document, its registry status is `in_review`.
A curator accepts the exact checksummed candidate in the local `/curation` view. Acceptance
is the only action that changes the status to `done`.

Before the first build, create `dataset-metadata.json`:

```json
{
  "name": "heva-example-annotations",
  "title": "HEVA example annotations",
  "description": "Curator-approved heritage-value annotations.",
  "creators": ["Research team"],
  "contributors": ["Annotator name"],
  "license": "CC-BY-4.0",
  "rights": "Annotations may be shared; source documents remain restricted.",
  "known_limitations": [
    "This release does not claim OCR support or complete heritage coverage."
  ]
}
```

Build the release candidate with:

```bash
./venv/bin/python -m heva.workflow.package_validator . release
```

The same guarded operation is available on the app's **Validate** page. Select
**Generate Data Package** after fixing the validation report, then download the generated
ZIP. The app still checks the stricter release requirements: every included document must
have curator acceptance and data-owner approval, and the project must have valid dataset
metadata. A successful workspace validation therefore does not automatically mean that a
release can be generated.

This creates:

```text
exports/heva-data-package/
├── build-log.json
├── datapackage.json
├── heva-annotations.json
└── heva-annotations.csv
```

Only sentences explicitly marked `approved` are exported. Excluded sentences remain in
the canonical working package and its audit history but do not enter the release. Source
PDFs, credentials, `review-state.json`, quality reports, and other working files are never
copied into the release directory. Every included document carries its source citation,
creator/reference or non-findability statement, document rights, annotator, curator
acceptance, source checksum, and immutable candidate checksum. The Data Package descriptor
records checksums and byte sizes for all release resources.

The build has no timestamps or random identifiers. Documents, records, JSON keys, and CSV
line endings have stable ordering, so unchanged approved inputs produce identical bytes.
The output is a **FAIR candidate**, not a publication: repository deposit remains an
explicit human decision. HEVA does not generate an example model prompt until the dataset
and controlled vocabulary have separately been approved for release.

The downloaded ZIP is only a portable wrapper around these four deterministic files. It
does not add source PDFs, local paths, review state, or other workspace evidence.
