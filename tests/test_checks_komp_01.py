"""KOMP-01: candidate-set construction and the derivation/flag logic, all
against a fake classifier -- no network call in this test module.
"""
from __future__ import annotations

from checks.catalogue import load_anlage_2_codes
from checks.llm.komp_01 import check_komp_01, derive_kompetenzzuordnung
from checks.llm.kompetenz_candidates import candidate_kompetenzen
from schemas.aufgabe import Aufsichtsarbeit, Teilaufgabe
from schemas.flag import Flag, NotChecked

# ---- candidate_kompetenzen ----------------------------------------------


def test_no_ce_falls_back_to_the_full_anlage_2_set() -> None:
    assert set(candidate_kompetenzen([])) == load_anlage_2_codes()


def test_ce_with_real_anlage_2_mapping_returns_its_codes() -> None:
    candidates = candidate_kompetenzen(["CE 04"])
    assert candidates
    assert set(candidates) <= load_anlage_2_codes()


def test_ce_whose_anlage_2_mapping_is_genuinely_empty_stays_empty() -> None:
    """CE 01/02/03 are 1st/2nd-Ausbildungsdrittel units with no
    staatliche-Pruefungs-relevant competency at all. This must NOT fall back
    to the full set -- that would mask a real, informative answer."""
    assert candidate_kompetenzen(["CE 01"]) == []


def test_unknown_ce_contributes_nothing_but_does_not_crash() -> None:
    assert candidate_kompetenzen(["CE 99"]) == []


def test_multiple_ce_union_their_candidates() -> None:
    only_04 = set(candidate_kompetenzen(["CE 04"]))
    combined = set(candidate_kompetenzen(["CE 01", "CE 04"]))
    assert combined == only_04, "CE 01 contributes nothing, so the union must equal CE 04 alone"


# ---- derive_kompetenzzuordnung -------------------------------------------


def test_derive_filters_classifier_output_to_the_candidate_set() -> None:
    """Defense in depth: even if the classifier returns something outside
    the candidates it was given, derive_kompetenzzuordnung must not pass it through."""
    teilaufgabe = Teilaufgabe(text="x", situationsmerkmale={"curriculare_einheit": ["CE 04"]})

    def rogue_classify(text, candidates, *, kompetenz_text, fallsituation_text=None):
        return [*candidates[:1], "ZZ.9.z"]

    result = derive_kompetenzzuordnung(teilaufgabe, classify=rogue_classify)
    assert result == candidates_of(teilaufgabe)[:1]


def test_derive_passes_fallsituation_text_through_to_classify() -> None:
    """The owning Aufgabe block's Fallsituation is context the classifier
    needs -- a Teilaufgabe's own text often only makes sense read against
    it -- so it must reach ``classify``, not get dropped along the way."""
    teilaufgabe = Teilaufgabe(text="x", situationsmerkmale={"curriculare_einheit": ["CE 04"]})
    seen = {}

    def classify(text, candidates, *, kompetenz_text, fallsituation_text=None):
        seen["fallsituation_text"] = fallsituation_text
        return []

    derive_kompetenzzuordnung(teilaufgabe, classify=classify, fallsituation_text="Frau K. ist 82 Jahre alt.")
    assert seen["fallsituation_text"] == "Frau K. ist 82 Jahre alt."


def test_derive_defaults_fallsituation_text_to_none() -> None:
    """A draft may not have a Fallsituation written yet -- that must not
    become a required argument."""
    teilaufgabe = Teilaufgabe(text="x", situationsmerkmale={"curriculare_einheit": ["CE 04"]})
    seen = {}

    def classify(text, candidates, *, kompetenz_text, fallsituation_text=None):
        seen["fallsituation_text"] = fallsituation_text
        return []

    derive_kompetenzzuordnung(teilaufgabe, classify=classify)
    assert seen["fallsituation_text"] is None


def candidates_of(teilaufgabe: Teilaufgabe) -> list[str]:
    return candidate_kompetenzen(teilaufgabe.situationsmerkmale.curriculare_einheit)


