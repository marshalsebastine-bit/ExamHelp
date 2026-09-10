"""Shared lexical normalisation for BM25 indexing and querying."""
from __future__ import annotations

import re


# Keep German letters (including umlauts and ß) and numbers; discard punctuation.
# Thus a user query such as ``begründen?`` contains the same token as ``begründen``
# in a source document.
TOKEN_PATTERN = re.compile(r"[0-9a-zäöüß]+", re.IGNORECASE)


def tokenize(text: str) -> list[str]:
    """Return case-normalised lexical tokens for German BM25 retrieval."""
    # ``lower`` retains ß, keeping source and query tokens readable and identical.
    return TOKEN_PATTERN.findall(text.lower())
