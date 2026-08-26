from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.retrieval import search

query = " ".join(sys.argv[1:]).strip()
if not query:
    raise SystemExit('Usage: python scripts/query.py "Ihre deutsche Prüfungsfrage ..."')

for i, result in enumerate(search(query), start=1):
    print(f"\n[{i}] {result['source_file']} | {result['source_locator']} | chunk={result['chunk_index']}")
    print("type:", result["document_type"], "/", result.get("content_type", "text"))
    print("scores:", {k: round(v, 4) for k, v in result["scores"].items()})
    print(result["text"][:1200])
