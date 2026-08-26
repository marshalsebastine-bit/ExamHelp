from __future__ import annotations

import json
import os
import pickle
import sys
from pathlib import Path

import faiss
import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import EMBEDDING_MODEL, INDEX_DIR, PROCESSED_DIR, RAW_DIR
from app.chunking import classify_source
from app.ingest import build_chunks
from app.lexical import tokenize


def main():
    paths = sorted(
        p for p in RAW_DIR.iterdir()
        if p.is_file()
        and p.name.casefold() != "readme.md"
        and p.suffix.lower() in {".html", ".htm", ".pdf", ".txt", ".md"}
    )
    if not paths:
        raise SystemExit("No source files found. Put .html/.pdf/.txt/.md files in data/raw/.")

    # When the official HTML and a legacy PDF share a legal document name, use the
    # HTML source only.  It has reliable provision boundaries and clean source text.
    html_legal_stems = {
        path.stem.casefold() for path in paths
        if path.suffix.lower() in {".html", ".htm"} and classify_source(path) == "legal"
    }
    paths = [
        path for path in paths
        if not (classify_source(path) == "legal" and path.suffix.lower() == ".pdf" and path.stem.casefold() in html_legal_stems)
    ]
    chunks = build_chunks(paths)
    texts = [c["text"] for c in chunks]
    print(f"Loaded {len(paths)} sources and created {len(texts)} chunks.")
    model = SentenceTransformer(EMBEDDING_MODEL)
    embeddings = model.encode(texts, batch_size=16, show_progress_bar=True, normalize_embeddings=True)
    embeddings = np.asarray(embeddings, dtype=np.float32)

    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(embeddings)
    bm25 = BM25Okapi([tokenize(text) for text in texts])
    # Write every artefact to a temporary sibling first.  A failed/aborted embedding
    # run must never leave metadata and indexes from different corpus versions mixed.
    faiss_tmp = INDEX_DIR / "faiss.index.tmp"
    metadata_tmp = INDEX_DIR / "metadata.json.tmp"
    bm25_tmp = INDEX_DIR / "bm25.pkl.tmp"
    chunks_tmp = PROCESSED_DIR / "chunks.jsonl.tmp"
    faiss.write_index(index, str(faiss_tmp))
    metadata_tmp.write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")
    with open(bm25_tmp, "wb") as f:
        pickle.dump(bm25, f)
    chunks_tmp.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in chunks), encoding="utf-8")

    for temporary, target in (
        (faiss_tmp, INDEX_DIR / "faiss.index"),
        (metadata_tmp, INDEX_DIR / "metadata.json"),
        (bm25_tmp, INDEX_DIR / "bm25.pkl"),
        (chunks_tmp, PROCESSED_DIR / "chunks.jsonl"),
    ):
        os.replace(temporary, target)

    print("Index built successfully.")


if __name__ == "__main__":
    main()