def test_derive_returns_empty_without_calling_classify_when_candidates_are_empty() -> None:
    teilaufgabe = Teilaufgabe(text="x", situationsmerkmale={"curriculare_einheit": ["CE 01"]})
    calls = []

    def classify(*args, **kwargs):
        calls.append(1)
        return []

    assert derive_kompetenzzuordnung(teilaufgabe, classify=classify) == []
    assert not calls, "no candidates means nothing to classify -- the call itself is skippable"


# ---- check_komp_01 --------------------------------------------------------


def _fake_classify(text, candidates, *, kompetenz_text, fallsituation_text=None):
    return [candidates[0]] if candidates else []


def test_fires_when_derived_set_is_empty() -> None:
    aufgabe = Aufsichtsarbeit.model_validate(
        {
            "aufgaben": [
                {
                    "fallsituation": {"text": "Frau Ostermann ist 82 Jahre alt."},
                    "teilaufgaben": [{"text": "x", "situationsmerkmale": {"curriculare_einheit": ["CE 01"]}}],
                }
            ]
        }
    )
    results = check_komp_01(aufgabe, classify=_fake_classify)
    assert len(results) == 1
    assert isinstance(results[0], Flag)
    assert results[0].rule_id == "KOMP-01"
    assert results[0].anchor == "ag.1.ta.1"


def test_does_not_fire_when_something_is_derived() -> None:
    aufgabe = Aufsichtsarbeit.model_validate(
        {
            "aufgaben": [
                {
                    "fallsituation": {"text": "Frau Ostermann ist 82 Jahre alt."},
                    "teilaufgaben": [{"text": "x", "situationsmerkmale": {"curriculare_einheit": ["CE 04"]}}],
                }
            ]
        }
    )
    results = check_komp_01(aufgabe, classify=_fake_classify)
    assert results == []


def test_missing_text_is_not_checked_not_flagged() -> None:
    aufgabe = Aufsichtsarbeit.model_validate({"aufgaben": [{"teilaufgaben": [{}]}]})
    results = check_komp_01(aufgabe, classify=_fake_classify)
    assert len(results) == 1
    assert isinstance(results[0], NotChecked)
    assert "teilaufgabe.text" in results[0].missing


def test_missing_fallsituation_text_is_not_checked_not_flagged() -> None:
    """Fallsituation text is now a hard precondition, gated the same way as
    a missing Teilaufgabentext -- a derivation without it is not run at all,
    not run on text alone."""
    aufgabe = Aufsichtsarbeit.model_validate(
        {"aufgaben": [{"teilaufgaben": [{"text": "x", "situationsmerkmale": {"curriculare_einheit": ["CE 04"]}}]}]}
    )
    calls = []

    def classify(*args, **kwargs):
        calls.append(1)
        return []

    results = check_komp_01(aufgabe, classify=classify)
    assert len(results) == 1
    assert isinstance(results[0], NotChecked)
    assert "aufgabe.aufgaben[].fallsituation.text" in results[0].missing
    assert not calls, "the classifier must never be called without a Fallsituation"


def test_derived_field_is_written_onto_the_artifact() -> None:
    aufgabe = Aufsichtsarbeit.model_validate(
        {
            "aufgaben": [
                {
                    "fallsituation": {"text": "Frau Ostermann ist 82 Jahre alt."},
                    "teilaufgaben": [{"text": "x", "situationsmerkmale": {"curriculare_einheit": ["CE 04"]}}],
                }
            ]
        }
    )
    check_komp_01(aufgabe, classify=_fake_classify)
    derived = aufgabe.aufgaben[0].teilaufgaben[0].kompetenzzuordnung_abgeleitet
    assert derived and derived[0] in candidate_kompetenzen(["CE 04"])


def test_check_komp_01_passes_the_blocks_fallsituation_text_to_classify() -> None:
    aufgabe = Aufsichtsarbeit.model_validate(
        {
            "aufgaben": [
                {
                    "fallsituation": {"text": "Frau Ostermann ist 82 Jahre alt."},
                    "teilaufgaben": [{"text": "x", "situationsmerkmale": {"curriculare_einheit": ["CE 04"]}}],
                }
            ]
        }
    )
    seen = []

    def classify(text, candidates, *, kompetenz_text, fallsituation_text=None):
        seen.append(fallsituation_text)
        return [candidates[0]] if candidates else []

    check_komp_01(aufgabe, classify=classify)
    assert seen == ["Frau Ostermann ist 82 Jahre alt."]
