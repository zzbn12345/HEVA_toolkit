# Persisting extraction results in a document package

`persist_extraction_results` is the safe boundary between extraction and a registered HEVA
package. It accepts records already produced by a PDF or DOCX extractor, validates every
record, and only then writes package resources.

The document must be registered and present. Its color configuration must either be
human-confirmed or explicitly authorized for extraction while pending review.

```python
from management.heva_management.extraction_session import persist_extraction_results

result = persist_extraction_results(
    ".",
    "HEVA-ABC123",
    records,
    extraction_method="automatic",
    extractor="HEVA PDF extractor",
    extractor_version="0.1.0",
)

print(result.annotations_path)
```

Successful persistence creates:

```text
data/packages/HEVA-ABC123/
├── annotations.json
├── extraction-session.json
└── package-metadata.json
```

It also:

- records the annotation resource and record count in package metadata;
- records extraction method, tool name, version, and time;
- preserves raw entity colors;
- marks sentence review incomplete;
- moves the registry document to `in_progress`;
- stores the source checksum in the session checkpoint.

If any record violates the HEVA contract, `ExtractionValidationError` contains all issues.
No existing `annotations.json` is replaced in that case.

`persist_extraction_results` itself does not invoke an extractor; it remains available as
the validation-and-persistence boundary for other workflows.

## Run extraction from a registered document

Once the document has a confirmed color configuration:

```python
from management.heva_management.extraction_session import run_registered_extraction

result = run_registered_extraction(".", "HEVA-ABC123")
print(result.annotations_path)
print(result.reused_checkpoint)
```

The runner selects the PDF or DOCX extractor from the registered source path, loads the
deliberately selected document-local mapping, and uses toolkit version `0.1.0` in
provenance. An authorized pending map produces `mapping_review_pending`; a confirmed map
produces `awaiting_review`.

If matching `annotations.json` and `extraction-session.json` already exist for the source
checksum, they are reused. Pass `force=True` only when an intentional re-extraction is
required.

PDFs with no extractable text are rejected with an explicit explanation that image-only
or scanned input is unsupported because the toolkit does not currently provide OCR.

Current resume support reuses a completed extraction checkpoint. Page-level continuation
after an interrupted extraction remains future work.

## Run selected documents or a batch

Run one registered document:

```bash
./venv/bin/python -m management.heva_management.extraction_session . \
  --document-id HEVA-ABC123
```

Run selected documents independently:

```bash
./venv/bin/python -m management.heva_management.extraction_session . \
  --document-id HEVA-ABC123 \
  --document-id HEVA-DEF456
```

Run every registered document:

```bash
./venv/bin/python -m management.heva_management.extraction_session . --all
```

Use `--json` for a machine-readable per-document report and `--force` for intentional
re-extraction. Batch order is deterministic from registry source paths. Each document
writes only to its own package; the batch does not merge annotations. A document failure
is reported without discarding successful or reused results from other documents.

If existing automatic proposals are still pending, the command reports that they are not
authorized and creates no annotations. After inspecting those proposals, explicitly
record the decision to use them:

```bash
./venv/bin/python -m management.heva_management.extraction_session . \
  --all \
  --authorize-pending-map-by "Research Annotator"
```

This does not mark the mappings as reviewed. It records the named user's decision to use
the proposals for extraction, and generated sessions remain `mapping_review_pending`.

## Build a reviewed collection

Collection building is deliberately separate from batch extraction. Only registry
documents with status `done` are eligible:

```bash
./venv/bin/python -m management.heva_management.release_builder .
```

The generated, ignored artifact is:

```text
data/heva-collection.json
```

The collection preserves document boundaries, source paths, source checksums, record
counts, and canonical annotation records. Documents are ordered by source path and records
by page and sentence ID, so unchanged completed packages produce byte-identical output.

Every eligible `annotations.json` is validated before the collection is written. If one
completed package is missing or invalid, the command reports an error and does not replace
an existing collection.
