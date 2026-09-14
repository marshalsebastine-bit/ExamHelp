"""KOMP-03 / KOMP-03B: does the item relate to its declared Pruefungsbereich.

Recreated after the 2026-09-11 schema change removed teilaufgabe.kompetenzzuordnung
(the author claim these tests used to exercise) and it was replaced same-day with
teilaufgabe.kompetenzzuordnung_abgeleitet, an LLM-derived value populated by KOMP-01
(checks/llm/komp_01.py). The corpus-driven assertions are the same as before the
schema change -- B-01/B-03 sound at 3-of-4, C-03 the KOMP-03B demonstration at
1-of-4, D-01 the exactly-half boundary case -- just re-authored against the new
field, since the old author-claimed values could not be reused as-is (they were
not constrained to any Teilaufgabe's curriculare-Einheit candidate set, which the
new derived values must be).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from checks.deterministic.komp_03 import check_komp_03, check_komp_03b, derived_schwerpunkte, schwerpunkt
from schemas.aufgabe import Aufsichtsarbeit
from schemas.flag import Flag, NotChecked

ITEMS_DIR = Path(__file__).resolve().parents[1] / "items"
ITEM_PATHS = sorted(p for p in ITEMS_DIR.glob("*.json") if p.name != "manifest.json")


def load(name: str) -> Aufsichtsarbeit:
    return Aufsichtsarbeit.model_validate(
        json.loads((ITEMS_DIR / f"{name}.json").read_text(encoding="utf-8"))
    )


def test_schwerpunkt_reduces_einzelkompetenz_to_its_schwerpunkt() -> None:
    assert schwerpunkt("I.3.a") == "I.3"
    assert schwerpunkt("III.2.f") == "III.2"


def test_derived_schwerpunkte_deduplicates_across_teilaufgaben() -> None:
    aufgabe = Aufsichtsarbeit.model_validate(
        {
            "aufgaben": [
                {
                    "teilaufgaben": [
                        {"kompetenzzuordnung_abgeleitet": ["I.3.a", "I.3.b"]},
                        {"kompetenzzuordnung_abgeleitet": ["I.4.a"]},
                    ]
                }
            ]
        }
    )
    assert derived_schwerpunkte(aufgabe) == {"I.3", "I.4"}


def test_derived_schwerpunkte_pools_across_both_aufgabe_blocks() -> None:
    """The Pruefungsbereich correspondence is one per whole paper (PflAPrV
    Sec 14 (1)-(2)): a code derived only in Aufgabe 2 must still count."""
    aufgabe = Aufsichtsarbeit.model_validate(
        {
            "aufgaben": [
                {"teilaufgaben": [{"kompetenzzuordnung_abgeleitet": ["I.3.a"]}]},
                {"teilaufgaben": [{"kompetenzzuordnung_abgeleitet": ["II.3.a"]}]},
            ]
        }
    )
    assert derived_schwerpunkte(aufgabe) == {"I.3", "II.3"}


@pytest.mark.parametrize("path", ITEM_PATHS, ids=lambda p: p.stem)
def test_komp_03_never_fires_on_the_synthetic_corpus(path: Path) -> None:
    """No item in the corpus touches zero of its required Schwerpunkte -- the
    blocker case is real but deliberately rare."""
    aufgabe = Aufsichtsarbeit.model_validate(json.loads(path.read_text(encoding="utf-8")))
    result = check_komp_03(aufgabe)
    assert not any(isinstance(entry, Flag) for entry in result), f"{path.stem}: unexpected KOMP-03 flag"


def test_komp_03b_fires_only_on_c_03() -> None:
    """C-03 is the documented KOMP-03(B) demonstration case: it covers only
    I.3 of Pruefungsbereich 3's 4 Kompetenzschwerpunkte."""
    flagged = []
    for path in ITEM_PATHS:
        aufgabe = load(path.stem)
        result = check_komp_03b(aufgabe)
        if any(isinstance(entry, Flag) for entry in result):
            flagged.append(path.stem)
    assert flagged == ["C-03"]


def test_komp_03b_flag_reports_the_actual_coverage() -> None:
    flags = check_komp_03b(load("C-03"))
    assert len(flags) == 1
    flag = flags[0]
    assert flag.rule_id == "KOMP-03B"
    assert flag.severity == "pruefen"
    assert "1 von 4" in flag.finding
    assert flag.evidence.rule_quote


def test_sound_items_with_partial_coverage_do_not_flag() -> None:
    """B-01 and B-03 cover 3 of 4 Schwerpunkte -- a majority, so neither rule
    should fire."""
    for name in ("B-01", "B-03"):
        aufgabe = load(name)
        assert check_komp_03(aufgabe) == []
        assert check_komp_03b(aufgabe) == []


def test_exactly_half_coverage_does_not_fire_komp_03b() -> None:
    """D-01 covers 2 of 4 Schwerpunkte -- exactly half. It is also an
    unfinished draft with only 2 Teilaufgaben, doubling as a check that
    KOMP-03B does not punish an in-progress draft."""
    aufgabe = load("D-01")
    assert check_komp_03b(aufgabe) == []


def test_empty_intersection_fires_komp_03_as_blocker() -> None:
    """Synthetic case for the rare blocker condition, since no corpus item
    reaches it: every derived code is outside the declared Pruefungsbereich."""
    aufgabe = Aufsichtsarbeit.model_validate(
        {
            "metadaten": {"pruefungsbereich": "3"},  # requires I.3, I.4, II.3, III.2
            "aufgaben": [
                {
                    "teilaufgaben": [
                        {"kompetenzzuordnung_abgeleitet": ["I.1.a"]},
                        {"kompetenzzuordnung_abgeleitet": ["I.2.b"]},
                    ]
                }
            ],
        }
    )
    flags = check_komp_03(aufgabe)
    assert len(flags) == 1
    assert flags[0].severity == "blocker"
    assert flags[0].rule_id == "KOMP-03"

    # And KOMP-03B fires too: zero coverage is also "fewer than half".
    assert len(check_komp_03b(aufgabe)) == 1


def test_missing_pruefungsbereich_is_not_checked_not_flagged() -> None:
    """requires unmet -> skip visibly, never flag (tech doc 1.5.1)."""
    aufgabe = Aufsichtsarbeit.model_validate(
        {"aufgaben": [{"teilaufgaben": [{"kompetenzzuordnung_abgeleitet": ["I.1.a"]}]}]}
    )
    for check in (check_komp_03, check_komp_03b):
        result = check(aufgabe)
        assert len(result) == 1
        assert isinstance(result[0], NotChecked)
        assert "aufgabe.metadaten.pruefungsbereich" in result[0].missing


def test_missing_kompetenzzuordnung_abgeleitet_is_not_checked_not_flagged() -> None:
    aufgabe = Aufsichtsarbeit.model_validate(
        {"metadaten": {"pruefungsbereich": "1"}, "aufgaben": [{"teilaufgaben": [{"text": "x"}]}]}
    )
    for check in (check_komp_03, check_komp_03b):
        result = check(aufgabe)
        assert len(result) == 1
        assert isinstance(result[0], NotChecked)
        assert "teilaufgabe.kompetenzzuordnung_abgeleitet" in result[0].missing
