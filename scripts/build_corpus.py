"""Build the chunked corpus from the public sources in the manifest.

Run:  python scripts/build_corpus.py [--embed]

Chunking is structural and needs no model, so the default run is fast and
dependency-light.  ``--embed`` additionally builds the dense index, which is
only needed for Family C retrieval (week 4).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from corpus.config import CHUNK_DIR, MAX_CHARS, RAW_DIR, SOURCE_MANIFEST
from corpus.ingest.chunking import SourceDocument, chunk_document, classify_source
from corpus.ingest.legal import legal_source_metadata, read_legal_html
from corpus.lexical import tokenize


def document_id(path: Path) -> str:
    return hashlib.sha1(path.name.encode("utf-8")).hexdigest()[:12]


def load_manifest() -> list[dict]:
    manifest = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    return [s for s in manifest["sources"] if s.get("in_retrieval_corpus") and s.get("source_file")]


def build() -> list[dict]:
    chunks: list[dict] = []
    for source in load_manifest():
        path = RAW_DIR / source["source_file"]
        if not path.exists():
            print(f"  SKIP {source['id']}: {path.name} not present")
            continue
        document_type = classify_source(path)
        if document_type != "legal":
            # The Lehrplan is ingested by the taxonomy extractor, not here: its
            # useful structure is CE and Situationsmerkmale, which chunk on
            # different boundaries than a legal provision (tech doc 3.2.1).
            print(f"  SKIP {source['id']}: handled by scripts/extract_lehrplan.py")
            continue

        provisions = read_legal_html(path)
        metadata = legal_source_metadata(path)
        metadata["authority"] = source["authority"]
        metadata["source_url"] = source.get("url")
        document = SourceDocument(
            document_id=document_id(path),
            path=path,
            title=str(metadata.get("official_title") or path.stem),
            document_type=document_type,
            provisions=provisions,
            metadata=metadata,
        )
        produced = chunk_document(document, max_chars=MAX_CHARS)
        chunks.extend(produced)
        anlage_chunks = sum(1 for c in produced if c.get("content_type") == "kompetenz")
        print(
            f"  {source['id']:16s} provisions={len(provisions):3d} "
            f"chunks={len(produced):4d} kompetenz_chunks={anlage_chunks:3d}"
        )
    return chunks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--embed", action="store_true", help="also build the dense index")
    args = parser.parse_args()

    CHUNK_DIR.mkdir(parents=True, exist_ok=True)
    print("Building corpus:")
    chunks = build()
    if not chunks:
        print("No chunks produced.")
        return 1

    (CHUNK_DIR / "metadata.json").write_text(
        json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with open(CHUNK_DIR / "bm25.pkl", "wb") as handle:
        from rank_bm25 import BM25Okapi

        pickle.dump(BM25Okapi([tokenize(c["text"]) for c in chunks]), handle)

    if args.embed:
        import numpy as np
        from sentence_transformers import SentenceTransformer

        from corpus.config import EMBEDDING_MODEL

        model = SentenceTransformer(EMBEDDING_MODEL)
        vectors = model.encode(
            [c["text"] for c in chunks], normalize_embeddings=True, show_progress_bar=True
        )
        np.save(CHUNK_DIR / "embeddings.npy", np.asarray(vectors, dtype="float32"))
        print(f"  embedded {len(chunks)} chunks with {EMBEDDING_MODEL}")

    print(f"\nWrote {len(chunks)} chunks to {CHUNK_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
