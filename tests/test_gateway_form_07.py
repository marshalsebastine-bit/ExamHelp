"""gateway/model_gateway.py::judge_form_07 -- prompt building, response
parsing, and caching, all against a fake backend (same pattern as
tests/test_gateway_model_registry.py). No network call here.
"""
from __future__ import annotations

import shutil

import pytest

from gateway import model_gateway
from gateway.cache import CACHE_DIR
from gateway.model_gateway import judge_form_07

NAMESPACE = "form_07"
OPERATORS = {"aufzählen": ["I"], "begründen": ["II"], "bewerten": ["III"]}
RULE_TEXT = "Der Erwartungshorizont muss die Leistung abbilden, die die Teilaufgabe verlangt."


@pytest.fixture(autouse=True)
def _isolate_registry_and_cache():
    original_backends = dict(model_gateway.BACKENDS)
    yield
    model_gateway.BACKENDS.clear()
    model_gateway.BACKENDS.update(original_backends)
    shutil.rmtree(CACHE_DIR / NAMESPACE, ignore_errors=True)


class FakeBackend:
    model = "fake-1"

    def __init__(self, response: str = '{"beleg_zitat": "", "mismatch": false, "begruendung": ""}') -> None:
        self.response = response
        self.calls: list[str] = []

    def complete(self, prompt: str, *, json_mode: bool = False, temperature: float = 0.0) -> str:
        self.calls.append(prompt)
        return self.response


def _use_fake(response: str) -> FakeBackend:
    backend = FakeBackend(response)
    model_gateway.BACKENDS["fake"] = lambda: backend
    return backend


def _judge(**overrides):
    kwargs = dict(
        teilaufgabe_text="Zählen Sie 3 Massnahmen auf.",
        teilaufgabe_operatoren=["aufzählen"],
        erwartungshorizont_text="Begründet die Reihenfolge.",
        operators=OPERATORS,
        rule_text=RULE_TEXT,
    )
    kwargs.update(overrides)
    return judge_form_07(kwargs.pop("teilaufgabe_text"), kwargs.pop("teilaufgabe_operatoren"), kwargs.pop("erwartungshorizont_text"), **kwargs)


def test_parses_a_true_mismatch_response(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "fake")
    _use_fake('{"beleg_zitat": "Begründet die Reihenfolge.", "mismatch": true, "begruendung": "Aufzaehlung verlangt, Begruendung bepunktet."}')
    result = _judge()
    assert result == {
        "mismatch": True,
        "beleg_zitat": "Begründet die Reihenfolge.",
        "begruendung": "Aufzaehlung verlangt, Begruendung bepunktet.",
    }


def test_parses_a_false_mismatch_response(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "fake")
    _use_fake('{"beleg_zitat": "", "mismatch": false, "begruendung": ""}')
    result = _judge()
    assert result == {"mismatch": False, "beleg_zitat": "", "begruendung": ""}


def test_malformed_json_degrades_to_no_mismatch(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "fake")
    _use_fake("not json at all")
    result = _judge()
    assert result == {"mismatch": False, "beleg_zitat": "", "begruendung": ""}


def test_prompt_includes_teilaufgabe_text_and_erwartungshorizont_text_and_rule_text(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "fake")
    backend = _use_fake('{"beleg_zitat": "", "mismatch": false, "begruendung": ""}')
    _judge()
    assert len(backend.calls) == 1
    prompt = backend.calls[0]
    assert "Zählen Sie 3 Massnahmen auf." in prompt
    assert "Begründet die Reihenfolge." in prompt
    assert RULE_TEXT in prompt
    assert "aufzählen" in prompt
    assert "keinen Prüfling" in prompt


def test_prompt_keeps_the_three_ingredients_that_removed_the_false_positives(monkeypatch) -> None:
    """These three were measured to take FORM-07 from 23 false positives to 0
    on 25 labelled-clean Teilaufgaben, same model (see
    docs/week3-form07-quality-spot-check.md 3). Losing any of them from the
    prompt would be a silent, expensive regression -- so pin them."""
    monkeypatch.setenv("MODEL_PROVIDER", "fake")
    backend = _use_fake('{"beleg_zitat": "", "mismatch": false, "begruendung": ""}')
    _judge()
    prompt = backend.calls[0]
    assert "Beispiel A" in prompt and "Beispiel B" in prompt, "both a mismatch and a match example must be shown"
    assert "NIEMALS ein Hinweis" in prompt, "must state that terse note form is not evidence of a mismatch"
    assert "Im Zweifel mismatch=false" in prompt, "must state the conservative default"
    assert "beleg_zitat" in prompt, "must require a literal quote"


def test_result_is_cached_on_all_text_inputs(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "fake")
    backend = _use_fake('{"beleg_zitat": "z", "mismatch": true, "begruendung": "x"}')
    _judge()
    _judge()
    assert len(backend.calls) == 1, "identical inputs must hit the cache, not call the backend twice"


def test_different_erwartungshorizont_text_is_not_cache_confused(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "fake")
    backend = _use_fake('{"beleg_zitat": "z", "mismatch": true, "begruendung": "x"}')
    _judge()
    _judge(erwartungshorizont_text="Etwas ganz anderes.")
    assert len(backend.calls) == 2, "a changed erwartungshorizont_text must not serve a stale cached answer"
