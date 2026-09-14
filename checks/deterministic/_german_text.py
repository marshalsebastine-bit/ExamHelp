"""Shared, private text-matching helpers for the Family A deterministic
checks (form_operators.py, form_sprache.py). Not a rule module itself and
not part of the public checks API.

The corpus is written almost entirely in the ae/oe/ue/ss ASCII
transliteration of ä/ö/ü/ß (see items/*.json -- "moechte", "waere",
"zweiundachtzig"), with only a handful of literal umlaut characters
scattered in. Every regex built here has to match both spellings, or a
check would silently miss most of the real corpus while working fine on
hand-typed test fixtures that use literal umlauts.
"""
from __future__ import annotations

import re

_UMLAUT_ALTS = {
    "ä": "(?:ä|ae)",
    "ö": "(?:ö|oe)",
    "ü": "(?:ü|ue)",
    "ß": "(?:ß|ss)",
}


def flex(word: str) -> str:
    """Regex fragment matching `word` letter-for-letter, tolerant of the
    ae/oe/ue/ss transliteration in either the pattern or (via re.IGNORECASE)
    the matched text's case."""
    return "".join(_UMLAUT_ALTS.get(ch, re.escape(ch)) for ch in word)


def flex_word(word: str) -> re.Pattern[str]:
    """`flex`, compiled with word boundaries and case-insensitivity -- the
    common case of "does this exact word occur anywhere in the text"."""
    return re.compile(rf"\b{flex(word)}\b", re.IGNORECASE)


def count_matches(words: tuple[str, ...], text: str) -> list[str]:
    """Every occurrence (not just distinct words) of any of `words` in
    `text`, in order of appearance -- used to threshold "at least N markers
    in one sentence" checks (FORM-05) so the finding can show what was
    actually counted."""
    if not text:
        return []
    pattern = re.compile(
        r"\b(?:" + "|".join(flex(w) for w in words) + r")\b", re.IGNORECASE
    )
    return [m.group(0) for m in pattern.finditer(text)]
