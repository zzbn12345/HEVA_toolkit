# HEVA web application

This package provides the optional local FastAPI interface for opening HEVA projects,
guiding annotators through document preparation, reviewing extracted sentences, running
validation, and recording curator decisions.

The web interface is a view over the workflow package. It must not contain a second data
model or silently rewrite extraction evidence.

## Install and start

```bash
python -m pip install -e ".[app]"
python -m heva.app
```

Open <http://127.0.0.1:8000>. To open a known project immediately:

```bash
python -m heva.app --project-root /path/to/heva-project
```

The application binds to localhost by default. It is intended as a single-user local
tool, not as a multi-user internet service.

## Responsibilities

- `main.py` composes the FastAPI application and project boundary.
- `project_context.py` holds the active project only for the running app session.
- `routes/` translates HTTP requests into workflow operations.
- `templates/` and `static/` contain the accessible browser interface.
- `documentation.py` renders the same sanitized Markdown used by the repository guide.
- `folder_picker.py` opens a native local folder chooser without uploading sources.

## Persistence boundary

The currently selected project exists only in memory for the running application and is
not restored after restart. Citation, annotator, color,
extraction, review, validation, and curation changes are persisted by `heva.workflow` in
the selected project's JSON package files. Browser state is never the authoritative copy.

The application does not upload or distribute source documents. Researchers can either
register an external PDF/DOCX without copying it or explicitly import a PDF into managed
project source storage. Managed imports are copied and registered atomically, so they remain
available after the application restarts. Rights and release decisions remain document-local
workflow evidence.

## Tests

```bash
python -m pytest tests/app
```

See the [tutorial](../../../docs/TUTORIAL.md) and
[software design](../../../docs/SOFTWARE_DESIGN.md).
