# HEVA project layout

```text
project/
├── data/
│   ├── dataset-metadata.json
│   └── documents/
│       └── HEVA-…/
│           ├── metadata.json
│           └── annotations.json
├── .heva/
│   ├── project.json
│   ├── annotators.json
│   └── documents/
│       └── HEVA-…/
│           ├── extraction-session.json
│           ├── review-state.json
│           ├── curation-state.json
│           └── quality-report.json
├── exports/
│   └── heva-data-package/
│       ├── datapackage.json
│       ├── heva-annotations.json
│       └── heva-annotations.csv
└── local source PDFs or DOCX files
```

`data/` is the canonical analytical dataset: it contains only dataset/document metadata
and annotations. `.heva/` is hidden application workspace state used to resume extraction,
review, and curation. `exports/` contains generated, validated HEVA Data Packages.

Source documents are not copied into the dataset or an export. Opening a legacy project
automatically moves its analytical files and workflow state into these locations without
changing document identifiers.
