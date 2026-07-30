# HEVA package layout

```text
project/
├── data/
│   ├── project-registry.json
│   ├── annotators.json
│   ├── dataset-metadata.json
│   └── packages/
│       └── HEVA-…/
│           ├── package-metadata.json
│           ├── annotations.json
│           ├── extraction-session.json
│           ├── review-state.json
│           └── curation-state.json
└── local source PDFs or DOCX files
```

The registry provides stable document identity. Each package keeps annotation data,
document metadata, extraction provenance, sentence decisions, and curator evidence
separate so they can be validated and versioned independently.

Source documents are not copied into a package. Generated releases are written separately
under `data/release/`.
