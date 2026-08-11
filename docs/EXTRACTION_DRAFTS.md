# Unresolved extraction drafts

HEVA can preserve automatic extraction before the meaning of every document color has
been decided. This makes extraction reusable and shareable without presenting raw hex
codes as validated heritage-value labels.

The draft is stored at `.heva/documents/<document-id>/extraction-draft.json`. It contains
source and extractor provenance, sentences, text offsets, and observed hex colors. Its
entity `label` is always `null` and its `mapping_status` is always `unresolved`. It may be
committed for collaboration, but it is not canonical `annotations.json` and is excluded
from training exports.

## Python usage

Run extraction without Ollama or a semantic color map:

```python
from heva.workflow.extraction_draft import run_registered_raw_extraction

path = run_registered_raw_extraction(project_root, document_id)
```

After selecting an immutable project color configuration, resolve the draft into records
that satisfy the HEVA sentence contract:

```python
from heva.workflow.extraction_draft import compile_extraction_draft

records = compile_extraction_draft(project_root, document_id)
```

Compilation fails when the source changed, a color is missing, or the resolved result
violates entity, label, or BIO rules. It does not overwrite canonical annotations.

Saving requires an active curator. A zero-result rerun preserves the previous draft.
Every observed color must resolve, and the exact selected configuration version is
recorded as mapping provenance.

The repository's machine-readable contract is
`schemas/heva-extraction-draft.schema.json`.
