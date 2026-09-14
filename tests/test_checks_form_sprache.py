"""FORM-05, FORM-12, FORM-14, FORM-15: linguistic-pattern checks on
Fallsituation/Teilaufgabe prose. Ground truth for the positive cases is
items/manifest.json's known_weaknesses for C-01 (deliberately constructed
to trip all four at once) plus C-02/C-03, which is where each rule's own
example in rules/form.yaml is verified against real text rather than only
a hand-written fixture.

A-02 stands in for "a clean item" across all four rules: unlike A-01 (which
genuinely contains one real werden-passive sentence -- a correct FORM-14
catch, not a bug, see form_sprache.py's docstring) A-02 has nothing at all
in any of the four dimensions, so it is the item that actually supports a
"nothing fires" assertion.
"""
from __future__ import annotations

import json
from pathlib import Path

from checks.deterministic.form_sprache import check_form_05, check_form_12, check_form_14, check_form_15
from schemas.aufgabe import Aufsichtsarbeit
from schemas.flag import Flag

ITEMS_DIR = Path(__file__).resolve().parents[1] / "items"


def load(name: str) -> Aufsichtsarbeit:
    return Aufsichtsarbeit.model_validate(json.loads((ITEMS_DIR / f"{name}.json").read_text(encoding="utf-8")))


# ---- FORM-05 ------------------------------------------------------------------

def test_form_05_fires_on_both_blocks_of_c_01() -> None:
    flags = check_form_05(load("C-01"))
    anchors = {f.anchor for f in flags}
    assert anchors == {"ag.1", "ag.2"}
    # Both defect types are present in Aufgabe 1; only the Schachtelsatz in Aufgabe 2.
    kinds_ag1 = {"Verschachtelt" in f.finding or "Negation" in f.finding for f in flags if f.anchor == "ag.1"}
    assert kinds_ag1 == {True}
    assert len([f for f in flags if f.anchor == "ag.1"]) == 2


def test_form_05_a_clean_item_does_not_fire() -> None:
    assert check_form_05(load("A-02")) == []


def test_form_05_short_sentence_does_not_fire() -> None:
    aufgabe = Aufsichtsarbeit.model_validate(
        {"aufgaben": [{"fallsituation": {"text": "Frau Muster ist 80 Jahre alt und lebt allein."}}]}
    )
    assert check_form_05(aufgabe) == []


# ---- FORM-12 ------------------------------------------------------------------

def test_form_12_fires_on_c_01() -> None:
    flags = [f for f in check_form_12(load("C-01")) if f.anchor == "ag.1"]
    assert len(flags) == 1
    assert "fuenf" in flags[0].finding and "zweiundachtzig" in flags[0].finding


def test_form_12_a_clean_item_does_not_fire() -> None:
    assert check_form_12(load("A-02")) == []


def test_form_12_does_not_flag_the_indefinite_article() -> None:
    """'ein'/'eins' is deliberately excluded: it is also the indefinite
    article, and flagging every 'ein Rollator' would swamp this
    hinweis-severity check with noise (see module docstring)."""
    aufgabe = Aufsichtsarbeit.model_validate({"aufgaben": [{"fallsituation": {"text": "Sie nutzt einen Rollator."}}]})
    assert check_form_12(aufgabe) == []


def test_form_12_catches_a_compound_number_word() -> None:
    aufgabe = Aufsichtsarbeit.model_validate({"aufgaben": [{"fallsituation": {"text": "Sie ist einundzwanzig Jahre alt."}}]})
    flags = check_form_12(aufgabe)
    assert len(flags) == 1
    assert "einundzwanzig" in flags[0].finding


# ---- FORM-14 ------------------------------------------------------------------

def test_form_14_fires_on_c_01() -> None:
    flags = check_form_14(load("C-01"))
    anchors = {f.anchor for f in flags}
    assert anchors == {"ag.1", "ag.2"}


def test_form_14_a_clean_item_does_not_fire() -> None:
    assert check_form_14(load("A-02")) == []


def test_form_14_active_sentence_does_not_fire() -> None:
    aufgabe = Aufsichtsarbeit.model_validate(
        {"aufgaben": [{"fallsituation": {"text": "Die Pflegefachperson misst den Blutdruck."}}]}
    )
    assert check_form_14(aufgabe) == []


# ---- FORM-15 ------------------------------------------------------------------

def test_form_15_fires_on_c_01() -> None:
    flags = check_form_15(load("C-01"))
    anchors = {f.anchor for f in flags}
    assert "ag.1" in anchors


def test_form_15_a_clean_item_does_not_fire() -> None:
    assert check_form_15(load("A-02")) == []


def test_form_15_does_not_flag_common_modal_hedging() -> None:
    """'moechte'/'koennte'/'sollte' are common, ambiguous modal usage in
    ordinary German (and 'moechte' already appears in the real A-01
    fixture) -- deliberately excluded, see module docstring."""
    aufgabe = Aufsichtsarbeit.model_validate(
        {"aufgaben": [{"fallsituation": {"text": "Sie moechte weiterhin selbststaendig kochen."}}]}
    )
    assert check_form_15(aufgabe) == []


def test_form_15_catches_ascii_transliterated_konjunktiv() -> None:
    aufgabe = Aufsichtsarbeit.model_validate(
        {"aufgaben": [{"fallsituation": {"text": "Sie sagte, dass sie das gerne tun wuerde."}}]}
    )
    flags = check_form_15(aufgabe)
    assert len(flags) == 1
    assert "wuerde" in flags[0].finding
