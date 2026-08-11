# External source documents and dataset repositories

The HEVA Toolkit code repository and a curated HEVA dataset repository should be separate.
The dataset repository contains canonical metadata, annotations, and collaborative workflow
evidence. Authorized PDFs or DOCX files may remain in a protected folder outside both.

When **Choose PDF or DOCX** is used, the project registry stores a portable logical name,
checksum, stable document ID, and `source_binding: external`. The absolute path is written
only to `.heva/local-sources.json`, which is ignored by Git. The source is not copied.

This means collaborators can clone and version the dataset safely. Each collaborator must
bind the same authorized source on their own computer before previewing or extracting it.
HEVA identifies an existing external record by checksum, so rebinding does not create a
duplicate document.

```python
from heva.workflow.project_registry import register_external_source

document_id = register_external_source(
    dataset_repository,
    "/protected/authorized/report.pdf",
)
```

Generated Data Packages continue to exclude source files and machine-local paths. Rights
metadata determines whether extracted text and annotations may be distributed.
