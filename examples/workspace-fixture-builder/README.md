# Complete workspace fixture builder

This builder creates `examples/complete-dummy-project/`, a portable HEVA workspace with two
fictional source PDFs, complete metadata, reviewed annotations, and project people.

Run it from the repository root:

```bash
python examples/workspace-fixture-builder/build_complete_workspace.py --force
```

The generated workspace must pass validation before the builder exits successfully.
