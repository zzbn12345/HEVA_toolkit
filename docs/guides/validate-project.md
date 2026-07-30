# Validate a project

Validation is HEVA's minimum product. It is read-only and reports validity separately from
curator completion.

In the app, choose **Validate this project** and then **Run validation**. From a terminal:

```bash
python -m heva.workflow.package_validator /path/to/project validate
```

Each issue has a stable code, exact JSON path, explanation, and corrective action. See
[Validating HEVA](../VALIDATION.md) for JSON reports, exit codes, and interpretation.
