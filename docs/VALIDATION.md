# Validating HEVA extracted records

HEVA validates a record in two stages:

1. **Pydantic checks the structure:** are the expected fields present, and does each field
   contain the right kind of data?
2. **HEVA checks the meaning:** do the fields follow the annotation rules and agree with
   each other?

In simple terms, Pydantic checks that a form was filled in correctly. HEVA validation
checks whether the answers on that form make sense together.

## A simple example

Pydantic checks basic questions such as:

- Is `sentence_id` an integer?
- Is `sentence` text?
- Is `tokens` a list?
- Does every entity contain `start`, `end`, `text`, and `label`?

For example, `"sentence_id": "first"` is invalid because `sentence_id` must be a number.
Pydantic can detect this without knowing anything about heritage annotations.

Once the structure is correct, HEVA checks domain-specific questions:

- Do the entity positions select the stated text from the sentence?
- Does every label belong to the approved HEVA vocabulary?
- Is every `I-label` preceded by a matching `B-label` or `I-label`?
- Do `values`, entities, and BIO tags describe the same labels?

Consider this annotation:

```json
{
  "sentence_id": 1,
  "page": 2,
  "sentence": "The historic harbour remains visible.",
  "tokens": ["The", "historic", "harbour", "remains", "visible", "."],
  "values": ["historic"],
  "entities": [
    {
      "start": 4,
      "end": 20,
      "text": "historic harbour",
      "label": "historic"
    }
  ],
  "ner_tags": ["O", "B-historic", "I-historic", "O", "O", "O"]
}
```

The three annotation representations agree:

- `values` says the sentence contains a `historic` value;
- the entity identifies `historic harbour` as the historic text span;
- the BIO tags mark the same label on the corresponding tokens.

If the BIO tags were all `O`, they would mean that no token is annotated. That would
contradict `values` and the entity. The HEVA validator reports this as
`bio_value_mismatch`.

| Validation layer | Question it answers |
|---|---|
| Pydantic structure | “Does this JSON contain the expected fields and data types?” |
| HEVA semantics | “Do these values make sense and agree according to HEVA rules?” |

A record must pass both stages. Correctly shaped JSON can still contain an incorrect or
contradictory annotation.

## Quickstart: validate in 3 commands

From the repository root:

### 1) Create environment and install dependencies

```bash
python3.12 -m venv venv
./venv/bin/python -m pip install --upgrade pip setuptools wheel
./venv/bin/python -m pip install -e .
```

### 2) Validate one file

```bash
./venv/bin/python -m heva.workflow.validate_records --file data/Galle_P127_extracted.json
```

Exit codes:
- `0`: valid
- `1`: decoded but has contract issues
- `2`: malformed JSON or unreadable input

### 3) Validate all extracted files in `data/`

```bash
./venv/bin/python -m heva.workflow.validate_records --all
```

Optional: validate by custom glob pattern.

```bash
./venv/bin/python -m heva.workflow.validate_records --glob "data/*_extracted.json"
```

Optional: limit printed issues per file.

```bash
./venv/bin/python -m heva.workflow.validate_records --all --max-issues 10
```

Expected baseline in this repository: four extracted files, all valid.

## Install the validator dependencies

From the repository root, install the pinned requirements in an isolated Python
environment:

```bash
python3.12 -m venv venv
./venv/bin/python -m pip install --upgrade pip setuptools wheel
./venv/bin/python -m pip install -e .
```

## What structural parsing validates

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

Pydantic checks field presence and primitive types. Positive integer, schema-version,
and other domain rules are enforced by the semantic checks in the same validator.

Run validation from Python as follows:

```python
from pathlib import Path
from heva.workflow.contract import ContractParseError, load_records

path = Path("data/Galle_P127_extracted.json")

try:
    results = load_records(path)
except ContractParseError as error:
    print(error)
else:
    for row_number, result in enumerate(results, start=1):
        for issue in result.issues:
            print(row_number, issue.code, issue.path, issue.message)

    valid = all(result.valid for result in results)
    print(f"{path}: {'valid' if valid else 'invalid'}")
```

For the current Galle example this reports `valid`.

## What the HEVA validator adds

`heva.workflow.contract` validates each decoded record and reports issues with stable codes and
JSON-style paths. It checks that:

- labels in `values`, entities, and BIO tags belong to the controlled HEVA vocabulary;
- `tokens` and `ner_tags` have the same length;
- an `I-label` follows `B-label` or `I-label` of the same category;
- BIO tags represent the same label set as `values` and entities;
- every entity range is inside the sentence;
- `sentence[start:end]` exactly equals the entity text;
- `values` equals the set of labels represented by entities;
- optional colors use normalized `#RRGGBB` syntax;
- optional mapping status is `pending_review` or `approved`;
- the record uses a supported schema version.

The validator returns all detectable issues for a decoded record rather than stopping at
the first one. A syntactically malformed JSON document is different: it raises
`ContractParseError`, because no records can be decoded. For example,
`data/json_word_P2_oracle.json` reports invalid JSON with line and column details.

## Validate every extracted example

```python
from pathlib import Path

from heva.workflow.contract import load_records

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
./venv/bin/pytest -q tests/workflow/test_contract.py
```

The tests cover descriptor field compatibility, all repository extraction examples,
malformed JSON, invalid labels, mismatched entity text, unequal token/BIO lengths,
invalid BIO transitions, preservation of color-mapping provenance, and exact golden-output
regressions for the real PDF and DOCX extractors.
