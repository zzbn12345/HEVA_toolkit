# HEVA project registry

The project registry is a JSON account of the PDF and DOCX sources known to a HEVA
project. It gives each document a stable ID and records where its analytical document data
belongs. Source files are scanned but never renamed or modified.

## Initialize or synchronize a project

From the project root, scan the default `data/` directory:

```bash
./venv/bin/python -m heva.workflow.project_registry .
```

To scan another folder inside the project:

```bash
./venv/bin/python -m heva.workflow.project_registry . --source-dir documents
```

The registry is written to `.heva/project.json`. A concise summary is printed for
people. Scripts can request JSON output:

```bash
./venv/bin/python -m heva.workflow.project_registry . --source-dir documents --json
```

## What synchronization does

- New PDF and DOCX files receive a stable `HEVA-...` identifier.
- The corresponding data path is `data/documents/<document-id>`.
- An analytical document directory and incomplete `metadata.json` template are created at that
  path. Missing authorship, rights, process, color, and resource details remain visibly
  empty for later HEVA steps; synchronization never invents them.
- When document metadata is saved, the registry records its `metadata_path`; detailed
  provenance, rights, color configuration, and extraction resources stay with the data.
- Re-running synchronization does not overwrite document metadata already edited by a
  researcher.
- Re-running synchronization preserves existing IDs and workflow states.
- New documents are added once.
- A changed file is marked `changed`; its original checksum and newly observed checksum
  are both retained.
- A missing file remains in the registry and is marked `missing` rather than silently
  deleted.
- Temporary Office files beginning with `~$` are ignored.

The precomputed `summary` contains document counts for `backlog`, `in_progress`,
`in_review`, and `done`, plus changed and missing source counts. This allows a later
dashboard to load project status without scanning all source files again.

## Registry authority and limits

The registry is authoritative for document IDs, source paths, data paths, checksums, and
project status. A document record must use the same ID recorded here.

At this stage, synchronization does not create annotation packages, validate sentences,
approve changed documents, or decide publication rights. Those are separate HEVA
capabilities. A changed checksum is deliberately reported for human resolution; it does
not replace the registered source identity automatically.
