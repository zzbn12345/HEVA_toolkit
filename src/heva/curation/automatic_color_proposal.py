"""Safe orchestration of raw color evidence and local Ollama suggestions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping
import urllib.error
import urllib.request

from pydantic import ValidationError

from heva.curation.color_mapping import (
    ColorMappingError,
    load_color_configuration,
    save_color_configuration,
)
from heva.curation.contract import HEVA_LABELS
from heva.curation.review_queue import ReviewQueueError, registered_source_path


DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "llama3.1:8b"


class AutomaticColorProposalError(ValueError):
    """Raised when automatic evidence cannot be produced safely."""


def _raw_records(source: Path) -> list[dict[str, Any]]:
    try:
        if source.suffix.lower() == ".pdf":
            from heva.extraction.pdf_extractor import extract_colored_highlights

            return extract_colored_highlights(str(source), color_label_map={})
        if source.suffix.lower() == ".docx":
            from heva.extraction.docx_extractor import extract_docx_highlights

            return extract_docx_highlights(str(source), color_label_map={})
    except (ImportError, OSError, ValueError) as error:
        raise AutomaticColorProposalError(
            f"Raw color evidence could not be extracted: {error}"
        ) from error
    raise AutomaticColorProposalError("Automatic color proposals support PDF and DOCX.")


def _group_color_evidence(records: list[Mapping[str, Any]]) -> dict[str, list[str]]:
    groups: dict[str, set[str]] = {}
    for record in records:
        sentence = str(record.get("sentence", "")).strip()
        for entity in record.get("entities", []):
            candidate = entity.get("color") or entity.get("label")
            if not isinstance(candidate, str) or not candidate.startswith("#"):
                continue
            color = candidate.upper()
            evidence = sentence or str(entity.get("text", "")).strip()
            if evidence:
                groups.setdefault(color, set()).add(evidence)
    return {color: sorted(values)[:25] for color, values in sorted(groups.items())}


def _prompt(groups: Mapping[str, list[str]]) -> str:
    evidence = "\n\n".join(
        f"{color}:\n" + "\n".join(f"- {text}" for text in texts)
        for color, texts in groups.items()
    )
    labels = ", ".join(sorted(HEVA_LABELS))
    return (
        "Classify highlighted heritage-annotation text by color. "
        f"Use exactly one of these controlled labels: {labels}.\n\n"
        f"{evidence}\n\n"
        'Return JSON with two objects: "mapping" maps every hex color to one label; '
        '"reasoning" maps every hex color to a short explanation. '
        "Include every supplied color and no additional colors."
    )


def _query_ollama(
    prompt: str,
    *,
    host: str,
    model: str,
    timeout_seconds: float,
) -> Mapping[str, Any]:
    request = urllib.request.Request(
        f"{host.rstrip('/')}/api/generate",
        data=json.dumps(
            {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.0},
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            envelope = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise AutomaticColorProposalError(
            f"Ollama rejected the request for model {model!r} (HTTP {error.code})."
        ) from error
    except urllib.error.URLError as error:
        raise AutomaticColorProposalError(
            f"Ollama is not reachable at {host}. Start Ollama and ensure {model!r} is installed."
        ) from error
    except (TimeoutError, json.JSONDecodeError) as error:
        raise AutomaticColorProposalError(
            "Ollama did not return valid JSON before the request timed out."
        ) from error
    response_text = envelope.get("response")
    if not isinstance(response_text, str):
        raise AutomaticColorProposalError("Ollama returned no classification response.")
    try:
        result = json.loads(response_text)
    except json.JSONDecodeError as error:
        raise AutomaticColorProposalError(
            "Ollama returned a classification that is not valid JSON."
        ) from error
    if not isinstance(result, dict):
        raise AutomaticColorProposalError("Ollama returned an invalid classification.")
    return result


def generate_automatic_color_proposals(
    project_root: str | Path,
    document_id: str,
    *,
    host: str = DEFAULT_OLLAMA_HOST,
    model: str = DEFAULT_OLLAMA_MODEL,
    timeout_seconds: float = 60,
) -> int:
    """Persist Ollama suggestions for unresolved colors without approving any label."""

    configuration = load_color_configuration(project_root, document_id)
    if configuration.human_confirmed:
        raise AutomaticColorProposalError(
            "This color configuration is already confirmed and will not be replaced."
        )
    unresolved = {
        color.hex
        for color in configuration.colors
        if color.status == "pending_review" and color.suggested_label is None
    }
    if not unresolved:
        raise AutomaticColorProposalError(
            "Every observed color already has a proposal or human decision."
        )
    try:
        source = registered_source_path(project_root, document_id)
    except ReviewQueueError as error:
        raise AutomaticColorProposalError(str(error)) from error
    groups = _group_color_evidence(_raw_records(source))
    available = set(groups)
    if not unresolved.issubset(available):
        missing = ", ".join(sorted(unresolved - available))
        raise AutomaticColorProposalError(
            f"No highlighted text evidence was extracted for: {missing}."
        )
    selected_groups = {color: groups[color] for color in sorted(unresolved)}
    result = _query_ollama(
        _prompt(selected_groups),
        host=host,
        model=model,
        timeout_seconds=timeout_seconds,
    )
    mapping = result.get("mapping")
    reasoning = result.get("reasoning")
    if not isinstance(mapping, dict) or not isinstance(reasoning, dict):
        raise AutomaticColorProposalError(
            "Ollama must return mapping and reasoning objects."
        )
    normalized_mapping = {str(color).upper(): value for color, value in mapping.items()}
    normalized_reasoning = {
        str(color).upper(): value for color, value in reasoning.items()
    }
    if (
        set(normalized_mapping) != unresolved
        or set(normalized_reasoning) != unresolved
    ):
        raise AutomaticColorProposalError(
            "Ollama did not return mapping and reasoning for every unresolved color."
        )
    updated = configuration.model_copy(deep=True)
    try:
        for color in updated.colors:
            if color.hex not in unresolved:
                continue
            label = normalized_mapping[color.hex]
            color.suggested_label = str(label).lower()
            color.reasoning = str(normalized_reasoning[color.hex]).strip() or None
            color.method = "ollama"
        updated.detection_method = "automatic"
        updated = type(updated).model_validate(updated.model_dump(mode="json"))
    except ValidationError as error:
        raise AutomaticColorProposalError(
            "Ollama proposed a label outside the controlled HEVA specification."
        ) from error
    try:
        save_color_configuration(project_root, document_id, updated)
    except ColorMappingError as error:
        raise AutomaticColorProposalError(str(error)) from error
    return len(unresolved)
