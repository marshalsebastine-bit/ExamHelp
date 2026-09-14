"""Proves the provider abstraction actually holds: gateway/model_gateway.py's
task-level functions never need to change to support a new backend, and
never talk to a specific provider's SDK directly.
"""
from __future__ import annotations

import shutil

import pytest

from gateway import model_gateway
from gateway.backends.mistral import MistralBackend
from gateway.base import ModelBackend
from gateway.cache import CACHE_DIR
from gateway.model_gateway import classify_kompetenz, get_backend

NAMESPACE = "kompetenz"


@pytest.fixture(autouse=True)
def _isolate_registry_and_cache():
    """Never let a fake backend registered by one test leak into another,
    and never let a cached response from one test's fake short-circuit
    another test's assertion."""
    original_backends = dict(model_gateway.BACKENDS)
    yield
    model_gateway.BACKENDS.clear()
    model_gateway.BACKENDS.update(original_backends)
    shutil.rmtree(CACHE_DIR / NAMESPACE, ignore_errors=True)


class FakeBackend:
    """A second, throwaway provider -- proves BACKENDS is a real registry,
    not a hardcoded reference to Mistral."""

    model = "fake-1"

    def __init__(self, response: str = '{"codes": []}') -> None:
        self.response = response
        self.calls: list[str] = []

    def complete(self, prompt: str, *, json_mode: bool = False, temperature: float = 0.0) -> str:
        self.calls.append(prompt)
        return self.response


def test_default_provider_is_mistral() -> None:
    assert isinstance(get_backend(), MistralBackend)


def test_get_backend_honours_the_model_provider_env_var(monkeypatch) -> None:
    model_gateway.BACKENDS["fake"] = FakeBackend
    monkeypatch.setenv("MODEL_PROVIDER", "fake")
    assert isinstance(get_backend(), FakeBackend)


def test_get_backend_honours_an_explicit_provider_argument() -> None:
    model_gateway.BACKENDS["fake"] = FakeBackend
    assert isinstance(get_backend("fake"), FakeBackend)


def test_unknown_provider_raises_a_clear_error() -> None:
    with pytest.raises(ValueError, match="unknown MODEL_PROVIDER"):
        get_backend("does-not-exist")


def test_every_registered_backend_satisfies_the_protocol() -> None:
    for backend_cls in model_gateway.BACKENDS.values():
        assert isinstance(backend_cls(), ModelBackend)


def test_classify_kompetenz_works_against_a_swapped_in_backend(monkeypatch) -> None:
    """The point of the abstraction: this call site is identical regardless
    of which provider answers it."""
    fake = FakeBackend('{"codes": ["I.1.h"]}')
    model_gateway.BACKENDS["fake"] = lambda: fake
    monkeypatch.setenv("MODEL_PROVIDER", "fake")

    result = classify_kompetenz("irgendein Text", ["I.1.h", "I.2.a"], kompetenz_text={})

    assert result == ["I.1.h"]
    assert len(fake.calls) == 1


def test_classify_kompetenz_filters_a_fake_backends_off_candidate_output(monkeypatch) -> None:
    fake = FakeBackend('{"codes": ["I.1.h", "Z.9.z"]}')
    model_gateway.BACKENDS["fake"] = lambda: fake
    monkeypatch.setenv("MODEL_PROVIDER", "fake")

    result = classify_kompetenz("x", ["I.1.h"], kompetenz_text={})

    assert result == ["I.1.h"]


def test_classify_kompetenz_caches_so_a_second_call_does_not_hit_the_backend_again(monkeypatch) -> None:
    fake = FakeBackend('{"codes": ["I.1.h"]}')
    model_gateway.BACKENDS["fake"] = lambda: fake
    monkeypatch.setenv("MODEL_PROVIDER", "fake")

    classify_kompetenz("x", ["I.1.h"], kompetenz_text={})
    classify_kompetenz("x", ["I.1.h"], kompetenz_text={})

    assert len(fake.calls) == 1


def test_classify_kompetenz_includes_fallsituation_text_in_the_prompt(monkeypatch) -> None:
    """The Fallsituation the Teilaufgabe belongs to is context the model
    needs, not just the bare Teilaufgabe text -- it must actually reach the
    backend's prompt."""
    fake = FakeBackend('{"codes": []}')
    model_gateway.BACKENDS["fake"] = lambda: fake
    monkeypatch.setenv("MODEL_PROVIDER", "fake")

    classify_kompetenz(
        "x", ["I.1.h"], kompetenz_text={}, fallsituation_text="Frau Ostermann ist 82 Jahre alt."
    )

    assert "Frau Ostermann ist 82 Jahre alt." in fake.calls[0]


def test_classify_kompetenz_omits_the_fallsituation_block_when_not_given(monkeypatch) -> None:
    """A draft without a Fallsituation yet must still get the original,
    text-only prompt -- no stray empty section."""
    fake = FakeBackend('{"codes": []}')
    model_gateway.BACKENDS["fake"] = lambda: fake
    monkeypatch.setenv("MODEL_PROVIDER", "fake")

    classify_kompetenz("x", ["I.1.h"], kompetenz_text={})

    assert "Fallsituation" not in fake.calls[0]


def test_classify_kompetenz_does_not_cache_across_different_fallsituation_text(monkeypatch) -> None:
    """Two Teilaufgaben with the same text and candidates but different
    Fallsituationen must not share a cache entry -- the Fallsituation is
    part of what the classifier saw."""
    fake = FakeBackend('{"codes": ["I.1.h"]}')
    model_gateway.BACKENDS["fake"] = lambda: fake
    monkeypatch.setenv("MODEL_PROVIDER", "fake")

    classify_kompetenz("x", ["I.1.h"], kompetenz_text={}, fallsituation_text="Fall A")
    classify_kompetenz("x", ["I.1.h"], kompetenz_text={}, fallsituation_text="Fall B")

    assert len(fake.calls) == 2
