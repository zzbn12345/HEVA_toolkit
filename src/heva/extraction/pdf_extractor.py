import fitz  # PyMuPDF
import math
import re
import spacy
from collections.abc import Callable, Sequence

try:
    from .utils import (
        detect_language,
        get_nlp_for_lang,
        is_colorful,
        is_margin_block,
        normalize_ligatures,
    )
except ImportError:  # Preserve a clear error if optional local NLP support is unavailable.
    from heva.extraction.tokenization import (
        detect_language,
        get_nlp_for_lang,
        is_colorful,
        is_margin_block,
        normalize_ligatures,
    )


class PDFTextExtractionError(ValueError):
    """Raised when a PDF text layer cannot safely support sentence extraction."""


def require_readable_text_layer(text: str) -> None:
    """Reject long text layers dominated by encoding artifacts rather than letters.

    Short labels and ordinary numeric fragments are allowed. A long document whose
    non-space characters contain very few Unicode letters cannot be segmented into
    trustworthy natural-language sentences and must be re-exported or OCRed first.
    """

    characters = [character for character in text if not character.isspace()]
    if len(characters) < 200:
        return
    letter_ratio = sum(character.isalpha() for character in characters) / len(characters)
    if letter_ratio < 0.15:
        raise PDFTextExtractionError(
            "The PDF text layer is not readable enough for annotation extraction "
            f"({letter_ratio:.0%} letters). Its embedded font encoding may be broken. "
            "Re-export the PDF with searchable Unicode text or apply OCR, then retry; "
            "HEVA did not persist the corrupted extraction."
        )

def int_to_hex(color_int):
    """Converts a PyMuPDF integer color code to a standard Hex string."""
    r = (color_int >> 16) & 255
    g = (color_int >> 8) & 255
    b = color_int & 255
    return f"#{r:02X}{g:02X}{b:02X}"

def get_block_sort_key(b, rotation):
    """Provides a rotation-aware block sorting key with binning to handle multi-column layouts."""
    x0, y0, x1, y1 = b[0], b[1], b[2], b[3]
    if rotation == 90:
        # Use y1 for rotation 90 because it represents the column alignment start (visual top/left)
        col_bin = round(y1 / 5.0) * 5.0
        return (-col_bin, x0)
    elif rotation == 270:
        col_bin = round(y0 / 5.0) * 5.0
        return (col_bin, -x0)
    elif rotation == 180:
        return (-y0, -x0)
    else:
        line_bin = round(y0 / 3.0) * 3.0
        return (line_bin, x0)

