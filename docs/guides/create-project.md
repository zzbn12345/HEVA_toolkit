# Create or open a project

Start HEVA with `python -m heva.app`, then open <http://127.0.0.1:8000>.

- **Create project** opens the system folder chooser, scans the selected local folder for
  PDF/DOCX sources, assigns stable
  document IDs, and creates document package workspaces.
- **Open existing project** opens the same chooser and loads a folder that already contains
  `data/project-registry.json`.

You may choose either the project root or its `data/` folder; HEVA resolves both to the
same project. The local app remembers the active project and reopens it after a restart.
Choosing **Close project** deliberately clears that remembered selection.

The browser receives only the selected folder path. HEVA does not upload, copy, rename,
or move source documents. See
[Project registry](../PROJECT_REGISTRY.md) for synchronization behavior and stable IDs.

Keep working HEVA projects outside the toolkit source-code checkout. Binary PDFs, Word
documents, spreadsheets, and presentations are intentionally ignored by Git; only
annotation packages approved for distribution should be versioned in a data repository.
