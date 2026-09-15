"""FORM-07: operator extraction (deterministic) + Anforderungsbereich
comparison against a fake judge for the Erwartungshorizont side only -- no
network call in this test module (same posture as
tests/test_checks_komp_01.py's fake classifier).
"""
from __future__ import annotations

from checks.llm.form_07 import check_form_07
from schemas.aufgabe import Aufsichtsarbeit
from schemas.flag import Flag, NotChecked


def _aufgabe(teilaufgabe_text: str, **teilaufgabe_kwargs) -> Aufsichtsarbeit:
    teilaufgabe = {"text": teilaufgabe_text, **teilaufgabe_kwargs}
    return Aufsichtsarbeit.model_validate({"aufgaben": [{"teilaufgaben": [teilaufgabe]}]})


def _judge_returning(operator: str):
    def judge(erwartungshorizont_text, candidates, *, operator_explanations):
        return operator

    return judge


def test_fires_when_operators_share_no_anforderungsbereich() -> None:
    """'Zaehlen Sie auf' is Anforderungsbereich I; 'bewerten' is III -- no overlap."""
    aufgabe = _aufgabe(
        "Zaehlen Sie 3 Massnahmen auf.",
        erwartungshorizont={"erwartungspunkte": [{"text": "Bewertet die Massnahmen kritisch.", "punkte": 3}]},
    )
    results = check_form_07(aufgabe, judge=_judge_returning("bewerten"))
    assert len(results) == 1
    assert isinstance(results[0], Flag)
    assert results[0].rule_id == "FORM-07"
    assert results[0].anchor == "ag.1.ta.1"
    assert results[0].mechanism == "llm"
    assert "aufzählen" in results[0].finding
    assert "bewerten" in results[0].finding


def test_does_not_fire_when_operators_share_an_anforderungsbereich() -> None:
    aufgabe = _aufgabe(
        "Zaehlen Sie 3 Massnahmen auf.",
        erwartungshorizont={"erwartungspunkte": [{"text": "Nennt 3 Massnahmen.", "punkte": 3}]},
    )
    results = check_form_07(aufgabe, judge=_judge_returning("aufzählen"))
    assert results == []


def test_does_not_fire_when_judge_finds_no_matching_operator() -> None:
    """An empty verdict means the model could not identify a matching
    operator -- 'cannot compare' must not become a guessed flag."""
    aufgabe = _aufgabe(
        "Zaehlen Sie 3 Massnahmen auf.",
        erwartungshorizont={"erwartungspunkte": [{"text": "Etwas Unklares.", "punkte": 3}]},
    )
    results = check_form_07(aufgabe, judge=_judge_returning(""))
    assert results == []


def test_missing_teilaufgabe_text_is_not_checked_not_flagged() -> None:
    aufgabe = Aufsichtsarbeit.model_validate({"aufgaben": [{"teilaufgaben": [{}]}]})
    calls = []

    def judge(*args, **kwargs):
        calls.append(1)
        return ""

    results = check_form_07(aufgabe, judge=judge)
    assert len(results) == 1
    assert isinstance(results[0], NotChecked)
    assert "teilaufgabe.text" in results[0].missing
    assert not calls, "the judge must never be called without a Teilaufgabentext"


def test_missing_erwartungshorizont_is_not_checked_not_flagged() -> None:
    aufgabe = _aufgabe("Zaehlen Sie 3 Massnahmen auf.")
    calls = []

    def judge(*args, **kwargs):
        calls.append(1)
        return ""

    results = check_form_07(aufgabe, judge=judge)
    assert len(results) == 1
    assert isinstance(results[0], NotChecked)
    assert "teilaufgabe.erwartungshorizont" in results[0].missing
    assert not calls, "the judge must never be called without an Erwartungshorizont"


def test_no_recognisable_operator_is_not_checked_not_flagged() -> None:
    """A Teilaufgabe with no catalogue operator at all has nothing to
    compare against -- FORM-03's stance, not a FORM-07 guess."""
    aufgabe = _aufgabe(
        "Es sollte eine Beschreibung erfolgen.",
        erwartungshorizont={"erwartungspunkte": [{"text": "Nennt 3 Massnahmen.", "punkte": 3}]},
    )
    calls = []

    def judge(*args, **kwargs):
        calls.append(1)
        return ""

    results = check_form_07(aufgabe, judge=judge)
    assert len(results) == 1
    assert isinstance(results[0], NotChecked)
    assert not calls, "the judge must never be called when no Teilaufgabe operator was found"


def test_judge_receives_erwartungshorizont_text_and_the_full_operator_candidate_list() -> None:
    aufgabe = _aufgabe(
        "Zaehlen Sie 3 Massnahmen auf.",
        erwartungshorizont={"erwartungspunkte": [{"text": "Nennt 3 Massnahmen.", "punkte": 3}]},
    )
    seen = {}

    def judge(erwartungshorizont_text, candidates, *, operator_explanations):
        seen["erwartungshorizont_text"] = erwartungshorizont_text
        seen["candidates"] = candidates
        seen["operator_explanations"] = operator_explanations
        return ""

    check_form_07(aufgabe, judge=judge)
    assert "Nennt 3 Massnahmen." in seen["erwartungshorizont_text"]
    assert "aufzählen" in seen["candidates"]
    assert "bewerten" in seen["candidates"]
    assert seen["operator_explanations"]["nennen"]