def sort_page_blocks(blocks, page_rect, rotation):
    """Sort blocks after calculating each page's layout model once.

    Full-width blocks divide a page into horizontal bands. Non-full-width
    blocks are then clustered into columns within each band. Layout metadata is
    precomputed before sorting because a sort key must only retrieve a result,
    not rebuild the full layout for every block.
    """
    if not blocks:
        return [], {}
    if rotation == 90:
        block_meta = {b[5]: (0, -round(b[3] / 5.0) * 5.0) for b in blocks}
        return sorted(blocks, key=lambda b: (-round(b[3] / 5.0) * 5.0, b[0])), block_meta
    elif rotation == 270:
        block_meta = {b[5]: (0, round(b[1] / 5.0) * 5.0) for b in blocks}
        return sorted(blocks, key=lambda b: (round(b[1] / 5.0) * 5.0, -b[0])), block_meta
    elif rotation == 180:
        block_meta = {b[5]: (0, 0) for b in blocks}
        return sorted(blocks, key=lambda b: (-b[1], -b[0])), block_meta
        
    def is_full_width(block):
        """Return whether a block crosses the page center at heading width."""
        x0, _, x1, _ = block[:4]
        return (
            x0 < page_rect.width * 0.45
            and x1 > page_rect.width * 0.55
            and (x1 - x0) > page_rect.width * 0.6
        )

    full_width_blocks = [block for block in blocks if is_full_width(block)]
            
    y_boundaries = [0.0, page_rect.height]
    for b in full_width_blocks:
        y_boundaries.extend([b[1], b[3]])
    y_boundaries = sorted(list(set(y_boundaries)))
    
    def band_index(block):
        """Locate a block center in the first matching inclusive band."""
        center_y = (block[1] + block[3]) / 2.0
        for idx in range(len(y_boundaries) - 1):
            if y_boundaries[idx] <= center_y <= y_boundaries[idx + 1]:
                return idx
        return 0

    column_by_band_and_signature = {}
    for current_band in range(len(y_boundaries) - 1):
        y_start = y_boundaries[current_band]
        y_end = y_boundaries[current_band + 1]
        band_blocks = [
            block
            for block in blocks
            if y_start <= (block[1] + block[3]) / 2.0 <= y_end
            and not is_full_width(block)
        ]
        band_blocks.sort(key=lambda block: block[0])

        # Store column bounds incrementally rather than repeatedly scanning all
        # existing members to calculate their minimum and maximum coordinates.
        columns = []
        for block in band_blocks:
            placed = False
            for col in columns:
                overlap_x0 = max(block[0], col["x0"])
                overlap_x1 = min(block[2], col["x1"])
                overlap_width = overlap_x1 - overlap_x0

                block_width = block[2] - block[0]
                col_width = col["x1"] - col["x0"]
                min_w = min(block_width, col_width)

                # 30% horizontal overlap is a safe threshold for column membership
                if overlap_width > 0.3 * min_w or (
                    overlap_width > 0
                    and block[0] >= col["x0"] - 5
                    and block[2] <= col["x1"] + 5
                ):
                    col["members"].append(block)
                    col["x0"] = min(col["x0"], block[0])
                    col["x1"] = max(col["x1"], block[2])
                    placed = True
                    break
            if not placed:
                columns.append({"members": [block], "x0": block[0], "x1": block[2]})

        for column_index, column in enumerate(columns):
            for member in column["members"]:
                signature = (member[4], *member[:4])
                column_by_band_and_signature.setdefault(
                    (current_band, signature), column_index
                )

    block_meta = {}
    sort_keys = []
    for block in blocks:
        current_band = band_index(block)
        column_index = 0
        if not is_full_width(block):
            signature = (block[4], *block[:4])
            column_index = column_by_band_and_signature.get(
                (current_band, signature), 0
            )
        block_meta[block[5]] = (current_band, column_index)
        line_bin = round(block[1] / 3.0) * 3.0
        sort_keys.append((current_band, column_index, line_bin, block[0]))

    sorted_indices = sorted(range(len(blocks)), key=sort_keys.__getitem__)
    sorted_blocks = [blocks[index] for index in sorted_indices]
    return sorted_blocks, block_meta

def rgb_to_hex(rgb_list):
    """Converts a PyMuPDF float RGB list to a standard Hex string."""
    if not rgb_list:
        return "#FFFF00"  # Fallback to standard Yellow if undefined
    return '#' + ''.join(f'{int(round(c * 255)):02X}' for c in rgb_list)


class VerticalRectIndex:
    """Index rectangular page items by horizontal strips.

    PDF text and highlight drawings are commonly spread vertically across a
    page. Indexing every rectangle in the strips it touches lets a word query
    only nearby candidates while returning them in their original order.
    """

    def __init__(self, items, bucket_height=50.0):
        """Build an immutable strip index for items containing a ``rect`` key."""
        self.items = items
        self.bucket_height = bucket_height
        self.buckets = {}
        for item_index, item in enumerate(items):
            for bucket in self._buckets_for_rect(item["rect"]):
                self.buckets.setdefault(bucket, []).append(item_index)

    def _buckets_for_rect(self, rect):
        """Return every vertical bucket touched by a rectangle."""
        first = math.floor(rect.y0 / self.bucket_height)
        last = math.floor(rect.y1 / self.bucket_height)
        return range(first, last + 1)

    def candidates(self, rect):
        """Return nearby indexed items in their original sequence."""
        candidate_indices = set()
        for bucket in self._buckets_for_rect(rect):
            candidate_indices.update(self.buckets.get(bucket, ()))
        return [self.items[index] for index in sorted(candidate_indices)]


