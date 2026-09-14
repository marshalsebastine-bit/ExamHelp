"""FORM-02, FORM-06, FORM-16: Punkte arithmetic.

Ground truth for the real-item assertions is items/manifest.json's
known_weaknesses (C-01, C-02, D-01) plus a direct arithmetic check on C-03,
which mathematically also falls under FORM-16's 40 percent floor even
though the manifest does not call it out (its own C-03 entry documents
Family B/KOMP defects; this Family A imbalance is a real, if unremarked,
side effect of that item's construction -- the rule fires on what the
Punkte actually say, not on what a fixture's own notes happened to list).
"""
from __future__ import annotations

import json
from pathlib import Path

from checks.deterministic.form_punkte import check_form_02, check_form_06, check_form_16
from schemas.aufgabe import Aufsichtsarbeit
from schemas.flag import Flag, NotChecked

ITEMS_DIR = Path(__file__).resolve().parents[1] / "items"


def load(name: str) -> Aufsichtsarbeit:
    return Aufsichtsarbeit.model_validate(json.loads((ITEMS_DIR / f"{name}.json").read_text(encoding="utf-8")))


# ---- FORM-02 ----------------------------------------------------------------

def test_form_02_a_clean_item_does_not_fire() -> None:
    assert [f for f in check_form_02(load("A-01")) if isinstance(f, Flag)] == []


def test_form_02_incomplete_draft_is_not_checked_not_flagged() -> None:
    """D-01 has only one of two Aufgabe blocks written. A workload judgement
    against half a paper is meaningless, not evidence of implausibility."""
    results = check_form_02(load("D-01"))
    assert len(results) == 1
    assert isinstance(results[0], NotChecked)
    assert "aufgabe.aufgaben[2]" in results[0].missing


def test_form_02_fires_on_inflated_scope() -> None:
    aufgabe = Aufsichtsarbeit.model_validate(
        {
            "metadaten": {"bearbeitungszeit_minuten": 120},
            "aufgaben": [
                {"teilaufgaben": [{"text": "x", "punkte": 40.0} for _ in range(4)]},
                {"teilaufgaben": [{"text": "x", "punkte": 25.0} for _ in range(4)]},
            ],
        }
    )
    flags = [f for f in check_form_02(aufgabe) if isinstance(f, Flag)]
    assert len(flags) == 1
    assert flags[0].severity == "pruefen"


def test_form_02_missing_punkte_is_not_checked() -> None:
    aufgabe = Aufsichtsarbeit.model_validate(
        {"aufgaben": [{"teilaufgaben": [{"text": "x"}]}, {"teilaufgaben": [{"text": "y"}]}]}
    )
    results = check_form_02(aufgabe)
    assert len(results) == 1
    assert isinstance(results[0], NotChecked)


# ---- FORM-06 ----------------------------------------------------------------

def test_form_06_fires_on_c_01() -> None:
    flags = [f for f in check_form_06(load("C-01")) if isinstance(f, Flag)]
    assert len(flags) == 1
    assert flags[0].anchor == "ag.1.ta.1"
    assert "8" in flags[0].finding and "6" in flags[0].finding


def test_form_06_matching_sums_on_c_03_do_not_fire() -> None:
    """C-03's ag.1.ta.1 declares 8 Punkte with an unevenly-weighted (2+3+3)
    but correctly-summing Erwartungshorizont -- a real quirk, not a
    FORM-06 violation (see items/manifest.json's own note on this item)."""
    flags = [f for f in check_form_06(load("C-03")) if isinstance(f, Flag) and f.anchor == "ag.1.ta.1"]
    assert flags == []


def test_form_06_a_clean_item_does_not_fire() -> None:
    assert [f for f in check_form_06(load("A-01")) if isinstance(f, Flag)] == []


def test_form_06_missing_erwartungshorizont_is_not_checked() -> None:
    results = [r for r in check_form_06(load("D-01")) if isinstance(r, NotChecked)]
    assert any("erwartungshorizont" in r.missing[0] for r in results)


def test_form_06_missing_punkte_is_not_checked() -> None:
    aufgabe = Aufsichtsarbeit.model_validate({"aufgaben": [{"teilaufgaben": [{"text": "x"}]}]})
    results = check_form_06(aufgabe)
    assert len(results) == 1
    assert isinstance(results[0], NotChecked)
    assert "teilaufgabe.punkte" in results[0].missing


# ---- FORM-16 ----------------------------------------------------------------

def test_form_16_fires_on_c_01() -> None:
    flags = [f for f in check_form_16(load("C-01")) if isinstance(f, Flag)]
    assert len(flags) == 1
    assert "37%" in flags[0].finding


def test_form_16_fires_on_c_02() -> None:
    flags = [f for f in check_form_16(load("C-02")) if isinstance(f, Flag)]
    assert len(flags) == 1
    assert "32%" in flags[0].finding


def test_form_16_a_clean_item_does_not_fire() -> None:
    assert [f for f in check_form_16(load("A-01")) if isinstance(f, Flag)] == []


def test_form_16_incomplete_draft_is_not_checked() -> None:
    results = check_form_16(load("D-01"))
    assert len(results) == 1
    assert isinstance(results[0], NotChecked)
