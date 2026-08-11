# HEVA project layout

```text
project/
├── source-document.pdf
├── source-document.docx
├── dataset-metadata.json
├── documents/
│   └── HEVA-…/
│       ├── metadata.json
│       └── annotations.json
├── .heva/
│   ├── project.json
│   ├── people.json
│   ├── color-configurations.json
│   └── documents/
│       └── HEVA-…/
│           ├── extraction-draft.json
│           ├── extraction-session.json
│           ├── review-state.json
│           ├── curation-state.json
│           ├── data-owner-approval.json
│           └── quality-report.json
├── exports/
│   └── heva-data-package/
│       ├── datapackage.json
│       ├── heva-annotations.json
│       └── heva-annotations.csv
```

The folder containing the source documents is the project root. `documents/` contains the
canonical analytical metadata and annotations. `.heva/` is hidden but durable application
workspace state used to resume and collaborate on extraction, review, and curation.
`exports/` contains reproducible, validated HEVA Data Packages.

`extraction-draft.json` is unresolved extractor evidence. It is workspace state, not a
canonical annotation or training resource.

HEVA does not copy or rename source documents. Opening a former parent-root project by
selecting its source folder moves the workspace into that folder without changing document
identifiers, annotations, or review history.

For collaboration, commit `documents/`, `.heva/project.json`, `.heva/people.json`, and
`.heva/documents/`. Ignore `.heva/cache/`, `.heva/locks/`, `.heva/session.json`, and
reproducible `exports/`.
