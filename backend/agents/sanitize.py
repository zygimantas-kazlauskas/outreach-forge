"""Deterministic guard against banned dashes in generated email copy.

The Writer/Critic system prompts ban em-dashes (U+2014) and en-dashes
(U+2013), but a prompt-level ban is probabilistic: the model violates it
even when told not to. This module is the suspenders to that belt — a
mechanical pass that guarantees the copy we return contains neither.
"""

from __future__ import annotations

import re

EM_DASH = "—"
EN_DASH = "–"

_DIGIT_RANGE = re.compile(r"(?<=\d)\s*[–—]\s*(?=\d)")
_ANY_DASH = re.compile(r"\s*[–—]\s*")
_SPACE_BEFORE_COMMA = re.compile(r"\s+,")
_DOUBLE_COMMA = re.compile(r",\s*,")
_MULTI_SPACE = re.compile(r"[ \t]{2,}")


def has_banned_dashes(text: str) -> bool:
    return EM_DASH in text or EN_DASH in text


def strip_banned_dashes(text: str) -> str:
    """Return `text` with all em/en dashes replaced by clean punctuation.

    En-dashes between digits (number ranges like 9-5) become hyphens;
    every other em/en dash becomes a comma, since that reads correctly in
    the clause-joining cases where the model reaches for a dash.
    """
    text = _DIGIT_RANGE.sub("-", text)
    text = _ANY_DASH.sub(", ", text)
    text = _SPACE_BEFORE_COMMA.sub(",", text)
    text = _DOUBLE_COMMA.sub(",", text)
    text = _MULTI_SPACE.sub(" ", text)
    return text
