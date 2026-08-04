# Create or open a project

Start HEVA with `python -m heva.app`, then open <http://127.0.0.1:8000>.

- **Create project** opens the system folder chooser, scans the selected local folder for
  PDF/DOCX sources, assigns stable
  document IDs, creates analytical records under `data/documents/`, and keeps application
  state in the hidden `.heva/` workspace.
- **Open existing project** opens the same chooser and loads a folder that already contains
  `.heva/project.json`.

You may choose either the project root or its `data/` folder; HEVA resolves both to the
same project. Project selection lasts only for the running application session. HEVA
starts with no project after a restart, and **Close project** clears the current selection.
The interface shows only the project folder name, not its absolute user-directory path.

The browser receives only the selected folder path. HEVA does not upload, copy, rename,
or move source documents. See
[Project registry](../PROJECT_REGISTRY.md) for synchronization behavior and stable IDs.

Keep working HEVA projects outside the toolkit source-code checkout. Binary PDFs, Word
documents, spreadsheets, and presentations are intentionally ignored by Git; only
validated exports or canonical annotation data should be versioned in a data repository.
