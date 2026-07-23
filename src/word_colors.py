"""Stable conversion of Word highlight names to normalized hex colors.

This module contains file-format knowledge only. HEVA semantic mappings belong to each
registered document's ``package-metadata.json``.
"""


WORD_HIGHLIGHT_TO_HEX = {
    "YELLOW": "#FFFF00",
    "BRIGHT_GREEN": "#00FF00",
    "TURQUOISE": "#00FFFF",
    "PINK": "#FF00FF",
    "BLUE": "#0000FF",
    "RED": "#FF0000",
    "DARK_BLUE": "#000080",
    "TEAL": "#008080",
    "GREEN": "#008000",
    "VIOLET": "#800080",
    "DARK_RED": "#800000",
    "DARK_YELLOW": "#808000",
    "GRAY_50": "#808080",
    "GRAY_25": "#C0C0C0",
    "BLACK": "#000000",
}
