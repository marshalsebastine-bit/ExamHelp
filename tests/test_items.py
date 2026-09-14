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
    assert aufgabe.aufgaben, "every base item has at least one Aufgabe block"
    assert aufgabe.alle_teilaufgaben(), "every base item has at least one Teilaufgabe"


@pytest.mark.parametrize("path", ITEM_PATHS, ids=lambda p: p.stem)
def test_item_has_two_aufgabe_blocks_unless_a_deliberate_draft(path: Path) -> None:
    """One Aufsichtsarbeit is always exactly two Aufgabe blocks (Aufgabe 1 /
    Aufgabe 2) when complete. D-01 is the one deliberate exception: an
    in-progress draft where Aufgabe 2 has not been started yet, which is what
    exercises completeness()["aufgaben.vollstaendig"] against a real fixture."""
    aufgabe = load(path)
    if path.stem == "D-01":
        assert len(aufgabe.aufgaben) == 1
    else:
        assert len(aufgabe.aufgaben) == 2


@pytest.mark.parametrize("path", ITEM_PATHS, ids=lambda p: p.stem)
def test_anchors_resolve(path: Path) -> None:
    """Every anchor the item advertises must resolve, or a flag cannot be placed."""
    aufgabe = load(path)
    for anchor in aufgabe.anchors():
        assert aufgabe.resolve(anchor) is not None, f"{anchor} does not resolve"


def test_unfinished_draft_validates_and_reports_gaps() -> None:
    """D-01 is the item that proves the tool works during drafting: Aufgabe 1
    is written but has no Erwartungshorizont yet, and Aufgabe 2 has not been
    started at all -- two independent, simultaneously-true completeness gaps."""
    draft = load(ITEMS_DIR / "D-01.json")
    completeness = draft.completeness()
    assert completeness["aufgabe_1.teilaufgabe.text"]
    assert not completeness["aufgabe_1.teilaufgabe.erwartungshorizont"]
    assert not completeness["aufgaben.vollstaendig"]


def test_corpus_spreads_across_versorgungsbereiche_and_altersgruppen() -> None:
    """Deliberate spread, per tech doc 7.1. Gathered across every Aufgabe block
    in the corpus, since that is the granularity a Fallsituation theme actually
    exists at now, not the whole-item level."""
    blocks = [block for item in ITEM_PATHS for block in load(item).aufgaben]
    bereiche = {b.fallsituation.versorgungsbereich for b in blocks}
    altersgruppen = {b.fallsituation.altersgruppe for b in blocks}
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


def test_claimed_curriculare_einheiten_are_well_formed() -> None:
    """Well-formed CE references, now claimed per Teilaufgabe
    (schema change 2026-09-11) rather than per Aufgabe block as ce_bezug."""
    import re

    for path in ITEM_PATHS:
        for teilaufgabe in load(path).alle_teilaufgaben():
            for ce in teilaufgabe.situationsmerkmale.curriculare_einheit:
                assert re.fullmatch(r"CE \d{2}", ce), f"{path.stem}: {ce}"


def test_derived_competency_codes_are_well_formed() -> None:
    """Well-formed, not necessarily valid: C-03 deliberately derives an
    Anlage-1-only code so KOMP-06 has something to find."""
    import re

    for path in ITEM_PATHS:
        for teilaufgabe in load(path).alle_teilaufgaben():
            for code in teilaufgabe.kompetenzzuordnung_abgeleitet:
                assert re.fullmatch(r"[IVX]{1,3}\.\d{1,2}\.[a-z]", code), f"{path.stem}: {code}"


def test_the_deliberate_komp_06_defect_is_present() -> None:
    """If this stops being a defect, C-03 has silently become a clean item.

    Pooled across both Aufgabe blocks: I.2.g must stay the only Anlage-1-only
    code in the item even after Aufgabe 2 contributes its own derived codes."""
    from checks.catalogue import load_anlage_1_codes, load_anlage_2_codes

    derived = {c for t in load(ITEMS_DIR / "C-03.json").alle_teilaufgaben() for c in t.kompetenzzuordnung_abgeleitet}
    anlage_1_only = derived & (load_anlage_1_codes() - load_anlage_2_codes())
    assert anlage_1_only == {"I.2.g"}


def test_komp_03b_demonstration_item_still_covers_exactly_one_of_four() -> None:
    """C-03 is the KOMP-03B demonstration (rules/kompetenz.yaml, tests/test_checks_komp_03.py):
    it must keep covering exactly 1 of Pruefungsbereich 3's 4 Kompetenzschwerpunkte after
    pooling both Aufgabe blocks, or the "1 von 4" assertions elsewhere silently go stale."""
    from checks.catalogue import load_pruefungsbereiche
    from checks.deterministic.komp_03 import derived_schwerpunkte

    aufgabe = load(ITEMS_DIR / "C-03.json")
    required = set(load_pruefungsbereiche()[3]["kompetenzschwerpunkte"])
    covered = derived_schwerpunkte(aufgabe) & required
    assert covered == {"I.3"}


def test_manifest_covers_every_item() -> None:
    manifest = json.loads((ITEMS_DIR / "manifest.json").read_text(encoding="utf-8"))
    listed = {i for s in manifest["sets"] for i in s["items"]}
    assert listed == {p.stem for p in ITEM_PATHS}
