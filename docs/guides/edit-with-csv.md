# Edit annotations through CSV

Researchers may edit the release-shaped CSV outside the app and compile it back into
registered document packages:

```bash
python -m heva.workflow.package_compiler /path/to/project \
  --csv /path/to/edited-annotations.csv
```

Compilation validates every row before mutation, refuses submitted/accepted packages,
refreshes changed sentence-review evidence, and rolls back on failure. Run project
validation afterward.

See [Validation](../VALIDATION.md#edit-csv-compile-packages-then-validate) for the required
columns and safety behavior.
