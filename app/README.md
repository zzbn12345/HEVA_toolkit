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
