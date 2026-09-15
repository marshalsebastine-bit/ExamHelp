"""FORM-07: operator extraction (deterministic) + dispatch on the judge's
free-form mismatch verdict -- no network call in this test module (same
posture as tests/test_checks_komp_01.py's fake classifier).
"""
from __future__ import annotations

from checks.llm.form_07 import check_form_07
from schemas.aufgabe import Aufsichtsarbeit
from schemas.flag import Flag, NotChecked


def _aufgabe(teilaufgabe_text: str, **teilaufgabe_kwargs) -> Aufsichtsarbeit:
    teilaufgabe = {"text": teilaufgabe_text, **teilaufgabe_kwargs}
    return Aufsichtsarbeit.model_validate({"aufgaben": [{"teilaufgaben": [teilaufgabe]}]})


def _judge_returning(mismatch: bool, begruendung: str = "", beleg_zitat: str = "Begruendet die Reihenfolge."):
    def judge(teilaufgabe_text, teilaufgabe_operatoren, erwartungshorizont_text, *, operators, rule_text):
        return {"mismatch": mismatch, "beleg_zitat": beleg_zitat, "begruendung": begruendung}

    return judge


def test_fires_when_judge_reports_a_mismatch() -> None:
    aufgabe = _aufgabe(
        "Zaehlen Sie 3 Massnahmen auf.",
        erwartungshorizont={"erwartungspunkte": [{"text": "Begruendet die Reihenfolge.", "punkte": 3}]},
    )
    results = check_form_07(aufgabe, judge=_judge_returning(True, "Aufzaehlung verlangt, Begruendung bepunktet."))
    assert len(results) == 1
    assert isinstance(results[0], Flag)
    assert results[0].rule_id == "FORM-07"
    assert results[0].anchor == "ag.1.ta.1"
    assert results[0].mechanism == "llm"
    assert "aufzählen" in results[0].finding
    assert "Aufzaehlung verlangt" in results[0].finding


def test_does_not_fire_when_judge_reports_no_mismatch() -> None:
    aufgabe = _aufgabe(
        "Zaehlen Sie 3 Massnahmen auf.",
        erwartungshorizont={"erwartungspunkte": [{"text": "Nennt 3 Massnahmen.", "punkte": 3}]},
    )
    results = check_form_07(aufgabe, judge=_judge_returning(False))
    assert results == []


def test_missing_teilaufgabe_text_is_not_checked_not_flagged() -> None:
    aufgabe = Aufsichtsarbeit.model_validate({"aufgaben": [{"teilaufgaben": [{}]}]})
    calls = []

    def judge(*args, **kwargs):
        calls.append(1)
        return {"mismatch": False, "beleg_zitat": "", "begruendung": ""}

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
        return {"mismatch": False, "beleg_zitat": "", "begruendung": ""}

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
        return {"mismatch": False, "beleg_zitat": "", "begruendung": ""}

    results = check_form_07(aufgabe, judge=judge)
    assert len(results) == 1
    assert isinstance(results[0], NotChecked)
    assert not calls, "the judge must never be called when no Teilaufgabe operator was found"


def test_judge_receives_full_context() -> None:
    aufgabe = _aufgabe(
        "Zaehlen Sie 3 Massnahmen auf.",
        erwartungshorizont={"erwartungspunkte": [{"text": "Nennt 3 Massnahmen.", "punkte": 3}]},
    )
    seen = {}

    def judge(teilaufgabe_text, teilaufgabe_operatoren, erwartungshorizont_text, *, operators, rule_text):
        seen["teilaufgabe_text"] = teilaufgabe_text
        seen["teilaufgabe_operatoren"] = teilaufgabe_operatoren
        seen["erwartungshorizont_text"] = erwartungshorizont_text
        seen["operators"] = operators
        seen["rule_text"] = rule_text
        return {"mismatch": False, "beleg_zitat": "", "begruendung": ""}

    check_form_07(aufgabe, judge=judge)
    assert seen["teilaufgabe_text"] == "Zaehlen Sie 3 Massnahmen auf."
    assert seen["teilaufgabe_operatoren"] == ["aufzählen"]
    assert "Nennt 3 Massnahmen." in seen["erwartungshorizont_text"]
    assert "aufzählen" in seen["operators"]
    assert seen["rule_text"]


def test_finding_falls_back_when_begruendung_is_empty() -> None:
    aufgabe = _aufgabe(
        "Zaehlen Sie 3 Massnahmen auf.",
        erwartungshorizont={"erwartungspunkte": [{"text": "Begruendet die Reihenfolge.", "punkte": 3}]},
    )
    results = check_form_07(aufgabe, judge=_judge_returning(True, ""))
    assert len(results) == 1
    assert results[0].finding


def test_mismatch_without_a_quote_does_not_produce_a_flag() -> None:
    """No quote, no flag -- the project's "no flag without evidence" rule
    applied to the model's own reasoning step, enforced here rather than
    trusted from the prompt (docs/week3-form07-quality-spot-check.md 3)."""
    aufgabe = _aufgabe(
        "Zaehlen Sie 3 Massnahmen auf.",
        erwartungshorizont={"erwartungspunkte": [{"text": "Begruendet die Reihenfolge.", "punkte": 3}]},
    )
    results = check_form_07(aufgabe, judge=_judge_returning(True, "Irgendein Widerspruch.", beleg_zitat=""))
    assert results == []


def test_flag_quotes_the_offending_erwartungspunkt() -> None:
    aufgabe = _aufgabe(
        "Zaehlen Sie 3 Massnahmen auf.",
        erwartungshorizont={"erwartungspunkte": [{"text": "Begruendet die Reihenfolge.", "punkte": 3}]},
    )
    results = check_form_07(aufgabe, judge=_judge_returning(True, beleg_zitat="Begruendet die Reihenfolge."))
    assert "Begruendet die Reihenfolge." in results[0].finding


def test_realistic_well_constructed_teilaufgabe_stays_quiet() -> None:
    """The case the suite was missing entirely: a terse, note-form
    Erwartungshorizont that legitimately matches its operator. Terseness is
    normal in a marking scheme and must not itself read as a mismatch -- the
    exact false positive that made this check flag 23 of 25 clean
    Teilaufgaben before the prompt was fixed."""
    aufgabe = _aufgabe(
        "Begruenden Sie 2 pflegerische Massnahmen, die die Selbststaendigkeit von Frau Ostermann erhalten.",
        erwartungshorizont={
            "erwartungspunkte": [
                {"text": "Anleitung zum sicheren Rollatorgebrauch, weil erhaltene Mobilitaet die Selbstversorgung traegt", "punkte": 3},
                {"text": "Beibehaltung der eigenen Mahlzeitenzubereitung, weil Alltagsaktivitaet Faehigkeiten stabilisiert", "punkte": 3},
            ]
        },
    )
    results = check_form_07(aufgabe, judge=_judge_returning(False))
    assert results == []
