"""gateway/cache.py: pure filesystem, no network -- hit/miss behavior of the
response cache KOMP-01's derivation call is wrapped in.
"""
from __future__ import annotations

import shutil

import pytest

from gateway.cache import CACHE_DIR, cached_call

NAMESPACE = "test_gateway_cache"


@pytest.fixture(autouse=True)
def _clean_namespace():
    shutil.rmtree(CACHE_DIR / NAMESPACE, ignore_errors=True)
    yield
    shutil.rmtree(CACHE_DIR / NAMESPACE, ignore_errors=True)


def test_cache_miss_calls_compute_and_stores_the_result() -> None:
    calls = []

    def compute():
        calls.append(1)
        return ["I.1.h"]

    result = cached_call(NAMESPACE, {"a": 1}, compute)
    assert result == ["I.1.h"]
    assert len(calls) == 1
    assert any((CACHE_DIR / NAMESPACE).glob("*.json"))


def test_cache_hit_never_calls_compute_again() -> None:
    calls = []

    def compute():
        calls.append(1)
        return ["I.1.h"]

    cached_call(NAMESPACE, {"a": 1}, compute)
    cached_call(NAMESPACE, {"a": 1}, compute)
    assert len(calls) == 1


def test_different_keys_do_not_collide() -> None:
    results = {
        "x": cached_call(NAMESPACE, {"a": 1}, lambda: "x"),
        "y": cached_call(NAMESPACE, {"a": 2}, lambda: "y"),
    }
    assert results == {"x": "x", "y": "y"}


def test_key_order_does_not_affect_the_cache_path() -> None:
    """The key is canonicalised (sort_keys=True) before hashing, so
    {"a": 1, "b": 2} and {"b": 2, "a": 1} must hit the same cache entry."""
    calls = []

    def compute():
        calls.append(1)
        return "same"

    cached_call(NAMESPACE, {"a": 1, "b": 2}, compute)
    cached_call(NAMESPACE, {"b": 2, "a": 1}, compute)
    assert len(calls) == 1
