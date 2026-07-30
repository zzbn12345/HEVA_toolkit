# Create or open a project

Start HEVA with `python -m heva.app`, then open <http://127.0.0.1:8000>.

- **Create project** scans a selected local folder for PDF/DOCX sources, assigns stable
  document IDs, and creates document package workspaces.
- **Open existing project** loads a folder that already contains
  `data/project-registry.json`.

HEVA does not upload, rename, or move source documents. See
[Project registry](../PROJECT_REGISTRY.md) for synchronization behavior and stable IDs.
