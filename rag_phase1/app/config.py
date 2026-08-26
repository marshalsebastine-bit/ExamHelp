from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
INDEX_DIR = ROOT / "data" / "index"

EMBEDDING_MODEL = "BAAI/bge-m3"
TARGET_CHARS = 1800
MAX_CHARS = 2600
OVERLAP_CHARS = 250
TOP_K_DENSE = 12
TOP_K_BM25 = 12
TOP_K_HYBRID = 8

for p in (RAW_DIR, PROCESSED_DIR, INDEX_DIR):
    p.mkdir(parents=True, exist_ok=True)
