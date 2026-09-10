"""The synthetic base corpus.

The load-bearing property is not that these items are good but that the schema
accepts every one of them, including the unfinished draft.  A schema that
rejects incomplete input locks out the primary user (tech doc 1.5.1).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from schemas.aufgabe import Aufsichtsarbeit

ITEMS_DIR = Path(__file__).resolve().parents[1] / "items"
ITEM_PATHS = sorted(p for p in ITEMS_DIR.glob("*.json") if p.name != "manifest.json")


def load(path: Path) -> Aufsichtsarbeit:
    return Aufsichtsarbeit.model_validate(json.loads(path.read_text(encoding="utf-8")))


def test_twelve_base_items_exist() -> None:
    assert len(ITEM_PATHS) == 12


@pytest.mark.parametrize("path", ITEM_PATHS, ids=lambda p: p.stem)
def test_item_validates(path: Path) -> None:
    aufgabe = load(path)
    assert aufgabe.aufgabe_id == path.stem
    assert aufgabe.teilaufgaben, "every base item has at least one Teilaufgabe"


@pytest.mark.parametrize("path", ITEM_PATHS, ids=lambda p: p.stem)
def test_anchors_resolve(path: Path) -> None:
    """Every anchor the item advertises must resolve, or a flag cannot be placed."""
    aufgabe = load(path)
    for anchor in aufgabe.anchors():
        assert aufgabe.resolve(anchor) is not None, f"{anchor} does not resolve"


def test_unfinished_draft_validates_and_reports_gaps() -> None:
    """D-01 is the item that proves the tool works during drafting."""
    draft = load(ITEMS_DIR / "D-01.json")
    completeness = draft.completeness()
    assert completeness["teilaufgabe.text"]
    assert not completeness["teilaufgabe.erwartungshorizont"]


def test_corpus_spreads_across_versorgungsbereiche_and_altersgruppen() -> None:
    """Deliberate spread, per tech doc 7.1."""
    items = [load(p) for p in ITEM_PATHS]
    bereiche = {i.fallsituation.versorgungsbereich for i in items}
    altersgruppen = {i.fallsituation.altersgruppe for i in items}
    assert len(bereiche) >= 5, f"only {bereiche}"
    assert altersgruppen == {"kind", "jugendlicher", "erwachsener", "alter_mensch"}


def test_sibling_references_are_symmetric() -> None:
    """KOMP-05 walks these, so a one-way reference would silently skip the check."""
    items = {p.stem: load(p) for p in ITEM_PATHS}
    for item_id, aufgabe in items.items():
        for sibling in aufgabe.geschwister_aufgaben:
            assert sibling in items, f"{item_id} references unknown sibling {sibling}"
            assert item_id in items[sibling].geschwister_aufgaben, (
                f"{sibling} does not reference {item_id} back"
            )


def test_claimed_competency_codes_are_well_formed() -> None:
    """Well-formed, not necessarily valid: C-03 deliberately claims an
    Anlage-1-only code so KOMP-06 has something to find."""
    import re

    for path in ITEM_PATHS:
        for teilaufgabe in load(path).teilaufgaben:
            for code in teilaufgabe.kompetenzzuordnung:
                assert re.fullmatch(r"[IVX]{1,3}\.\d{1,2}\.[a-z]", code), f"{path.stem}: {code}"


def test_the_deliberate_komp_06_defect_is_present() -> None:
    """If this stops being a defect, C-03 has silently become a clean item."""
    from checks.catalogue import load_anlage_1_codes, load_anlage_2_codes

    claimed = {c for t in load(ITEMS_DIR / "C-03.json").teilaufgaben for c in t.kompetenzzuordnung}
    anlage_1_only = claimed & (load_anlage_1_codes() - load_anlage_2_codes())
    assert anlage_1_only == {"I.2.g"}


def test_manifest_covers_every_item() -> None:
    manifest = json.loads((ITEMS_DIR / "manifest.json").read_text(encoding="utf-8"))
    listed = {i for s in manifest["sets"] for i in s["items"]}
    assert listed == {p.stem for p in ITEM_PATHS}
