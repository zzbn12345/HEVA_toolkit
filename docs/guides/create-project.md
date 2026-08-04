# Create or open a project

Start HEVA with `python -m heva.app`, then open <http://127.0.0.1:8000>.

- **Create project** opens the system folder chooser, scans the selected local folder for
  PDF/DOCX sources, assigns stable
  document IDs, creates analytical records under `documents/`, and keeps application
  state in the hidden `.heva/` workspace.
- **Open existing project** opens the same chooser and loads a folder that already contains
  `.heva/project.json`.

Choose the folder that contains the source documents. That folder becomes the project
root and receives the hidden `.heva/` workspace. Project selection lasts only for the
running application session. HEVA
starts with no project after a restart, and **Close project** clears the current selection.
The interface shows only the project folder name, not its absolute user-directory path.

The browser receives only the selected folder path. HEVA does not upload, copy, or rename
source documents. It may move an existing HEVA workspace from a former parent directory
into the selected source folder after conflict checks. See
[Project registry](../PROJECT_REGISTRY.md) for synchronization behavior and stable IDs.

When the workspace is collaborative, version `documents/` and the durable JSON under
`.heva/`. Source binaries should be versioned only when their rights permit repository
storage. Generated `exports/`, caches, locks, and local session preferences remain ignored.
