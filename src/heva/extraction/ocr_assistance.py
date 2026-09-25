"""Explicit OCR-assisted candidate extraction for PDFs with broken text encoding."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Callable, Sequence

import fitz

from heva.extraction.errors import ExtractionCancelled


TOKEN = re.compile(r"\w+(?:['’\-]\w+)*|[^\w\s]", re.UNICODE)


class OCRAssistanceError(ValueError):
    """Raised when an assisted candidate cannot be produced safely."""

    def __init__(self, message: str, *, code: str = "ocr_assistance_failed") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class OCRCandidateResult:
    """Summary of a separately persisted, review-required OCR candidate."""

    records: list[dict]
    engine: str
    engine_version: str
    render_dpi: int
    mean_confidence: float
    processed_pages: list[int]


def _engine_version() -> str:
    executable = shutil.which("tesseract")
    if executable is None:
        raise OCRAssistanceError(
            "Tesseract is not installed in the HEVA environment.",
            code="ocr_dependency_missing",
        )
    completed = subprocess.run(
        [executable, "--version"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise OCRAssistanceError(
            "Tesseract could not be started.",
            code="ocr_dependency_unavailable",
        )
    return completed.stdout.splitlines()[0].strip()


def _overlap_ratio(first: fitz.Rect, second: fitz.Rect) -> float:
    intersection = first & second
    if intersection.is_empty or first.get_area() <= 0:
        return 0.0
    return intersection.get_area() / first.get_area()


def _native_colored_spans(page: fitz.Page, accepted_colors: set[str]) -> list[tuple[fitz.Rect, str]]:
    spans: list[tuple[fitz.Rect, str]] = []
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                color = f"#{span.get('color', 0):06X}"
                if color in accepted_colors:
                    spans.append((fitz.Rect(span["bbox"]), color))
    return spans


def _native_table_cells(page: fitz.Page) -> list[fitz.Rect]:
    """Return ruled table cells, leaving non-table page regions unaffected."""

    cells: list[fitz.Rect] = []
    try:
        tables = page.find_tables().tables
    except (AttributeError, RuntimeError, ValueError):
        return cells
    for table in tables:
        if table.row_count < 2 or table.col_count < 2:
            continue
        cells.extend(
            fitz.Rect(cell)
            for cell in table.cells
            if cell is not None and fitz.Rect(cell).get_area() > 0
        )
    return cells


def _ocr_page_words(
    page: fitz.Page,
    *,
    executable: str,
    language: str,
    render_dpi: int,
    directory: Path,
) -> list[dict]:
    scale = render_dpi / 72
    image = directory / f"page-{page.number + 1}.png"
    page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False).save(image)
    completed = subprocess.run(
        [executable, str(image), "stdout", "-l", language, "tsv"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip().splitlines()[-1] if completed.stderr.strip() else "unknown error"
        raise OCRAssistanceError(f"OCR failed on source page {page.number + 1}: {detail}")
    words: list[dict] = []
    for line in completed.stdout.splitlines()[1:]:
        columns = line.split("\t", 11)
        if len(columns) != 12:
            continue
        level, _, block, paragraph, line_number, word_number = columns[:6]
        left_value, top_value, width_value, height_value, confidence_value, text_value = columns[6:]
        text = text_value.strip()
        if level != "5" or not text:
            continue
        try:
            confidence = float(confidence_value)
            left, top, width, height = (
                int(value) for value in (left_value, top_value, width_value, height_value)
            )
        except (TypeError, ValueError) as error:
            raise OCRAssistanceError("Tesseract returned malformed word evidence.") from error
        if confidence < 0:
            continue
        words.append(
            {
                "text": text,
                "confidence": confidence,
                "block": int(block),
                "paragraph": int(paragraph),
                "line": int(line_number),
                "word": int(word_number),
                "bbox": fitz.Rect(
                    left / scale,
                    top / scale,
                    (left + width) / scale,
                    (top + height) / scale,
                ),
            }
        )
    return words


def _records_from_words(
    words: list[dict],
    *,
    page_number: int,
    colored_spans: list[tuple[fitz.Rect, str]],
    table_cells: list[fitz.Rect] | None = None,
    first_sentence_id: int,
) -> list[dict]:
    groups: dict[tuple, list[dict]] = {}
    table_cells = table_cells or []
    for word in words:
        matches = [
            (ratio, color)
            for span, color in colored_spans
            if (ratio := _overlap_ratio(word["bbox"], span)) >= 0.35
        ]
        word["color"] = max(matches)[1] if matches else None
        center = (word["bbox"].x0 + word["bbox"].x1) / 2, (
            word["bbox"].y0 + word["bbox"].y1
        ) / 2
        cell_index = next(
            (index for index, cell in enumerate(table_cells) if cell.contains(center)),
            None,
        )
        group_key = (
            ("table_cell", cell_index)
            if cell_index is not None
            else ("paragraph", word["block"], word["paragraph"])
        )
        groups.setdefault(group_key, []).append(word)

    records: list[dict] = []
    sentence_id = first_sentence_id
    ordered_groups = sorted(
        groups.values(),
        key=lambda group: (
            min(word["bbox"].y0 for word in group),
            min(word["bbox"].x0 for word in group),
        ),
    )
    for group in ordered_groups:
        group.sort(key=lambda item: (item["line"], item["word"], item["bbox"].x0))
        text = ""
        positioned: list[tuple[dict, int, int]] = []
        previous_line = None
        for word in group:
            separator = "" if not text else ("\n" if previous_line != word["line"] else " ")
            text += separator
            start = len(text)
            text += word["text"]
            positioned.append((word, start, len(text)))
            previous_line = word["line"]
        if not any(word["color"] for word, _, _ in positioned):
            continue

        entities: list[dict] = []
        for word, start, end in positioned:
            color = word["color"]
            if color is None:
                continue
            if entities and entities[-1]["color"] == color and start <= entities[-1]["end"] + 1:
                entities[-1]["end"] = end
                entities[-1]["text"] = text[entities[-1]["start"] : end]
            else:
                entities.append(
                    {"start": start, "end": end, "text": text[start:end], "label": color, "color": color}
                )

        token_matches = list(TOKEN.finditer(text))
        tags = ["O"] * len(token_matches)
        for entity in entities:
            first = True
            for index, token in enumerate(token_matches):
                if token.start() >= entity["start"] and token.end() <= entity["end"]:
                    tags[index] = f"{'B' if first else 'I'}-{entity['color']}"
                    first = False
        records.append(
            {
                "sentence_id": sentence_id,
                "page": page_number,
                "sentence": text,
                "tokens": [match.group() for match in token_matches],
                "values": sorted({entity["color"] for entity in entities}),
                "entities": entities,
                "ner_tags": tags,
            }
        )
        sentence_id += 1
    return records


def extract_ocr_candidate(
    source: str | Path,
    *,
    accepted_colors: Sequence[str],
    language: str = "eng",
    render_dpi: int = 288,
    page_numbers: Sequence[int] | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    cancellation_callback: Callable[[], bool] | None = None,
) -> OCRCandidateResult:
    """OCR selected pages and align readable words to existing colored PDF spans."""

    source_path = Path(source)
    executable = shutil.which("tesseract")
    version = _engine_version()
    assert executable is not None
    colors = {color.upper() for color in accepted_colors}
    if not colors:
        raise OCRAssistanceError("Confirm at least one document color before assisted extraction.")
    records: list[dict] = []
    confidences: list[float] = []
    processed_pages: list[int] = []
    with fitz.open(source_path) as document, tempfile.TemporaryDirectory() as temp:
        indices = [number - 1 for number in page_numbers] if page_numbers else list(range(len(document)))
        if any(index < 0 or index >= len(document) for index in indices):
            raise OCRAssistanceError("The assisted extraction page selection is outside the PDF.")
        for completed, index in enumerate(indices, start=1):
            if cancellation_callback is not None and cancellation_callback():
                raise ExtractionCancelled("OCR assistance was cancelled before the next source page.")
            page = document[index]
            words = _ocr_page_words(
                page,
                executable=executable,
                language=language,
                render_dpi=render_dpi,
                directory=Path(temp),
            )
            confidences.extend(word["confidence"] for word in words)
            records.extend(
                _records_from_words(
                    words,
                    page_number=index + 1,
                    colored_spans=_native_colored_spans(page, colors),
                    table_cells=_native_table_cells(page),
                    first_sentence_id=len(records) + 1,
                )
            )
            processed_pages.append(index + 1)
            if progress_callback is not None:
                progress_callback(completed, len(indices))
    if not records:
        raise OCRAssistanceError(
            "OCR produced no colored candidate records; no project data was changed.",
            code="ocr_candidate_empty",
        )
    return OCRCandidateResult(
        records=records,
        engine="tesseract",
        engine_version=version,
        render_dpi=render_dpi,
        mean_confidence=(sum(confidences) / len(confidences)) if confidences else 0.0,
        processed_pages=processed_pages,
    )
