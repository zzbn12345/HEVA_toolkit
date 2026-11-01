"""The eight Cultural Value Framework (CVF) values and their BIO tag set."""

from __future__ import annotations

# Fixed order: label vectors (T1) and tag indices (T2) depend on it.
VALUES: tuple[str, ...] = (
    "social",
    "economic",
    "political",
    "historic",
    "aesthetical",
    "scientific",
    "age",
    "ecological",
)

BIO_TAGS: tuple[str, ...] = ("O",) + tuple(
    f"{prefix}-{value}" for value in VALUES for prefix in ("B", "I")
)
TAG_TO_ID = {tag: index for index, tag in enumerate(BIO_TAGS)}

# Spellings used by other annotation tools (e.g. Atlas.ti code names).
_ALIASES = {
    "aesthetic": "aesthetical",
    "aesthetics": "aesthetical",
    "history": "historic",
    "historical": "historic",
    "economical": "economic",
    "politic": "political",
    "politics": "political",
    "science": "scientific",
    "ecology": "ecological",
    "ecologic": "ecological",
}


def normalize_value(name: str) -> str | None:
    """Return the canonical CVF value for a label name, or None if it is not one."""
    key = name.strip().lower()
    key = _ALIASES.get(key, key)
    return key if key in VALUES else None


def encode_values(values) -> list[int]:
    """Encode a collection of canonical values as a 0/1 vector in VALUES order."""
    present = set(values)
    return [1 if value in present else 0 for value in VALUES]
