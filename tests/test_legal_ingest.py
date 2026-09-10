"""Regression tests for the Anlage citation defect (repo review 4.1).

The defect these guard against was not a crash: it was a *plausible wrong
citation*.  Every Anlage 1 and Anlage 2 competency was cited as "§ 62", which
under the evidence rule (tech doc 4.1) is a fabricated citation and worse than
producing no flag.  A silent regression here would be invisible without tests.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from corpus.config import RAW_DIR
from corpus.ingest.kompetenzen import parse_anlage_kompetenzen
from corpus.ingest.legal import find_provision, read_legal_html

PFLAPRV = RAW_DIR / "PflAPrV.html"

pytestmark = pytest.mark.skipif(
    not PFLAPRV.exists(), reason="PflAPrV.html not present; run scripts/download_legal_sources.py"
)


@pytest.fixture(scope="module")
def provisions():
    return read_legal_html(PFLAPRV)


def test_anlagen_are_first_class_units(provisions) -> None:
    anlagen = [p for p in provisions if p.is_anlage]
    assert len(anlagen) == 15
    assert all(p.unit_number for p in anlagen)


def test_anlage_1_and_2_are_distinguishable(provisions) -> None:
    """The whole point of the fix: these were indistinguishable in phase 1."""
    anlage_1 = find_provision(provisions, "Anlage 1")
    anlage_2 = find_provision(provisions, "Anlage 2")
    assert anlage_1.locator != anlage_2.locator
    assert anlage_1.locator.startswith("Anlage 1")
    assert anlage_2.locator.startswith("Anlage 2")
    # Fundstelle page ranges were the only phase-1 difference; now they are read.
    assert anlage_1.fundstelle != anlage_2.fundstelle


def test_no_anlage_is_cited_as_a_paragraph(provisions) -> None:
    for provision in provisions:
        if provision.is_anlage:
            assert not provision.locator.startswith("§"), (
                f"Anlage {provision.unit_number} is cited as {provision.locator!r}"
            )


def test_anlage_2_locator_names_its_enabling_paragraph(provisions) -> None:
    anlage_2 = find_provision(provisions, "Anlage 2")
    # Anlage 2 is the competency catalogue for the staatliche Prüfung under § 9.
    assert anlage_2.locator == "Anlage 2 (zu § 9 Absatz 1 Satz 2)"


def test_kompetenz_codes_parse_to_the_lehrplan_code_form(provisions) -> None:
    anlage_2 = find_provision(provisions, "Anlage 2")
    records = parse_anlage_kompetenzen(anlage_2)
    codes = {r.code for r in records}
    # Codes the Bavarian Lehrplan cites, which Family B tags against.
    assert {"I.1.h", "II.3.a", "V.2.c"} <= codes
    assert all(r.anlage == "2" for r in records)
    assert all(r.text for r in records)


def test_anlage_2_competency_count_is_stable(provisions) -> None:
    """Pins the authoritative count KOMP-06 tests membership against.

    If PflAPrV is amended this test should fail loudly, because the KOMP-06
    code list is then stale.
    """
    records = parse_anlage_kompetenzen(find_provision(provisions, "Anlage 2"))
    assert len(records) == 85
    per_bereich = {}
    for record in records:
        per_bereich[record.kompetenzbereich] = per_bereich.get(record.kompetenzbereich, 0) + 1
    assert per_bereich == {"I": 33, "II": 14, "III": 18, "IV": 9, "V": 11}


def test_every_competency_carries_its_anlage_citation(provisions) -> None:
    """No flag without evidence: a competency must be able to cite itself."""
    for anlage_prefix in ("Anlage 1", "Anlage 2"):
        provision = find_provision(provisions, anlage_prefix)
        for record in parse_anlage_kompetenzen(provision):
            assert record.anlage_locator.startswith(anlage_prefix)
            assert record.fundstelle
            assert record.kompetenzbereich_titel
            assert record.schwerpunkt_titel


def test_non_competency_anlagen_yield_no_competencies(provisions) -> None:
    """Certificate templates must not be mined for competencies."""
    anlage_12 = find_provision(provisions, "Anlage 12 ")
    assert parse_anlage_kompetenzen(anlage_12) == []
