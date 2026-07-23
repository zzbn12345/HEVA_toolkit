import fitz  # PyMuPDF
import re
import spacy

from utils import (
    detect_language,
    get_nlp_for_lang,
    normalize_ligatures,
    is_margin_block,
    is_colorful,
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
    """Sorts page blocks by dividing the page into bands and clustering blocks horizontally into columns."""
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
        
    full_width_blocks = []
    for b in blocks:
        x0, y0, x1, y1 = b[0], b[1], b[2], b[3]
        if x0 < page_rect.width * 0.45 and x1 > page_rect.width * 0.55 and (x1 - x0) > page_rect.width * 0.6:
            full_width_blocks.append(b)
            
    y_boundaries = [0.0, page_rect.height]
    for b in full_width_blocks:
        y_boundaries.extend([b[1], b[3]])
    y_boundaries = sorted(list(set(y_boundaries)))
    
    block_meta = {}
    
    def get_sort_key(b):
        x0, y0, x1, y1 = b[0], b[1], b[2], b[3]
        cy = (y0 + y1) / 2.0
        
        band_idx = 0
        for idx in range(len(y_boundaries) - 1):
            if y_boundaries[idx] <= cy <= y_boundaries[idx + 1]:
                band_idx = idx
                break
                
        y_start, y_end = y_boundaries[band_idx], y_boundaries[band_idx + 1]
        band_blocks = [x for x in blocks if y_start <= (x[1] + x[3])/2.0 <= y_end]
        
        # Filter out full width blocks from column clustering within the band
        band_cols_blocks = [x for x in band_blocks if x not in full_width_blocks]
        
        # Sort band blocks by x0 to identify columns from left to right
        band_cols_blocks = sorted(band_cols_blocks, key=lambda x: x[0])
        
        columns = []
        for x_block in band_cols_blocks:
            placed = False
            for col in columns:
                col_x0 = min(member[0] for member in col)
                col_x1 = max(member[2] for member in col)
                
                overlap_x0 = max(x_block[0], col_x0)
                overlap_x1 = min(x_block[2], col_x1)
                overlap_width = overlap_x1 - overlap_x0
                
                b_width = x_block[2] - x_block[0]
                col_width = col_x1 - col_x0
                min_w = min(b_width, col_width)
                
                # 30% horizontal overlap is a safe threshold for column membership
                if overlap_width > 0.3 * min_w or (overlap_width > 0 and (x_block[0] >= col_x0 - 5 and x_block[2] <= col_x1 + 5)):
                    col.append(x_block)
                    placed = True
                    break
            if not placed:
                columns.append([x_block])
                
        # Find which column this block belongs to
        col_idx = 0
        if b not in full_width_blocks:
            for idx, col in enumerate(columns):
                if any(x[4] == b[4] and x[:4] == b[:4] for x in col):
                    col_idx = idx
                    break
                    
        block_meta[b[5]] = (band_idx, col_idx)
        line_bin = round(y0 / 3.0) * 3.0
        return (band_idx, col_idx, line_bin, x0)
        
    sorted_blocks = sorted(blocks, key=get_sort_key)
    return sorted_blocks, block_meta

def rgb_to_hex(rgb_list):
    """Converts a PyMuPDF float RGB list to a standard Hex string."""
    if not rgb_list:
        return "#FFFF00"  # Fallback to standard Yellow if undefined
    return '#' + ''.join(f'{int(round(c * 255)):02X}' for c in rgb_list)

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

def extract_colored_highlights(pdf_path, color_label_map=None):
    """
    Extracts highlights along with their exact hex color codes or mapped labels.
    It uses an automated drawing-overlap alignment algorithm to find and map
    colored highlighted text within parsed sentences, generating BIO-tagged NER output.
    """
    doc = fitz.open(pdf_path)

    final_output = []
    sentence_id = 1
    detected_colors = set()

    global_reconstructed_text = ""
    global_word_spans = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        page_rect = page.rect
        
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

        # Extract spans with their coordinates and colors
        text_dict = page.get_text("dict")
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

        # 2. Extract words with coordinates and check highlight overlap
        raw_words = page.get_text("words")
        words = []
        for w in raw_words:
            w_text = normalize_ligatures(w[4])
            w_rect = fitz.Rect(w[0], w[1], w[2], w[3])
            highlight_color = None
            max_overlap = 0
            for hd in highlight_drawings:
                intersect = w_rect & hd["rect"]
                area = intersect.get_area()
                if area > max_overlap:
                    max_overlap = area
                    highlight_color = hd["color"]
            if max_overlap < 0.1 * w_rect.get_area():
                highlight_color = None

            # Fallback to text color if no drawing highlight overlaps
            if highlight_color is None:
                w_center = fitz.Point((w_rect.x0 + w_rect.x1) / 2, (w_rect.y0 + w_rect.y1) / 2)
                for span in spans:
                    if w_center in span["rect"]:
                        span_color = span["color"]
                        if is_colorful(span_color):
                            highlight_color = span_color
                        break

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
        blocks = page.get_text("blocks")
        blocks = [b for b in blocks if not is_margin_block(b[4]) and not is_header_footer(b, page_rect, page.rotation)]
        blocks, block_metadata = sort_page_blocks(blocks, page_rect, page.rotation)

        # Reconstruct page text block by block
        page_reconstructed_text = ""
        page_word_spans = []
        
        for b_idx, block in enumerate(blocks):
            block_no = block[5]
            block_words = [w for w in words if w["block_no"] == block_no]
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

    # Dynamically load the language-specific spaCy blank model
    lang_code = detect_language(global_reconstructed_text)
    nlp = get_nlp_for_lang(lang_code)

    # Segment the entire document text into sentences using spaCy
    doc_global = nlp(global_reconstructed_text)
    
    # Generalized prefix matcher
    prefix_pattern = r"^(\w+(?:\s+\w+){0,2})\s*:\s*"

    for sent in doc_global.sents:
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

        sent_words = []
        sent_pages = []
        for ws in global_word_spans:
            if ws["start"] >= sent_start_in_doc and ws["end"] <= sent_end_in_doc:
                sent_words.append({
                    "word": ws["word"],
                    "start": ws["start"] - sent_start_in_doc,
                    "end": ws["end"] - sent_start_in_doc
                })
                sent_pages.append(ws["page"])

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
                "label": label
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
