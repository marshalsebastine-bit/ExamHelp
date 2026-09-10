"""Catalogue integrity tests.

These enforce the non-negotiables from tech doc 9 as tests rather than as
prose, because every one of them is easy to erode under time pressure.
"""
from __future__ import annotations

import pytest

from checks.catalogue import (
    load_anlage_1_codes,
    load_anlage_2_codes,
    load_kompetenzen,
    load_operators,
    load_pruefungsbereiche,
    load_ruleset,
    load_situationsmerkmale,
)
from schemas.rule import CheckType, Family


@pytest.fixture(scope="module")
def ruleset():
    return load_ruleset()


def test_catalogue_loads_and_ids_are_unique(ruleset) -> None:
    assert ruleset.counts["total"] >= 20
    assert len({r.id for r in ruleset.rules}) == len(ruleset.rules)


def test_every_rule_ships_with_a_mutation(ruleset) -> None:
    """A rule without a mutation is not testable and does not ship (tech doc 3.3)."""
    for rule in ruleset.rules:
        assert rule.mutation.id, f"{rule.id} has no mutation id"
        assert rule.mutation.operation, f"{rule.id} has no mutation operation"
        assert rule.mutation.description.strip(), f"{rule.id} has no mutation description"


def test_mutation_ids_are_unique(ruleset) -> None:
    ids = [r.mutation.id for r in ruleset.rules]
    assert len(set(ids)) == len(ids)


def test_every_rule_can_produce_evidence(ruleset) -> None:
    """No flag without evidence (tech doc 4.1).

    Family B's evidence is the competency text looked up at runtime, so those
    rules carry a locator but no static quote.  Every other rule must carry a
    quote, unless it is explicitly blocked on an unacquired source.
    """
    for rule in ruleset.rules:
        assert rule.source.document and rule.source.locator, f"{rule.id} cannot cite a source"
        if rule.family != Family.B and rule.runnable:
            assert rule.source.quote, f"{rule.id} has no quotable evidence"


def test_blocker_severity_only_for_binding_federal(ruleset) -> None:
    """Severity derives from source authority, not from a hand assignment."""
    for rule in ruleset.rules:
        if rule.severity_default.value == "blocker":
            assert rule.authority.value == "binding_federal", (
                f"{rule.id} claims blocker on authority {rule.authority.value}"
            )


def test_requires_is_covered_by_input_slice(ruleset) -> None:
    """A precondition on data the check never receives cannot be meaningful."""
    for rule in ruleset.rules:
        for path in rule.requires:
            assert any(
                path == s or path.startswith(f"{s}.") or s.startswith(f"{path}.")
                for s in rule.input_slice
            ), f"{rule.id}: requires {path} not in input_slice"


def test_family_a_rules_offer_suggestions(ruleset) -> None:
    """For the author, suggestions carry most of the value (tech doc 1.5.2)."""
    for rule in ruleset.by_family(Family.A):
        assert rule.suggestion_template, f"{rule.id} offers no suggestion"


def test_majority_of_checks_need_no_model(ruleset) -> None:
    """'Half the checks require no model at all' is a credibility line the
    catalogue has to actually support (tech doc 3.4)."""
    deterministic = sum(1 for r in ruleset.rules if r.check_type == CheckType.deterministic)
    assert deterministic / len(ruleset.rules) >= 0.4


def test_blocked_rules_are_excluded_from_the_runnable_set(ruleset) -> None:
    blocked = {r.id for r in ruleset.rules if not r.runnable}
    assert all(r.blocked_on for r in ruleset.rules if r.id in blocked)
    assert blocked.isdisjoint({r.id for r in ruleset.runnable})


# ---- lookup tables -----------------------------------------------------------


def test_operator_lookup_answers_the_negative_case() -> None:
    """The whole reason the operator table is a dict and not a vector index."""
    operators = load_operators()
    assert "nennen" in operators
    assert "erfinden" not in operators
    assert "ueberlegen" not in operators


def test_grouped_operator_row_is_individually_addressable() -> None:
    """The source lists "entwickeln, planen, ableiten" as one row; a lookup for
    "planen" must still succeed or FORM-03 raises a false flag."""
    operators = load_operators()
    for name in ("entwickeln", "planen", "ableiten"):
        assert name in operators, f"{name} is not individually addressable"


def test_operator_may_carry_more_than_one_level() -> None:
    assert sorted(load_operators()["ableiten"]) == ["II", "III"]


def test_komp_06_uses_the_authoritative_anlage_2_list() -> None:
    """Built on the Lehrplan's citations this check would false-flag six real
    Anlage 2 competencies (tech doc 12 verification item)."""
    anlage_2 = load_anlage_2_codes()
    assert len(anlage_2) == 85
    # The six the Lehrplan never cites at the Anlage-2 level, including I.1.h,
    # which tech doc 3.3.1 uses as its own worked example.
    for code in ("I.1.a", "I.1.f", "I.1.h", "I.1.i", "I.2.d", "I.2.f"):
        assert code in anlage_2, f"{code} missing: KOMP-06 would false-flag it"


def test_anlage_1_and_anlage_2_are_distinct_sets() -> None:
    """KOMP-06 exists precisely because these differ."""
    anlage_1, anlage_2 = load_anlage_1_codes(), load_anlage_2_codes()
    assert anlage_1 != anlage_2
    assert anlage_1 - anlage_2, "no Anlage-1-only code exists, so KOMP-06 could never fire"


def test_lehrplan_citations_are_a_subset_of_pflaprv() -> None:
    """Records the cross-check result: the Lehrplan invents no code."""
    cross_check = load_kompetenzen()["meta"]["cross_check"]["anlage_2"]
    assert cross_check["cited_by_lehrplan_but_absent_from_pflaprv"] == []
    assert len(cross_check["in_pflaprv_but_never_cited_by_lehrplan"]) == 6


def test_pruefungsbereiche_cover_the_three_written_areas() -> None:
    bereiche = load_pruefungsbereiche()
    assert set(bereiche) == {1, 2, 3}
    for entry in bereiche.values():
        assert entry["kompetenzschwerpunkte"], "KOMP-03 needs Schwerpunkte per Bereich"
        assert entry["quote"], "KOMP-03 needs a quotable § 14 (1) passage"


def test_situationsmerkmale_cover_all_eleven_ce() -> None:
    merkmale = load_situationsmerkmale()
    assert len(merkmale) == 11
    for ce, entry in merkmale.items():
        assert entry["handlungsanlaesse"], f"{ce} has no Handlungsanlaesse for KOMP-07"


def test_curriculare_einheiten_carry_zeitrichtwerte() -> None:
    einheiten = load_kompetenzen()["curriculare_einheiten"]
    assert len(einheiten) == 11
    assert all(e["zeitrichtwert_stunden"] > 0 for e in einheiten)
    # Eight CEs continue into the third Ausbildungsdrittel (tech doc 3.2.1).
    assert sum(1 for e in einheiten if e["im_dritten_ausbildungsdrittel"]) == 8
