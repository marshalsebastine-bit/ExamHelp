"""A simple file-based response cache for model-gateway calls.

Not the tech doc's full response cache (that also keys on item_version and
is meant to sit in front of every rule, not just this one) -- just enough to
avoid re-paying for an identical call across repeated dev/test runs. Each
entry is one JSON file, so it's easy to inspect or delete by hand.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, TypeVar

CACHE_DIR = Path(__file__).resolve().parents[1] / "build" / "cache"

T = TypeVar("T")


def _cache_path(namespace: str, key: dict[str, Any]) -> Path:
    canonical = json.dumps(key, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return CACHE_DIR / namespace / f"{digest}.json"


def cached_call(namespace: str, key: dict[str, Any], compute: Callable[[], T]) -> T:
    """Return the cached result for ``key`` under ``namespace``, computing
    and storing it via ``compute`` on a miss.

    ``key`` must be JSON-serialisable and should include everything that
    could change the answer (input text, candidate set, model name) -- it is
    hashed as-is, so anything left out risks a stale hit.
    """
    path = _cache_path(namespace, key)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))["result"]

    result = compute()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"key": key, "result": result}, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
