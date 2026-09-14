"""KOMP-04: Anforderungsniveau distribution must not be degenerate across
the whole paper. Ground truth is items/manifest.json's C-03 entry
("every Teilaufgabe in both Aufgabe blocks declares Anforderungsniveau I")
plus a full sweep confirming C-03 is the only one of the 12 real items with
exactly one distinct declared level.
"""
from __future__ import annotations

import json
from pathlib import Path

from checks.deterministic.komp_04 import check_komp_04
from schemas.aufgabe import Aufsichtsarbeit
from schemas.flag import Flag, NotChecked

ITEMS_DIR = Path(__file__).resolve().parents[1] / "items"


def load(name: str) -> Aufsichtsarbeit:
    return Aufsichtsarbeit.model_validate(json.loads((ITEMS_DIR / f"{name}.json").read_text(encoding="utf-8")))


def test_fires_on_c_03() -> None:
    flags = [f for f in check_komp_04(load("C-03")) if isinstance(f, Flag)]
    assert len(flags) == 1
    assert "I" in flags[0].finding
    assert flags[0].severity == "pruefen"


def test_a_clean_item_does_not_fire() -> None:
    assert [f for f in check_komp_04(load("A-01")) if isinstance(f, Flag)] == []


def test_only_c_03_fires_across_the_real_corpus() -> None:
    paths = sorted(p for p in ITEMS_DIR.glob("*.json") if p.name != "manifest.json")
    fired = [p.stem for p in paths if [f for f in check_komp_04(load(p.stem)) if isinstance(f, Flag)]]
    assert fired == ["C-03"]


def test_no_declared_niveau_is_not_checked() -> None:
    aufgabe = Aufsichtsarbeit.model_validate({"aufgaben": [{"teilaufgaben": [{"text": "x"}]}]})
    results = check_komp_04(aufgabe)
    assert len(results) == 1
    assert isinstance(results[0], NotChecked)


def test_two_distinct_levels_across_blocks_does_not_fire() -> None:
    aufgabe = Aufsichtsarbeit.model_validate(
        {
            "aufgaben": [
                {"teilaufgaben": [{"text": "x", "anforderungsniveau": "I"}]},
                {"teilaufgaben": [{"text": "y", "anforderungsniveau": "II"}]},
            ]
        }
    )
    assert check_komp_04(aufgabe) == []
