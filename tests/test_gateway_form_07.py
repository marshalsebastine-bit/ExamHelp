"""gateway/model_gateway.py::judge_form_07 -- prompt building, response
parsing, candidate filtering, and caching, all against a fake backend (same
pattern as tests/test_gateway_model_registry.py). No network call here.
"""
from __future__ import annotations

import shutil

import pytest

from gateway import model_gateway
from gateway.cache import CACHE_DIR
from gateway.model_gateway import judge_form_07

NAMESPACE = "form_07"
CANDIDATES = ["aufzählen", "begründen", "bewerten"]
EXPLANATIONS = {"aufzählen": "...", "begründen": "...", "bewerten": "..."}


@pytest.fixture(autouse=True)
def _isolate_registry_and_cache():
    original_backends = dict(model_gateway.BACKENDS)
    yield
    model_gateway.BACKENDS.clear()
    model_gateway.BACKENDS.update(original_backends)
    shutil.rmtree(CACHE_DIR / NAMESPACE, ignore_errors=True)


class FakeBackend:
    model = "fake-1"

    def __init__(self, response: str = '{"erwartungshorizont_operator": ""}') -> None:
        self.response = response
        self.calls: list[str] = []

    def complete(self, prompt: str, *, json_mode: bool = False, temperature: float = 0.0) -> str:
        self.calls.append(prompt)
        return self.response


def _use_fake(response: str) -> FakeBackend:
    backend = FakeBackend(response)
    model_gateway.BACKENDS["fake"] = lambda: backend
    return backend


def test_returns_the_chosen_operator_when_it_is_in_the_candidate_list(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "fake")
    _use_fake('{"erwartungshorizont_operator": "bewerten"}')
    result = judge_form_07("Bewertet die Massnahmen kritisch.", CANDIDATES, operator_explanations=EXPLANATIONS)
    assert result == "bewerten"


def test_filters_out_an_operator_not_in_the_candidate_list() -> None:
    """Defense in depth: even though the prompt already constrains the
    model to the candidate list, a hallucinated operator must not pass
    through -- same posture as classify_kompetenz filtering codes."""
    model_gateway.BACKENDS["fake"] = lambda: FakeBackend('{"erwartungshorizont_operator": "erfinden"}')
    result = judge_form_07(
        "x", CANDIDATES, operator_explanations=EXPLANATIONS, provider="fake"
    )
    assert result == ""


def test_malformed_json_degrades_to_empty_string(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "fake")
    _use_fake("not json at all")
    result = judge_form_07("x", CANDIDATES, operator_explanations=EXPLANATIONS)
    assert result == ""


def test_no_candidates_returns_empty_without_calling_the_backend(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "fake")
    backend = _use_fake('{"erwartungshorizont_operator": "bewerten"}')
    result = judge_form_07("x", [], operator_explanations=EXPLANATIONS)
    assert result == ""
    assert not backend.calls


def test_result_is_cached_on_text_and_candidates(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "fake")
    backend = _use_fake('{"erwartungshorizont_operator": "bewerten"}')
    judge_form_07("Erwartungshorizont A", CANDIDATES, operator_explanations=EXPLANATIONS)
    judge_form_07("Erwartungshorizont A", CANDIDATES, operator_explanations=EXPLANATIONS)
    assert len(backend.calls) == 1, "identical inputs must hit the cache, not call the backend twice"


def test_different_text_is_not_cache_confused(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "fake")
    backend = _use_fake('{"erwartungshorizont_operator": "bewerten"}')
    judge_form_07("Erwartungshorizont A", CANDIDATES, operator_explanations=EXPLANATIONS)
    judge_form_07("Erwartungshorizont B", CANDIDATES, operator_explanations=EXPLANATIONS)
    assert len(backend.calls) == 2, "a changed erwartungshorizont_text must not serve a stale cached answer"
