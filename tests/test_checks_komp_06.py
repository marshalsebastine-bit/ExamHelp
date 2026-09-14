"""KOMP-06: every derived competency code exists in Anlage 2.

Never had a code implementation before teilaufgabe.kompetenzzuordnung_abgeleitet
(checks/deterministic/komp_06.py, new 2026-09-11): the old author-claimed
kompetenzzuordnung field was removed with no replacement before this field
took its place the same day.
"""
from __future__ import annotations

import json
from pathlib import Path

from checks.deterministic.komp_06 import check_komp_06
from schemas.aufgabe import Aufsichtsarbeit
from schemas.flag import Flag, NotChecked

ITEMS_DIR = Path(__file__).resolve().parents[1] / "items"


def load(name: str) -> Aufsichtsarbeit:
    return Aufsichtsarbeit.model_validate(
        json.loads((ITEMS_DIR / f"{name}.json").read_text(encoding="utf-8"))
    )


def test_the_deliberate_defect_fires_on_c_03() -> None:
    """ag.1.ta.2 derives I.2.g, which exists in Anlage 1 but not Anlage 2 --
    the only such code in the catalogue, injected deliberately since real
    derivation is filtered to a candidate set that is itself always a
    subset of Anlage 2 (checks/llm/kompetenz_candidates.py)."""
    flags = [f for f in check_komp_06(load("C-03")) if isinstance(f, Flag)]
    assert len(flags) == 1
    assert flags[0].anchor == "ag.1.ta.2"
    assert "I.2.g" in flags[0].finding
    assert flags[0].severity == "blocker"


def test_a_clean_item_does_not_fire() -> None:
    flags = [f for f in check_komp_06(load("A-01")) if isinstance(f, Flag)]
    assert flags == []


def test_missing_derived_field_is_not_checked_not_flagged() -> None:
    aufgabe = Aufsichtsarbeit.model_validate({"aufgaben": [{"teilaufgaben": [{"text": "x"}]}]})
    results = check_komp_06(aufgabe)
    assert len(results) == 1
    assert isinstance(results[0], NotChecked)
    assert "teilaufgabe.kompetenzzuordnung_abgeleitet" in results[0].missing


def test_an_invented_code_that_exists_in_neither_anlage_also_fires() -> None:
    """The common real defect is a mistyped or invented reference, not
    specifically an Anlage-1-only one -- both are set-membership failures."""
    aufgabe = Aufsichtsarbeit.model_validate(
        {"aufgaben": [{"teilaufgaben": [{"kompetenzzuordnung_abgeleitet": ["Z.9.z"]}]}]}
    )
    flags = [f for f in check_komp_06(aufgabe) if isinstance(f, Flag)]
    assert len(flags) == 1
    assert "Z.9.z" in flags[0].finding
