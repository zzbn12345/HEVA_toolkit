import re
import spacy

# Cache for blank spaCy models
_nlp_cache = {}

def detect_language(text):
    text_lower = text.lower()
    # Common English stop words
    en_words = {"the", "of", "and", "to", "is", "in", "that", "it", "was", "for"}
    # Common Dutch stop words
    nl_words = {"de", "het", "en", "van", "ik", "je", "we", "ze", "op", "in"}
    
    words = re.findall(r"\b\w+\b", text_lower)
    en_count = sum(1 for w in words if w in en_words)
    nl_count = sum(1 for w in words if w in nl_words)
    
    return "nl" if nl_count > en_count else "en"

def get_nlp_for_lang(lang_code):
    if lang_code not in _nlp_cache:
        nlp = spacy.blank(lang_code)
        nlp.add_pipe("sentencizer")
        
        # Register language-specific newline component
        @spacy.Language.component(f"newline_boundary_{lang_code}")
        def newline_boundary(doc):
            for token in doc[:-1]:
                if "\n" in token.text:
                    doc[token.i + 1].is_sent_start = True
            return doc
        nlp.add_pipe(f"newline_boundary_{lang_code}", before="sentencizer")
        
        # Register parenthetical fixer component to prevent splitting on parenthetical metadata
        @spacy.Language.component(f"parenthetical_fixer_{lang_code}")
        def parenthetical_fixer(doc):
            for token in doc[:-1]:
                if token.text == "(":
                    token.is_sent_start = False
                    if token.i + 1 < len(doc):
                        doc[token.i + 1].is_sent_start = False
            return doc
        nlp.add_pipe(f"parenthetical_fixer_{lang_code}", after="sentencizer")
        
        _nlp_cache[lang_code] = nlp
    return _nlp_cache[lang_code]

def normalize_ligatures(text):
    replacements = {
        "\ufb00": "ff",
        "\ufb01": "fi",
        "\ufb02": "fl",
        "\ufb03": "ffi",
        "\ufb04": "ffl",
        "\ufb05": "ft",
        "\ufb06": "st",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text

def is_margin_block(text):
    """Checks if a block is just a margin code annotation (e.g. EN1, SO3/EN1, AUT, INT, N.v.t.)."""
    text_clean = text.strip()
    if text_clean in {"AUT", "INT", "N.v.t."}:
        return True
    return bool(re.match(r"^[A-Z]{2}\d(?:/[A-Z]{2}\d)*$", text_clean))

def is_colorful(hex_color):
    """Excludes greyscale/neutral text colors (e.g. black, page headers/footers) using RGB variance."""
    hex_color = hex_color.lstrip('#')
    if len(hex_color) != 6:
        return False
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return (max(r, g, b) - min(r, g, b)) > 30
