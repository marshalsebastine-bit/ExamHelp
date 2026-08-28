from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.retrieval import search


def parse_filters(values: list[str]) -> dict[str, str]:
    filters = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"Invalid filter {value!r}; use key=value.")
        key, expected = value.split("=", 1)
        if not key or not expected:
            raise ValueError(f"Invalid filter {value!r}; use key=value.")
        filters[key] = expected
    return filters


parser = argparse.ArgumentParser(description="Search the local hybrid RAG index.")
parser.add_argument("query", nargs="+", help="German question or search phrase.")
parser.add_argument("--filter", action="append", default=[], metavar="KEY=VALUE", help="Restrict results by metadata; repeat as needed.")
args = parser.parse_args()
query = " ".join(args.query)
filters = parse_filters(args.filter)

if filters:
    print("filters:", filters)

for i, result in enumerate(search(query, filters=filters), start=1):
    print(f"\n[{i}] {result['source_file']} | {result['source_locator']} | chunk={result['chunk_index']}")
    print("type:", result["document_type"], "/", result.get("content_type", "text"))
    if result.get("source_url"):
        print("source:", result["source_url"], "| retrieved:", result.get("retrieved_at"))
    print("scores:", {k: round(v, 4) for k, v in result["scores"].items()})
    print(result["text"][:1200])
