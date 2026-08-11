# Programmatic citation import

Citation is not a gate for sentence curation. It is required before HEVA generates a
Data Package or AI-training derivative. Researchers may enter it in the app or import it
programmatically; neither route is privileged if the same validation passes.

The first import profile uses a small CSL-compatible core:

- exact source filename;
- title;
- one or more creators, separated by semicolons in CSV;
- CSL item type (`article`, `book`, `chapter`, `paper-conference`, `report`, or `webpage`);
- issued year, or an explicit `undated=true` decision;
- human-readable citation; and
- DOI/public URL, or a reason the source is not publicly findable.

Exact filenames are intentional. HEVA does not use fuzzy matching because two similarly
named PDFs could otherwise receive each other's citation. A relative source path may be
used when basenames are not unique.

```python
from heva.workflow.citation_import import import_citation_csv

document_ids = import_citation_csv(
    project_root,
    "citations.csv",
    validated_by="institutional-catalogue-adapter/1.0",
)
```

The imported values and validation provenance are written to each document's
`metadata.json`. A malformed or unmatched row raises an error; it is never silently
assigned. The sample fixture at `tests/fixtures/citations.csv` can be copied when designing
the researchers' authoritative spreadsheet adapter.
