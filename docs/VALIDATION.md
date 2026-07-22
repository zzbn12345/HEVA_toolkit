# Validating HEVA extracted records

HEVA uses two complementary validation layers:

1. **Frictionless validation** checks whether the JSON records follow the declared,
   interoperable field structure.
2. **HEVA semantic validation** checks relationships that a tabular schema cannot express,
   such as entity offsets, controlled labels, and BIO transitions.

Passing only one layer is not sufficient evidence that a HEVA record is correct.

## Install the validator dependencies

From the repository root, install the pinned requirements in an isolated Python
environment:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## What Frictionless validates

The descriptor at `schemas/heva-extracted-record.json` defines one extracted sentence as a
row with these fields:

| Field | Type | Required in legacy records | Meaning |
|---|---|---:|---|
| `sentence_id` | integer | yes | Positive sentence identifier within the document |
| `page` | integer | yes | Positive source page number |
| `sentence` | string | yes | Sentence providing the annotation context |
| `tokens` | array | yes | Tokenized sentence |
| `values` | array | yes | Distinct HEVA labels represented in the sentence |
| `entities` | array | yes | Labeled character spans |
| `ner_tags` | array | yes | BIO tag corresponding to each token |
| `schema_version` | string | no | Explicit contract version for new records |
| `mapping_provenance` | object | no | Origin and human-review state of color mapping |

Frictionless checks field presence, primitive types, and positive integer constraints. Run
it from Python as follows:

```python
import json
from pathlib import Path

from frictionless import Resource

records = json.loads(Path("data/Galle_P127_extracted.json").read_text(encoding="utf-8"))
resource = Resource(data=records, schema="schemas/heva-extracted-record.json")
report = resource.validate()

print("valid:", report.valid)
for error in report.flatten(["type", "rowNumber", "fieldName", "message"]):
    print(error)
```

For the current Galle example this reports `valid: True`.

Frictionless is useful here because the same machine-readable descriptor can later be used
by package builders, command-line tools, and other data-processing software. It does not,
however, understand HEVA's nested annotation semantics.

## What the HEVA validator adds

`src.heva_contract` validates each decoded record and reports issues with stable codes and
JSON-style paths. It checks that:

- labels in `values`, entities, and BIO tags belong to the controlled HEVA vocabulary;
- `tokens` and `ner_tags` have the same length;
- an `I-label` follows `B-label` or `I-label` of the same category;
- every entity range is inside the sentence;
- `sentence[start:end]` exactly equals the entity text;
- `values` equals the set of labels represented by entities;
- optional colors use normalized `#RRGGBB` syntax;
- optional mapping status is `pending_review` or `approved`;
- the record uses a supported schema version.

Validate a file with:

```python
from pathlib import Path

from src.heva_contract import ContractParseError, load_records

path = Path("data/Galle_P127_extracted.json")

try:
    results = load_records(path)
except ContractParseError as error:
    print(error)  # Includes source path, line, and column.
else:
    for row_number, result in enumerate(results, start=1):
        for issue in result.issues:
            print(row_number, issue.code, issue.path, issue.message)

    valid = all(result.valid for result in results)
    print(f"{path}: {'valid' if valid else 'invalid'}")
```

The validator returns all detectable issues for a decoded record rather than stopping at
the first one. A syntactically malformed JSON document is different: it raises
`ContractParseError`, because no records can be decoded. For example,
`data/json_word_P2_oracle.json` currently reports invalid JSON at line 202, column 8.

## Validate every extracted example

```python
from pathlib import Path

from src.heva_contract import load_records

failed = False
for path in sorted(Path("data").glob("*_extracted.json")):
    results = load_records(path)
    issues = [issue for result in results for issue in result.issues]
    print(f"{path.name}: {len(results)} records, {len(issues)} issues")
    failed = failed or bool(issues)

raise SystemExit(1 if failed else 0)
```

The current repository baseline is four extracted files, 82 records, and zero contract
issues.

## Interpreting a successful result

A successful structural and semantic validation means that the extracted records are
internally consistent with contract version 1.0. It does **not** prove that:

- every highlight in the source document was extracted;
- the selected sentence or span is academically correct;
- an automatically suggested HEVA label is correct;
- a color mapping has been approved by an annotator;
- every sentence has completed human review;
- source provenance and publication rights are complete;
- the document package is ready for curator review or public release.

Those are later validation levels. Until they are implemented, this validator should be
described as a **record-contract validator**, not a complete HEVA package or FAIRness
validator.

## Run the acceptance tests

```bash
.venv/bin/pytest -q tests/test_heva_contract.py
```

The tests cover the Frictionless descriptor, all repository extraction examples, malformed
JSON, invalid labels, mismatched entity text, unequal token/BIO lengths, invalid BIO
transitions, and preservation of color-mapping provenance.
