# Optional HEVA web application

The application is kept separate from the extraction and data-management modules so that
using the original NLP scripts or validating JSON does not require FastAPI.

Create an application-specific environment from the repository root:

```bash
python3.12 -m venv app/venv
./app/venv/bin/python -m pip install -r app/requirements.txt
```

Run it against one persistent HEVA project:

```bash
./app/venv/bin/python -m app.heva_app --project-root .
```

Then open `http://127.0.0.1:8000`.

Run only the application tests with:

```bash
./app/venv/bin/python -m pytest -q app/tests
```

The app calls the same project registry, review state, and validator modules used by
scripts. It must not duplicate HEVA validation or extraction rules inside HTTP handlers.

## Document review

Open `/review` to see batch-prepared documents as a queue. Counts may be summarized across
the queue, but selecting a document opens only that document's persisted annotations,
quality flags, decisions, and source PDF.

The document screen provides:

- independently scrolling annotation and PDF panes;
- a hide/show PDF control;
- pending and problematic filters;
- page sizes of 20 or 50 sentences;
- readable raw color codes, controlled labels, and quality flags;
- explicit Approve, Needs correction, or Exclude decisions per sentence;
- previous/next navigation that changes the complete document context.

Decisions are written through `management.heva_management.review_state`, including the
project annotator and individual audit event. The interface never stores an alternative
review state.
