import docx
import re
import spacy

from word_colors import WORD_HIGHLIGHT_TO_HEX
from utils import (
    detect_language,
    get_nlp_for_lang,
    normalize_ligatures,
    is_colorful,
)

def extract_docx_highlights(docx_path, color_label_map=None):
    """
    Extracts highlights and colored text from a Word document (.docx).
    Segments paragraphs into sentences, aligns highlighted run offsets,
    and returns BIO-tagged NER output matching the format of PDF extraction.
    """
    doc = docx.Document(docx_path)
    final_output = []
    sentence_id = 1
    detected_colors = set()
    current_page = 1

    for p_idx, para in enumerate(doc.paragraphs):
        # Check for page breaks in the paragraph's XML before skipping empty ones
        for el in para._element.iter():
            if el.tag.endswith('lastRenderedPageBreak') or (el.tag.endswith('br') and el.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}type') == 'page'):
                current_page += 1

        para_text = para.text
        if not para_text.strip():
            continue

        # 1. Map each character in the paragraph to its highlight color / text color
        # Build paragraph text and character-level colors from runs
        char_colors = []
        reconstructed_text = ""
        
        for run in para.runs:
            run_text = normalize_ligatures(run.text)
            if not run_text:
                continue
            
            # Detect highlight color
            highlight = None
            if run.font.highlight_color is not None:
                # Get the name of the highlight color (e.g. 'YELLOW', 'PINK')
                try:
                    name = run.font.highlight_color.name
                    if name and name != "AUTO":
                        highlight = WORD_HIGHLIGHT_TO_HEX.get(name, name)
                except AttributeError:
                    pass
            
            # Fallback to font color if no highlight
            if highlight is None:
                if run.font.color and run.font.color.rgb:
                    rgb = run.font.color.rgb
                    hex_color = f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"
                    if is_colorful(hex_color):
                        highlight = hex_color
            
            if highlight:
                detected_colors.add(highlight)
                
            # Append run text and track char-level colors
            reconstructed_text += run_text
            char_colors.extend([highlight] * len(run_text))

        reconstructed_text = reconstructed_text.strip()
        if not reconstructed_text:
            continue

        # 2. Segment the paragraph into sentences using spaCy
        lang_code = detect_language(reconstructed_text)
        nlp = get_nlp_for_lang(lang_code)
        doc_para = nlp(reconstructed_text)

        prefix_pattern = r"^(\w+(?:\s+\w+){0,2})\s*:\s*"

        for sent in doc_para.sents:
            sent_text = sent.text.strip()
            if not sent_text:
                continue

            prefix_match = re.match(prefix_pattern, sent_text)
            sent_start_offset = 0
            if prefix_match:
                prefix_len = len(prefix_match.group(0))
                sent_text = sent_text[prefix_len:].strip()
                sent_start_offset = prefix_len

            sent_start_in_para = sent.start_char + sent_start_offset
            sent_end_in_para = sent.end_char

            # Get tokens and their start/end indices in sentence
            sent_tokens = []
            token_indices = []
            for token in sent:
                tok_start_in_sent = token.idx - sent.start_char
                if tok_start_in_sent >= sent_start_offset:
                    rel_tok_start = tok_start_in_sent - sent_start_offset
                    rel_tok_end = rel_tok_start + len(token.text)
                    sent_tokens.append(token.text)
                    token_indices.append((rel_tok_start, rel_tok_end))

            # Extract entities based on token-level colors
            entities = []
            current_entity = None
            
            # Map tokens to their dominant color
            token_colors = []
            for t_idx, (t_start, t_end) in enumerate(token_indices):
                # Map back to paragraph offsets
                p_start = sent.start_char + sent_start_offset + t_start
                p_end = sent.start_char + sent_start_offset + t_end
                
                # Check colors of characters inside the token
                tok_colors = [c for c in char_colors[p_start:p_end] if c is not None]
                tok_color = None
                if tok_colors:
                    tok_color = max(set(tok_colors), key=tok_colors.count)
                token_colors.append(tok_color)
            
            # Group consecutive tokens with the same color
            for t_idx, (t_start, t_end) in enumerate(token_indices):
                color = token_colors[t_idx]
                if color is not None:
                    if current_entity and current_entity["color"] == color:
                        current_entity["end"] = t_end
                    else:
                        current_entity = {
                            "color": color,
                            "start": t_start,
                            "end": t_end
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
                if not clean_text:
                    continue
                
                label = ent["color"]
                if color_label_map and label in color_label_map:
                    label = color_label_map[label]
                # Also try mapping highlight color names (e.g. 'YELLOW') directly
                elif color_label_map:
                    name_found = False
                    for name, hex_val in WORD_HIGHLIGHT_TO_HEX.items():
                        if hex_val == label and name in color_label_map:
                            label = color_label_map[name]
                            name_found = True
                            break
                
                final_entities.append({
                    "start": clean_start,
                    "end": clean_end,
                    "text": clean_text,
                    "label": label,
                    "color": ent["color"],
                })

            if not final_entities:
                continue

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

            final_output.append({
                "sentence_id": sentence_id,
                "page": current_page,
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
        matched_keys = set()
        for c in unmapped_colors:
            for name, hex_val in WORD_HIGHLIGHT_TO_HEX.items():
                if hex_val == c and name in color_label_map:
                    matched_keys.add(c)
        unmapped_colors = unmapped_colors - matched_keys

    if unmapped_colors:
        if color_label_map:
            print(f"   [!] Warning: The following highlight colors were found but are not defined in the color map: {sorted(list(unmapped_colors))}")
            print(f"       They will default to their raw hex codes in the output JSON.")
        else:
            print(f"   [i] Info: No color map applied. The following raw highlight colors were detected: {sorted(list(unmapped_colors))}")

    return final_output
