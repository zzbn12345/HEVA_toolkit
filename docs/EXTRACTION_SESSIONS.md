# Persisting extraction results in a document package

`persist_extraction_results` is the safe boundary between extraction and a registered HEVA
package. It accepts records already produced by a PDF or DOCX extractor, validates every
record, and only then writes package resources.

The document must be registered and present. Its color configuration must either be
human-confirmed or explicitly authorized for extraction while pending review.

```python
from heva.workflow.extraction_session import persist_extraction_results

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
data/documents/HEVA-ABC123/
├── annotations.json
└── metadata.json

.heva/documents/HEVA-ABC123/
└── extraction-session.json
```

It also:

- records the annotation resource and record count in document metadata;
- records extraction method, tool name, version, and time;
- preserves raw entity colors;
- marks sentence review incomplete;
- moves the registry document to `in_progress`;
- stores source and selected color-mapping checksums in the session checkpoint.

If any record violates the HEVA contract, `ExtractionValidationError` contains all issues.
No existing `annotations.json` is replaced in that case.

An extraction that produces zero records raises `EmptyExtractionError` with corrective
guidance. It is not persisted as a successful empty resource and does not replace an
earlier checkpoint.

`persist_extraction_results` itself does not invoke an extractor; it remains available as
the validation-and-persistence boundary for other workflows.

## Run extraction from a registered document

Once the document has a confirmed color configuration:

```python
from heva.workflow.extraction_session import run_registered_extraction

result = run_registered_extraction(".", "HEVA-ABC123")
print(result.annotations_path)
print(result.reused_checkpoint)
```

The runner selects the PDF or DOCX extractor from the registered source path, loads the
deliberately selected document-local mapping, and uses toolkit version `0.1.0` in
provenance. An authorized pending map produces `mapping_review_pending`; a confirmed map
produces `awaiting_review`.

Existing `annotations.json` and `extraction-session.json` are reused only when the source
checksum, mapping checksum, declared count, and actual positive record count all match.
Legacy checkpoints without mapping provenance remain readable but are marked stale.
Changing a source or color decision therefore preserves existing records while requiring
a rebuild. Pass `force=True` only when an intentional re-extraction is required.

The web workspace restores this state when a document opens. It reports the persisted
sentence count, pending-map warning, and any stale reason. **Rebuild extraction** is a
separate deliberate action from ordinary extraction/checkpoint reuse.

PDFs with no extractable text are rejected with an explicit explanation that image-only
or scanned input is unsupported because the toolkit does not currently provide OCR.

Current resume support reuses a completed extraction checkpoint. Page-level continuation
after an interrupted extraction remains future work.

## Run selected documents or a batch

Run one registered document:

```bash
./venv/bin/python -m heva.workflow.extraction_session . \
  --document-id HEVA-ABC123
```

Run selected documents independently:

```bash
./venv/bin/python -m heva.workflow.extraction_session . \
  --document-id HEVA-ABC123 \
  --document-id HEVA-DEF456
```

Run every registered document:

```bash
./venv/bin/python -m heva.workflow.extraction_session . --all
```

Use `--json` for a machine-readable per-document report and `--force` for intentional
re-extraction. Batch order is deterministic from registry source paths. Each document
writes only to its own package; the batch does not merge annotations. A document failure
is reported without discarding successful or reused results from other documents.

If existing automatic proposals are still pending, the command reports that they are not
authorized and creates no annotations. After inspecting those proposals, explicitly
record the decision to use them:

```bash
./venv/bin/python -m heva.workflow.extraction_session . \
  --all \
  --authorize-pending-map-by "Research Annotator"
```

This does not mark the mappings as reviewed. It records the named user's decision to use
the proposals for extraction, and generated sessions remain `mapping_review_pending`.

## Build a FAIR candidate

Release building is deliberately separate from batch extraction. A registry status alone
is not sufficient: every member must have intact curator-acceptance evidence and the
project must provide citable dataset metadata.

```bash
./venv/bin/python -m heva.workflow.package_validator . release
```

See `docs/APPROVED_EXPORT.md` for dataset metadata, generated resources, checksum behavior,
rights boundaries, and the remaining human publication gate.
