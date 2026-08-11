# Source discovery when opening a project

HEVA compares the configured source folder with the project registry every time a project
is opened. The scan is read-only: it reports new, changed, and missing PDF/DOCX files
without silently rewriting membership or existing checksums.

New files appear on the project home screen with two explicit choices:

- **Add to project** assigns a stable document ID and initializes its analytical metadata.
- **Not this session** hides the suggestion until the project is closed. This choice is
  intentionally not written to the repository.

Changed and missing registered sources remain validation findings. A new source cannot be
accepted if it disappeared after the scan, and only explicitly selected discoveries are
registered. This avoids accidentally adding every PDF placed in a shared research folder.

The same boundary is available to Python clients through `scan_project_sources()` and
`register_discovered_sources()` in `heva.workflow.project_registry`.
