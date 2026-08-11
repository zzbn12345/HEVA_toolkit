# Per-document data-owner approval

Curator acceptance means the annotations passed curation. It does not by itself authorize
distribution. Before HEVA generates a Data Package, every included document must also have
approval from a named project person with the `data_owner` role.

The approval records the exact content-addressed curator candidate, owner identity,
timestamp, applicable license or waiver, and a short approval statement. It lives at
`.heva/documents/<document-id>/data-owner-approval.json` so collaborators can audit the
workflow. The generated package contains the responsible person's public metadata and the
approval statement, not the source PDF.

```python
from heva.workflow.data_owner_approval import approve_document_distribution

approve_document_distribution(
    project_root,
    document_id,
    data_owner_id="PERSON-...",
    license_or_waiver="CC-BY-4.0",
    statement="I approve distribution of this document's annotation data.",
)
```

Approval is per document. One project-level click cannot silently authorize every source.
If accepted evidence changes, the old approval becomes stale and package generation is
blocked until the owner approves the new candidate.
