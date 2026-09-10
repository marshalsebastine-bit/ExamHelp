"""Corpus and retrieval configuration.

Constants are read from here by every consumer.  Phase 1 declared these and then
never wired them in, so the chunkers ran on their own defaults (repo review 3).
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "corpus" / "raw"
CHUNK_DIR = ROOT / "corpus" / "chunks"
BUILD_DIR = ROOT / "build"
CACHE_DIR = BUILD_DIR / "cache"

SOURCE_MANIFEST = ROOT / "corpus" / "source_manifest.json"

# Chunk sizing.  Structure decides boundaries; this is only the ceiling at which
# an over-long structural unit gets split.
MAX_CHARS = 1800

# Retrieval.  No embedding model is loaded for the deterministic checks; these
# apply to Family C retrieval only (week 4).
EMBEDDING_MODEL = "BAAI/bge-m3"
TOP_K_DENSE = 12
TOP_K_BM25 = 12
TOP_K_HYBRID = 8
