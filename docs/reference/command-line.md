# Command-line reference

HEVA exposes Python modules for scripting and interoperability rather than requiring a
separately installed shell command.

| Task | Command |
|---|---|
| Start the app | `python -m heva.app` |
| Validate a project | `python -m heva.workflow.package_validator PROJECT validate` |
| Validate one document | `python -m heva.workflow.package_validator PROJECT validate --document-id ID` |
| Write JSON validation | `python -m heva.workflow.package_validator PROJECT validate --json --report REPORT` |
| Compile edited CSV | `python -m heva.workflow.package_compiler PROJECT --csv FILE` |
| Run registered extraction | `python -m heva.workflow.extraction_session PROJECT --document-id ID` |
| Build a FAIR candidate | `python -m heva.workflow.package_validator PROJECT release` |
| Score evaluation evidence | `python -m heva.workflow.evaluation MANIFEST --report REPORT` |

Use `--help` after any module for its complete options.