def find_highlight_color(word_rect, highlight_drawings, drawing_index=None):
    """Return the color with the greatest meaningful overlap with a word."""
    candidates = (
        drawing_index.candidates(word_rect)
        if drawing_index is not None
        else highlight_drawings
    )
    highlight_color = None
    max_overlap = 0.0
    for drawing in candidates:
        overlap = (word_rect & drawing["rect"]).get_area()
        if overlap > max_overlap:
            max_overlap = overlap
            highlight_color = drawing["color"]
    if max_overlap < 0.1 * word_rect.get_area():
        return None
    return highlight_color


def find_text_span_color(word_rect, spans, span_index=None):
    """Return the colorful first text span containing a word's center.

    The first containing span remains authoritative even when it is neutral,
    matching the extractor's established fallback behavior.
    """
    word_center = fitz.Point(
        (word_rect.x0 + word_rect.x1) / 2,
        (word_rect.y0 + word_rect.y1) / 2,
    )
    candidates = span_index.candidates(word_rect) if span_index else spans
    for span in candidates:
        if word_center in span["rect"]:
            return span["color"] if is_colorful(span["color"]) else None
    return None


def group_words_by_block(words):
    """Group page words by block number while preserving source order."""
    grouped = {}
    for word in words:
        grouped.setdefault(word["block_no"], []).append(word)
    return grouped

def is_header_footer(b, page_rect, rotation):
    """Checks if a block is in the page margins (header or footer)."""
    x0, y0, x1, y1 = b[0], b[1], b[2], b[3]
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0
    margin = 70.0
    if rotation == 90 or rotation == 270:
        return cx < margin or cx > page_rect.width - margin
    else:
        return cy < margin or cy > page_rect.height - margin


def iter_sentence_word_spans(sentences, global_word_spans):
    """Yield each non-empty sentence with only its contained word spans.

    Both spaCy sentences and reconstructed PDF word spans are ordered by their
    document offsets. A moving cursor therefore avoids rescanning every word in
    the document for every sentence while preserving the original containment
    rule.
    """
    word_cursor = 0
    prefix_pattern = r"^(\w+(?:\s+\w+){0,2})\s*:\s*"

    for sent in sentences:
        sent_text = sent.text.strip()
        if not sent_text:
            continue

        prefix_match = re.match(prefix_pattern, sent_text)
        sent_start_offset = 0
        if prefix_match:
            prefix_len = len(prefix_match.group(0))
            sent_text = sent_text[prefix_len:].strip()
            sent_start_offset = prefix_len

        sent_start_in_doc = sent.start_char + sent_start_offset
        sent_end_in_doc = sent.end_char

        while (
            word_cursor < len(global_word_spans)
            and global_word_spans[word_cursor]["end"] <= sent_start_in_doc
        ):
            word_cursor += 1

        sent_words = []
        sent_pages = []
        span_index = word_cursor
        while (
            span_index < len(global_word_spans)
            and global_word_spans[span_index]["start"] < sent_end_in_doc
        ):
            word_span = global_word_spans[span_index]
            if (
                word_span["start"] >= sent_start_in_doc
                and word_span["end"] <= sent_end_in_doc
            ):
                sent_words.append({
                    "word": word_span["word"],
                    "start": word_span["start"] - sent_start_in_doc,
                    "end": word_span["end"] - sent_start_in_doc,
                })
                sent_pages.append(word_span["page"])
            span_index += 1

        yield sent, sent_text, sent_start_offset, sent_words, sent_pages

