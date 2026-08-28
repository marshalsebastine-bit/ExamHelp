from __future__ import annotations

import json
import pickle

import faiss
import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

from app.config import EMBEDDING_MODEL, INDEX_DIR, TOP_K_BM25, TOP_K_DENSE, TOP_K_HYBRID
from app.lexical import tokenize


def minmax(values):
    values = np.asarray(values, dtype=np.float32)
    if values.size == 0:
        return values
    lo, hi = values.min(), values.max()
    if hi - lo < 1e-8:
        return np.ones_like(values)
    return (values - lo) / (hi - lo)


def metadata_value(item: dict, key: str):
    """Read a top-level or dotted metadata field, e.g. ``structure.section``."""
    value: object = item
    for part in key.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def matches_filters(item: dict, filters: dict[str, str] | None) -> bool:
    """Match all metadata filters case-insensitively using exact field values."""
    if not filters:
        return True
    return all(
        str(metadata_value(item, key) or "").casefold() == str(expected).casefold()
        for key, expected in filters.items()
    )


def load_index():
    index = faiss.read_index(str(INDEX_DIR / "faiss.index"))
    metadata = json.loads((INDEX_DIR / "metadata.json").read_text(encoding="utf-8"))
    with open(INDEX_DIR / "bm25.pkl", "rb") as f:
        bm25 = pickle.load(f)
    model = SentenceTransformer(EMBEDDING_MODEL)
    return model, index, metadata, bm25


def search(query: str, filters: dict[str, str] | None = None, resources=None):
    """Run hybrid retrieval.

    ``resources`` lets batch callers load the embedding model and indexes once.
    """
    model, index, metadata, bm25 = resources or load_index()
    q = model.encode([query], normalize_embeddings=True)
    q = np.asarray(q, dtype=np.float32)
    # With a filter, inspect all candidates before taking the dense/BM25 top-k.
    # This avoids silently excluding a valid chunk merely because its global rank is low.
    dense_limit = index.ntotal if filters else TOP_K_DENSE
    dense_scores, dense_ids = index.search(q, min(dense_limit, index.ntotal))

    candidates = {}
    for idx, score in zip(dense_ids[0], dense_scores[0]):
        if idx >= 0 and matches_filters(metadata[int(idx)], filters):
            candidates.setdefault(int(idx), {})["dense"] = float(score)

    bm25_scores_all = np.asarray(bm25.get_scores(tokenize(query)), dtype=np.float32)
    bm25_ids = np.argsort(-bm25_scores_all)
    if filters:
        bm25_ids = [idx for idx in bm25_ids if matches_filters(metadata[int(idx)], filters)][:TOP_K_BM25]
    else:
        bm25_ids = bm25_ids[:TOP_K_BM25]
    for idx in bm25_ids:
        candidates.setdefault(int(idx), {})["bm25"] = float(bm25_scores_all[idx])

    dense_norm = minmax([v.get("dense", 0.0) for v in candidates.values()])
    bm25_norm = minmax([v.get("bm25", 0.0) for v in candidates.values()])

    for (idx, scores), d, b in zip(candidates.items(), dense_norm, bm25_norm):
        scores["hybrid"] = 0.65 * float(d) + 0.35 * float(b)

    ranked = sorted(candidates.items(), key=lambda x: x[1]["hybrid"], reverse=True)[:TOP_K_HYBRID]
    results = []
    for idx, scores in ranked:
        item = dict(metadata[idx])
        item["scores"] = scores
        results.append(item)
    return results
