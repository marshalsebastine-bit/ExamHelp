"""KOMP-03 / KOMP-03B: does the item relate to its declared Pruefungsbereich.

The two-rule split exists because one rule's own rule_text turned out to
contradict itself: "must cover the Schwerpunkte" (read: full coverage) versus
the stated trigger "touches none of them" (read: any overlap at all). Neither
literal reading matched items/manifest.json's own documented intent for C-03,
and "full coverage" would have false-flagged B-01 and B-03, which the manifest
documents as sound. These tests pin the corrected two-threshold design against
the real corpus rather than against invented fixtures, so a regression here
means the split rules disagree with what the corpus was built to demonstrate.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from checks.deterministic.komp_03 import check_komp_03, check_komp_03b, claimed_schwerpunkte, schwerpunkt
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


def test_claimed_schwerpunkte_deduplicates_across_teilaufgaben() -> None:
    aufgabe = Aufsichtsarbeit.model_validate(
        {"teilaufgaben": [{"kompetenzzuordnung": ["I.3.a", "I.3.b"]}, {"kompetenzzuordnung": ["I.4.a"]}]}
    )
    assert claimed_schwerpunkte(aufgabe) == {"I.3", "I.4"}


@pytest.mark.parametrize("path", ITEM_PATHS, ids=lambda p: p.stem)
def test_komp_03_never_fires_on_the_synthetic_corpus(path: Path) -> None:
    """No item in the corpus touches zero of its required Schwerpunkte -- the
    blocker case is real but deliberately rare."""
    aufgabe = Aufsichtsarbeit.model_validate(json.loads(path.read_text(encoding="utf-8")))
    result = check_komp_03(aufgabe)
    assert not any(isinstance(entry, Flag) for entry in result), f"{path.stem}: unexpected KOMP-03 flag"


def test_komp_03b_fires_only_on_c_03() -> None:
    """C-03 is the documented KOMP-03(B) demonstration case: it claims I.2.g,
    IV.1.a and II.1.a alongside a single I.3.a, covering only 1 of the 4
    Schwerpunkte Pruefungsbereich 3 requires."""
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
    should fire. These are documented as sound items; flagging them would be
    exactly the false-flag-fatigue failure mode tech doc 1.5.1/7.3 warns about."""
    for name in ("B-01", "B-03"):
        aufgabe = load(name)
        assert check_komp_03(aufgabe) == []
        assert check_komp_03b(aufgabe) == []


def test_exactly_half_coverage_does_not_fire_komp_03b() -> None:
    """D-01 covers 2 of 4 Schwerpunkte -- exactly half. It is also an
    unfinished draft with only 2 of an intended 4 Teilaufgaben, so this
    doubles as a check that KOMP-03B does not punish an in-progress draft
    for not yet having reached its later Teilaufgaben."""
    aufgabe = load("D-01")
    assert check_komp_03b(aufgabe) == []


def test_empty_intersection_fires_komp_03_as_blocker() -> None:
    """Synthetic case for the rare blocker condition, since no corpus item
    reaches it: every claimed code is outside the declared Pruefungsbereich."""
    aufgabe = Aufsichtsarbeit.model_validate(
        {
            "metadaten": {"pruefungsbereich": "3"},  # requires I.3, I.4, II.3, III.2
            "teilaufgaben": [{"kompetenzzuordnung": ["I.1.a"]}, {"kompetenzzuordnung": ["I.2.b"]}],
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
    aufgabe = Aufsichtsarbeit.model_validate({"teilaufgaben": [{"kompetenzzuordnung": ["I.1.a"]}]})
    for check in (check_komp_03, check_komp_03b):
        result = check(aufgabe)
        assert len(result) == 1
        assert isinstance(result[0], NotChecked)
        assert "aufgabe.metadaten.pruefungsbereich" in result[0].missing


def test_missing_kompetenzzuordnung_is_not_checked_not_flagged() -> None:
    aufgabe = Aufsichtsarbeit.model_validate({"metadaten": {"pruefungsbereich": "1"}, "teilaufgaben": [{"text": "x"}]})
    for check in (check_komp_03, check_komp_03b):
        result = check(aufgabe)
        assert len(result) == 1
        assert isinstance(result[0], NotChecked)
        assert "teilaufgabe.kompetenzzuordnung" in result[0].missing
