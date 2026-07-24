# Persisting extraction results in a document package

`persist_extraction_results` is the safe boundary between extraction and a registered HEVA
package. It accepts records already produced by a PDF or DOCX extractor, validates every
record, and only then writes package resources.

The document must be registered, present, and have a human-confirmed color configuration.

```python
from src.extraction_session import persist_extraction_results

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

This function does not yet invoke the PDF or DOCX extractor itself. Source execution,
scanned-PDF reporting, and resumable page-level extraction are later F05 slices.
