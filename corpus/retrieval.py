"""Hybrid retrieval over the chunked corpus.

FAISS is gone: at this corpus size (hundreds of chunks, not tens of thousands)
brute-force cosine over a numpy array is *exact*, instant, and one dependency
lighter.  Reintroduce an approximate index past ~50k chunks (repo review 3).
"""
from __future__ import annotations

import json
import pickle

import numpy as np
from rank_bm25 import BM25Okapi

from corpus.config import CHUNK_DIR, TOP_K_BM25, TOP_K_DENSE, TOP_K_HYBRID
from corpus.lexical import tokenize


def minmax(values):
    """Normalise scores to [0, 1] within one candidate set.

    Note these are *per-query* normalisations: comparable within a query,
    meaningless across queries.  Never threshold on them and never present them
    as a confidence (repo review 4.5).
    """
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


def cosine_scores(query_vector: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Exact cosine similarity against every chunk.

    Both sides are expected L2-normalised, so the dot product *is* the cosine.
    """
    return matrix @ query_vector.reshape(-1)


def load_index():
    metadata = json.loads((CHUNK_DIR / "metadata.json").read_text(encoding="utf-8"))
    embeddings = np.load(CHUNK_DIR / "embeddings.npy")
    with open(CHUNK_DIR / "bm25.pkl", "rb") as handle:
        bm25 = pickle.load(handle)
    return metadata, embeddings, bm25


def search(query: str, filters: dict[str, str] | None = None, resources=None):
    """Run hybrid dense + BM25 retrieval.

    ``resources`` lets batch callers load the embedding model and index once.
    """
    from sentence_transformers import SentenceTransformer

    from corpus.config import EMBEDDING_MODEL

    if resources is None:
        metadata, embeddings, bm25 = load_index()
        model = SentenceTransformer(EMBEDDING_MODEL)
    else:
        model, metadata, embeddings, bm25 = resources

    query_vector = np.asarray(
        model.encode([query], normalize_embeddings=True), dtype=np.float32
    )
    dense_all = cosine_scores(query_vector, embeddings)
    # With a filter, inspect all candidates before taking the top-k, so a valid
    # chunk is not silently excluded merely because its global rank is low.
    order = np.argsort(-dense_all)
    if filters:
        dense_ids = [i for i in order if matches_filters(metadata[int(i)], filters)][:TOP_K_DENSE]
    else:
        dense_ids = order[:TOP_K_DENSE]

    candidates: dict[int, dict] = {}
    for idx in dense_ids:
        candidates.setdefault(int(idx), {})["dense"] = float(dense_all[int(idx)])

    bm25_all = np.asarray(bm25.get_scores(tokenize(query)), dtype=np.float32)
    bm25_order = np.argsort(-bm25_all)
    if filters:
        bm25_ids = [i for i in bm25_order if matches_filters(metadata[int(i)], filters)][:TOP_K_BM25]
    else:
        bm25_ids = bm25_order[:TOP_K_BM25]
    for idx in bm25_ids:
        candidates.setdefault(int(idx), {})["bm25"] = float(bm25_all[int(idx)])

    dense_norm = minmax([v.get("dense", 0.0) for v in candidates.values()])
    bm25_norm = minmax([v.get("bm25", 0.0) for v in candidates.values()])
    for (_, scores), dense, lexical in zip(candidates.items(), dense_norm, bm25_norm):
        scores["hybrid"] = 0.65 * float(dense) + 0.35 * float(lexical)

    ranked = sorted(candidates.items(), key=lambda kv: kv[1]["hybrid"], reverse=True)[:TOP_K_HYBRID]
    results = []
    for idx, scores in ranked:
        item = dict(metadata[idx])
        item["scores"] = scores
        results.append(item)
    return results
