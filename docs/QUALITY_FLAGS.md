# Sentence quality flags

Quality flags help annotators find records that deserve closer inspection. They do not
change labels, repair text, exclude sentences, or decide whether an annotation is valid
research evidence.

Generate a report for one registered package:

```bash
./venv/bin/python -m heva.workflow.quality_flags . \
  --document-id HEVA-ABC123
```

The report is written to:

```text
data/documents/HEVA-ABC123/quality-report.json
```

Every annotation remains represented in `findings`, including records with no flags. This
supports the rule that annotators review every sentence while allowing an interface to
highlight problematic ones.

## Initial deterministic flags

- `empty_sentence`
- `single_word_sentence`
- `unusually_short_sentence`
- `unusually_long_sentence`
- `too_many_tokens`
- `suspicious_character`
- `likely_sentence_boundary_error`
- `unresolved_color_mapping`
- structural and semantic HEVA contract codes such as `entity_text_mismatch`,
  `token_tag_length_mismatch`, and `invalid_bio_transition`

Each flag has a stable code, severity, message, and evidence object.

## Configurable thresholds

Rules receive `QualityThresholds`:

```python
from heva.workflow.quality_flags import QualityThresholds, assess_record

thresholds = QualityThresholds(
    minimum_characters=20,
    maximum_characters=450,
    maximum_tokens=90,
)

flags = assess_record(record, thresholds)
```

Thresholds are explicit data rather than hidden interface behavior. Running the same
record with the same thresholds produces the same flags.

## Interpretation limit

A warning is a review aid, not proof of an error. For example, a sentence without terminal
punctuation may be a genuine heading rather than a broken boundary. Human approval,
correction, or exclusion belongs to the later sentence-review workflow.
