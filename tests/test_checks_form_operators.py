"""FORM-03, FORM-04, FORM-11, FORM-13: operator extraction and its four
readings. Ground truth is items/manifest.json's known_weaknesses for
C-01/C-02/C-03, plus a couple of extra true positives those items contain
that the manifest's illustrative list does not call out by name (verified
directly against the item text in each case, not assumed).
"""
from __future__ import annotations

import json
from pathlib import Path

from checks.deterministic.form_operators import (
    check_form_03,
    check_form_04,
    check_form_11,
    check_form_13,
    find_operator_matches,
)
from schemas.aufgabe import Aufsichtsarbeit
from schemas.flag import Flag, NotChecked

ITEMS_DIR = Path(__file__).resolve().parents[1] / "items"


def load(name: str) -> Aufsichtsarbeit:
    return Aufsichtsarbeit.model_validate(json.loads((ITEMS_DIR / f"{name}.json").read_text(encoding="utf-8")))


# ---- extraction --------------------------------------------------------------

def test_find_operator_matches_does_not_misread_benennen_as_nennen() -> None:
    """'Benennen Sie' textually contains the substring 'nennen Sie' -- a
    regex without a leading word boundary would double-match it as the
    distinct operator 'nennen' too."""
    matches = find_operator_matches("Benennen Sie 3 Berufsgruppen.")
    assert [m["operator"] for m in matches] == ["benennen"]


def test_find_operator_matches_requires_the_separable_particle() -> None:
    """'Stellen Sie das dar' has no 'gegenueber' anywhere, so it must not
    be attributed to the catalogue operator 'gegenueberstellen'."""
    assert find_operator_matches("Stellen Sie das dar.") == []


def test_find_operator_matches_finds_a_separable_operator_with_its_particle() -> None:
    matches = find_operator_matches("Stellen Sie 2 Konzepte gegenueber.")
    assert [m["operator"] for m in matches] == ["gegenüberstellen"]


def test_find_operator_matches_tolerates_ascii_transliteration() -> None:
    """Real corpus text is written 'Begruenden', not 'Begründen'."""
    matches = find_operator_matches("Begruenden Sie 2 Massnahmen.")
    assert [m["operator"] for m in matches] == ["begründen"]


# ---- FORM-03 ------------------------------------------------------------------

def test_form_03_a_clean_item_does_not_fire() -> None:
    assert [f for f in check_form_03(load("A-01")) if isinstance(f, Flag)] == []


def test_form_03_nominalised_instruction_is_not_checked_not_flagged() -> None:
    """C-01's ag.1.ta.2 has no operator at all -- FORM-11's defect, not
    FORM-03's: there is no verb here to judge against the list."""
    results = [r for r in check_form_03(load("C-01")) if r.anchor == "ag.1.ta.2"]
    assert len(results) == 1
    assert isinstance(results[0], NotChecked)


def test_form_03_fires_on_an_unlisted_operator() -> None:
    aufgabe = Aufsichtsarbeit.model_validate(
        {"aufgaben": [{"teilaufgaben": [{"text": "Erfinden Sie 3 Loesungen."}]}]}
    )
    flags = [f for f in check_form_03(aufgabe) if isinstance(f, Flag)]
    assert len(flags) == 1
    assert "Erfinden" in flags[0].finding


# ---- FORM-04 ------------------------------------------------------------------

def test_form_04_fires_on_c_02() -> None:
    flags = [f for f in check_form_04(load("C-02")) if isinstance(f, Flag)]
    assert len(flags) == 1
    assert flags[0].anchor == "ag.1.ta.1"
    assert "nennen" in flags[0].finding and "III" in flags[0].finding


def test_form_04_a_clean_item_does_not_fire() -> None:
    assert [f for f in check_form_04(load("A-01")) if isinstance(f, Flag)] == []


def test_form_04_no_recognised_operator_is_not_checked() -> None:
    aufgabe = Aufsichtsarbeit.model_validate(
        {"aufgaben": [{"teilaufgaben": [{"text": "Es sollte etwas erfolgen.", "anforderungsniveau": "I"}]}]}
    )
    results = check_form_04(aufgabe)
    assert len(results) == 1
    assert isinstance(results[0], NotChecked)


# ---- FORM-11 ------------------------------------------------------------------

def test_form_11_fires_on_two_operators_in_c_03() -> None:
    flags = [f for f in check_form_11(load("C-03")) if isinstance(f, Flag) and f.anchor == "ag.1.ta.1"]
    assert len(flags) == 1
    assert "nennen" in flags[0].finding and "bewerten" in flags[0].finding


def test_form_11_fires_on_zero_operators_in_c_01() -> None:
    flags = [f for f in check_form_11(load("C-01")) if isinstance(f, Flag)]
    anchors = {f.anchor for f in flags}
    assert {"ag.1.ta.2", "ag.2.ta.2"} <= anchors


def test_form_11_a_clean_item_does_not_fire() -> None:
    assert [f for f in check_form_11(load("A-01")) if isinstance(f, Flag)] == []


def test_form_11_operator_not_at_sentence_start_fires() -> None:
    aufgabe = Aufsichtsarbeit.model_validate(
        {"aufgaben": [{"teilaufgaben": [{"text": "Bei Frau Muster nennen Sie 3 Massnahmen."}]}]}
    )
    flags = [f for f in check_form_11(aufgabe) if isinstance(f, Flag)]
    assert len(flags) == 1
    assert "Satzanfang" in flags[0].finding


# ---- FORM-13 ------------------------------------------------------------------

def test_form_13_fires_on_c_01() -> None:
    flags = [f for f in check_form_13(load("C-01")) if isinstance(f, Flag) and f.anchor == "ag.1.ta.1"]
    assert len(flags) == 1
    assert "nennen" in flags[0].finding


def test_form_13_does_not_fire_when_a_count_is_present() -> None:
    aufgabe = Aufsichtsarbeit.model_validate({"aufgaben": [{"teilaufgaben": [{"text": "Nennen Sie 3 Massnahmen."}]}]})
    assert [f for f in check_form_13(aufgabe) if isinstance(f, Flag)] == []


def test_form_13_does_not_apply_to_a_non_enumerating_operator() -> None:
    aufgabe = Aufsichtsarbeit.model_validate({"aufgaben": [{"teilaufgaben": [{"text": "Begruenden Sie Massnahmen."}]}]})
    assert [f for f in check_form_13(aufgabe) if isinstance(f, Flag)] == []


def test_form_13_a_clean_item_does_not_fire() -> None:
    assert [f for f in check_form_13(load("A-01")) if isinstance(f, Flag)] == []
