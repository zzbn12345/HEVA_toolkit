# HEVA data management

`heva_management` owns the canonical record contract and the complete trust workflow:
registry identities, metadata, document-local color decisions, extraction checkpoints,
quality flags, sentence review, package validation, and approved release building.

It consumes canonical JSON records and does not import PDF, Word, spaCy, or FastAPI
dependencies except at the explicit extraction-session adapter boundary.

Install only this capability with:

```bash
./venv/bin/python -m pip install -r management/requirements.txt
```

New code should import, for example:

```python
from management.heva_management.contract import validate_record
from management.heva_management.project_registry import sync_registry
```

The modules under `src/` are temporary compatibility entry points for older scripts.