def extract_colored_highlights(
    pdf_path,
    color_label_map=None,
    progress_callback: Callable[[int, int], None] | None = None,
    cancellation_callback: Callable[[], bool] | None = None,
    page_numbers: Sequence[int] | None = None,
):
    """
    Extracts highlights along with their exact hex color codes or mapped labels.
    It uses an automated drawing-overlap alignment algorithm to find and map
    colored highlighted text within parsed sentences, generating BIO-tagged NER output.
    """
    doc = fitz.open(pdf_path)

    if page_numbers is None:
        selected_page_indices = list(range(len(doc)))
    else:
        if not page_numbers:
            doc.close()
            raise ValueError("Select at least one PDF page for extraction.")
        if any(
            not isinstance(page, int)
            or isinstance(page, bool)
            or page < 1
            or page > len(doc)
            for page in page_numbers
        ):
            doc.close()
            raise ValueError(f"PDF pages must be between 1 and {len(doc)}.")
        if len(set(page_numbers)) != len(page_numbers):
            doc.close()
            raise ValueError("PDF page selection cannot contain duplicates.")
        selected_page_indices = [page - 1 for page in sorted(page_numbers)]

    final_output = []
    sentence_id = 1
    detected_colors = set()

    global_reconstructed_text = ""
    global_word_spans = []

    for completed_pages, page_num in enumerate(selected_page_indices, start=1):
        if cancellation_callback is not None and cancellation_callback():
            from heva.extraction.errors import ExtractionCancelled

            doc.close()
            raise ExtractionCancelled(
                f"Extraction was cancelled before source page {page_num + 1}."
            )
        page = doc[page_num]
        page_rect = page.rect
        # DICT uses the superset of flags required by all three derived views,
        # including image blocks returned by the established blocks request.
        text_page = page.get_textpage(flags=fitz.TEXTFLAGS_DICT)
        
        # 1. Extract non-white fill drawings as highlights
        drawings = page.get_drawings()
        highlight_drawings = []
        for d in drawings:
            if d["type"] == "f" and d["fill"] is not None:
                # Skip white background/boxes
                if d["fill"] == (1.0, 1.0, 1.0) or d["fill"] == (1, 1, 1):
                    continue
                highlight_drawings.append({
                    "rect": d["rect"],
                    "color": rgb_to_hex(d["fill"])
                })
        highlight_index = VerticalRectIndex(highlight_drawings)

        # Extract spans with their coordinates and colors
        text_dict = page.get_text("dict", textpage=text_page)
        spans = []
        for block in text_dict["blocks"]:
            if "lines" in block:
                for line in block["lines"]:
                    for span in line["spans"]:
                        spans.append({
                            "rect": fitz.Rect(span["bbox"]),
                            "color": int_to_hex(span["color"]),
                            "text": span["text"]
                        })
        span_index = VerticalRectIndex(spans)

        # 2. Extract words with coordinates and check highlight overlap
        raw_words = page.get_text("words", textpage=text_page)
        words = []
        for w in raw_words:
            w_text = normalize_ligatures(w[4])
            w_rect = fitz.Rect(w[0], w[1], w[2], w[3])
            highlight_color = find_highlight_color(
                w_rect, highlight_drawings, highlight_index
            )

            # Fallback to text color if no drawing highlight overlaps
            if highlight_color is None:
                highlight_color = find_text_span_color(w_rect, spans, span_index)

            if highlight_color:
                detected_colors.add(highlight_color)
            words.append({
                "text": w_text,
                "rect": w_rect,
                "block_no": w[5],
                "line_no": w[6],
                "word_no": w[7],
                "color": highlight_color
            })

        # 3. Sort blocks
        blocks = page.get_text("blocks", textpage=text_page)
        blocks = [b for b in blocks if not is_margin_block(b[4]) and not is_header_footer(b, page_rect, page.rotation)]
        blocks, block_metadata = sort_page_blocks(blocks, page_rect, page.rotation)
        words_by_block = group_words_by_block(words)

        # Reconstruct page text block by block
        page_reconstructed_text = ""
        page_word_spans = []
        
        for b_idx, block in enumerate(blocks):
            block_no = block[5]
            block_words = words_by_block.get(block_no, [])
            if not block_words:
                continue
                
            i = 0
            while i < len(block_words):
                w = block_words[i]
                
                # Check for paragraph breaks inside block by looking at vertical line gap
                separator = " "
                if i > 0:
                    prev_w = block_words[i - 1]
                    if w["line_no"] != prev_w["line_no"]:
                        vertical_gap = w["rect"].y0 - prev_w["rect"].y1
                        if vertical_gap > 6.0:
                            separator = "\n"

                if w["text"].endswith("-") and i + 1 < len(block_words) and block_words[i+1]["line_no"] != w["line_no"]:
                    merged_text = w["text"][:-1] + block_words[i+1]["text"]
                    merged_color = w["color"] or block_words[i+1]["color"]
                    
                    if separator == "\n" and page_reconstructed_text.endswith(" "):
                        page_reconstructed_text = page_reconstructed_text[:-1] + "\n"
                        
                    start_idx = len(page_reconstructed_text)
                    page_reconstructed_text += merged_text + " "
                    end_idx = len(page_reconstructed_text) - 1
                    
                    merged_word = {"text": merged_text, "color": merged_color}
                    page_word_spans.append({"word": merged_word, "start": start_idx, "end": end_idx})
                    i += 2
                else:
                    if separator == "\n" and page_reconstructed_text.endswith(" "):
                        page_reconstructed_text = page_reconstructed_text[:-1] + "\n"
                        
                    start_idx = len(page_reconstructed_text)
                    page_reconstructed_text += w["text"] + " "
                    end_idx = len(page_reconstructed_text) - 1
                    
                    page_word_spans.append({"word": w, "start": start_idx, "end": end_idx})
                    i += 1
            
            # Decide separator to next block
            if b_idx + 1 < len(blocks):
                next_block = blocks[b_idx + 1]
                separator = " "
                
                # 1. Different columns/bands or line transition
                b1_meta = block_metadata.get(block[5], (0, 0))
                b2_meta = block_metadata.get(next_block[5], (0, 0))
                if b1_meta[0] != b2_meta[0] or b1_meta[1] != b2_meta[1]:
                    separator = "\n"
                elif page.rotation not in (90, 270):
                    line_bin_1 = round(block[1] / 3.0) * 3.0
                    line_bin_2 = round(next_block[1] / 3.0) * 3.0
                    if line_bin_1 != line_bin_2:
                        separator = "\n"
                else:
                    last_word_text = block_words[-1]["text"].strip()
                    if last_word_text.endswith(":") or last_word_text.endswith(".") or last_word_text.endswith("?"):
                        separator = "\n"
                    # 3. Large distance
                    else:
                        if page.rotation == 90:
                            dist = next_block[0] - block[2]
                        else:
                            dist = next_block[1] - block[3]
                        if dist > 18.0:
                            separator = "\n"
                
                if separator == "\n" and page_reconstructed_text.endswith(" "):
                    page_reconstructed_text = page_reconstructed_text[:-1] + "\n"

        page_reconstructed_text = page_reconstructed_text.strip()
        if not page_reconstructed_text:
            if progress_callback is not None:
                progress_callback(completed_pages, len(selected_page_indices))
            continue

        # Append page text to global text with a space boundary to prevent splitting sentences on page join
        if global_reconstructed_text:
            global_reconstructed_text += " "
            
        offset_shift = len(global_reconstructed_text)
        
        for pws in page_word_spans:
            global_word_spans.append({
                "word": pws["word"],
                "start": pws["start"] + offset_shift,
                "end": pws["end"] + offset_shift,
                "page": page_num + 1
            })
            
        global_reconstructed_text += page_reconstructed_text
        if progress_callback is not None:
            progress_callback(completed_pages, len(selected_page_indices))

    if cancellation_callback is not None and cancellation_callback():
        from heva.extraction.errors import ExtractionCancelled

        doc.close()
        raise ExtractionCancelled("Extraction was cancelled before sentence analysis.")

    # Refuse corrupted font mappings before NLP can turn them into plausible records.
    require_readable_text_layer(global_reconstructed_text)

    # Dynamically load the language-specific spaCy blank model
    lang_code = detect_language(global_reconstructed_text)
    nlp = get_nlp_for_lang(lang_code)

    # Segment the entire document text into sentences using spaCy
    doc_global = nlp(global_reconstructed_text)
    
    for sent, sent_text, sent_start_offset, sent_words, sent_pages in (
        iter_sentence_word_spans(doc_global.sents, global_word_spans)
    ):

        # Extract entities based on color highlighting
        entities = []
        current_entity = None
        for sw in sent_words:
            color = sw["word"]["color"]
            if color is not None:
                if current_entity and current_entity["color"] == color:
                    current_entity["end"] = sw["end"]
                    current_entity["words"].append(sw)
                else:
                    current_entity = {
                        "color": color,
                        "start": sw["start"],
                        "end": sw["end"],
                        "words": [sw]
                    }
                    entities.append(current_entity)
            else:
                current_entity = None

        # Only keep sentences that contain highlighted text
        if not entities:
            continue

        final_entities = []
        for ent in entities:
            ent_text = sent_text[ent["start"]:ent["end"]]
            
            # Strip leading/trailing spaces
            clean_start = ent["start"] + (len(ent_text) - len(ent_text.lstrip()))
            clean_text = ent_text.strip()
            
            # Strip trailing punctuation
            while clean_text and clean_text[-1] in " ,.:;":
                clean_text = clean_text[:-1]
            
            clean_end = clean_start + len(clean_text)
            
            label = ent["color"]
            if color_label_map and label in color_label_map:
                label = color_label_map[label]
            
            final_entities.append({
                "start": clean_start,
                "end": clean_end,
                "text": clean_text,
                "label": label,
                "color": ent["color"],
            })

        # Get tokens
        sent_tokens = []
        token_indices = []
        for token in sent:
            tok_start_in_sent = token.idx - sent.start_char
            if tok_start_in_sent >= sent_start_offset:
                rel_tok_start = tok_start_in_sent - sent_start_offset
                rel_tok_end = rel_tok_start + len(token.text)
                sent_tokens.append(token.text)
                token_indices.append((rel_tok_start, rel_tok_end))

        # Generate BIO tags
        ner_tags = ["O"] * len(sent_tokens)
        for ent in final_entities:
            ent_start = ent["start"]
            ent_end = ent["end"]
            label = ent["label"]
            is_first = True
            for i, (t_start, t_end) in enumerate(token_indices):
                if t_start >= ent_start and t_end <= ent_end:
                    if is_first:
                        ner_tags[i] = f"B-{label}"
                        is_first = False
                    else:
                        ner_tags[i] = f"I-{label}"

        values = sorted(list(set(ent["label"] for ent in final_entities)))

        # If there are any entities remaining, keep sentence
        if final_entities:
            sent_page = sent_pages[0] if sent_pages else 1
            final_output.append({
                "sentence_id": sentence_id,
                "page": sent_page,
                "sentence": sent_text,
                "tokens": sent_tokens,
                "values": values,
                "entities": final_entities,
                "ner_tags": ner_tags
            })
            sentence_id += 1

    # Warn about detected colors that are not in the color mapping
    unmapped_colors = detected_colors
    if color_label_map:
        unmapped_colors = detected_colors - set(color_label_map.keys())

    if unmapped_colors:
        if color_label_map:
            print(f"   [!] Warning: The following highlight colors were found but are not defined in the color map: {sorted(list(unmapped_colors))}")
            print(f"       They will default to their raw hex codes in the output JSON.")
        else:
            print(f"   [i] Info: No color map applied. The following raw highlight colors were detected: {sorted(list(unmapped_colors))}")

    return final_output
