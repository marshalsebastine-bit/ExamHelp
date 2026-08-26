"""Run the manually labelled retrieval checks in evaluation/queries.jsonl."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.retrieval import load_index, search

DEFAULT_QUERIES = ROOT / "evaluation" / "queries.jsonl"


def normalise(value: object) -> str:
    return " ".join(str(value or "").casefold().split())


def source_matches(result: dict, expected_sources: list[str]) -> bool:
    source = normalise(result.get("source_file"))
    return any(normalise(expected) in source for expected in expected_sources)


def metadata_matches(result: dict, case: dict) -> bool:
    checks = {
        "expected_content_type": result.get("content_type"),
        "expected_operator": result.get("operator"),
        "expected_source_locator": result.get("source_locator"),
    }
    section = result.get("structure", {}).get("section")
    if "expected_section" in case:
        checks["expected_section"] = section
    return all(
        expected_key not in case or normalise(case[expected_key]) in normalise(actual)
        for expected_key, actual in checks.items()
    )


def expected_rank(results: list[dict], case: dict) -> int | None:
    for rank, result in enumerate(results, start=1):
        if source_matches(result, case["expected_sources"]) and metadata_matches(result, case):
            return rank
    return None


def load_cases(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate hybrid retrieval against labelled queries.")
    parser.add_argument("--top-k", type=int, default=3, help="Rank cutoff for a passing result (default: 3).")
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES, help="JSONL evaluation set.")
    args = parser.parse_args()
    if args.top_k < 1:
        raise SystemExit("--top-k must be at least 1")

    cases = load_cases(args.queries)
    resources = load_index()
    passed = 0
    print(f"Evaluating {len(cases)} queries; pass threshold: top {args.top_k}.\n")
    for number, case in enumerate(cases, start=1):
        results = search(case["query"], resources=resources)
        rank = expected_rank(results, case)
        is_pass = rank is not None and rank <= args.top_k
        passed += is_pass
        status = "PASS" if is_pass else "FAIL"
        observed = f"rank {rank}" if rank is not None else "not in retrieved results"
        print(f"[{status}] {number}. {case['query']}\n  Expected: {', '.join(case['expected_sources'])}; {observed}")

    print(f"\nResult: {passed}/{len(cases)} passed within top {args.top_k}.")
    raise SystemExit(0 if passed == len(cases) else 1)


if __name__ == "__main__":
    main()
