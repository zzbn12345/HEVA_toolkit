# HEVA and validation

HEVA Toolkit turns color-annotated PDF and DOCX documents into structured heritage-value
annotation data. It helps a researcher discover colors, assign HEVA labels, review extracted
sentences, and produce a reusable Data Package.

## Validation is the central feature

Validation is the repeatable check that tells a user what is complete and what must be fixed.
It can run in the app or from a terminal:

```bash
python -m heva.curation.package_validator /path/to/project validate
```

HEVA uses two kinds of checks:

1. **Schema checks** confirm that required fields exist and contain the expected basic types.
2. **HEVA checks** confirm relationships, such as valid labels, text offsets that select the
   recorded phrase, and BIO tags that align with tokens.

Schemas matter because they make the expected data shape explicit and machine-checkable.
The additional HEVA checks catch mistakes that a field-by-field schema cannot see.

A passing report means the project conforms to the current HEVA specification. It does not
prove that an interpretation is scholarly correct or that automatic extraction found every
annotation. Human review remains essential.

Next: [understand the Data Package](DATA_PACKAGE.md).
