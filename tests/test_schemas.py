"""The output contract and the catalogue schema.

These test the guardrails, not the happy path: each one corresponds to a
non-negotiable that is easy to erode later (tech doc 9).
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from schemas.aufgabe import Aufsichtsarbeit, Fallsituation
from schemas.flag import CheckResult, Evidence, Flag, NotChecked
from schemas.rule import Rule, RuleSet

EVIDENCE = Evidence(rule_quote="Die Aufsichtsarbeiten dauern jeweils 120 Minuten.", source="PflAPrV § 14 Abs. 3")


def flag(**overrides):
    payload = {
        "flag_id": "f_001",
        "rule_id": "FORM-02",
        "anchor": "ta.1",
        "severity": "hinweis",
        "mechanism": "deterministic",
        "finding": "Der Umfang passt nicht zur Bearbeitungszeit.",
        "evidence": EVIDENCE,
    }
    return Flag(**{**payload, **overrides})


# ---- no flag without evidence ------------------------------------------------


def test_flag_requires_evidence() -> None:
    with pytest.raises(ValidationError):
        Flag(
            flag_id="f", rule_id="R", anchor="ta.1", severity="hinweis",
            mechanism="llm", finding="etwas",
        )


def test_evidence_requires_a_quote_and_a_source() -> None:
    with pytest.raises(ValidationError):
        Evidence(rule_quote="", source="PflAPrV § 14")
    with pytest.raises(ValidationError):
        Evidence(rule_quote="Text", source="")


def test_confidence_cannot_be_set() -> None:
    """Deliberately omitted: a model-generated number would be unfounded and
    reviewers would over-trust it (tech doc 4.2)."""
    with pytest.raises(ValidationError):
        flag(confidence=0.87)


# ---- tone --------------------------------------------------------------------


@pytest.mark.parametrize(
    "finding",
    [
        "Die Punkte der Teilaufgaben ergeben 40, angegeben sind 45.",
        "Die Pflegekraft soll die Beobachtung notieren.",
        "Die Schmerzkontrolle ist unzureichend dokumentiert.",
    ],
)
def test_factual_findings_are_accepted(finding: str) -> None:
    assert flag(finding=finding).finding == finding


def test_findings_are_not_word_filtered() -> None:
    """The advisory register is the prompt's job, not the schema's. A
    blocklist validator here used to reject a correct FORM-07 finding because
    "Bewertung" is also the honest name for what the operator "bewerten"
    demands -- see schemas/flag.py's comment on ``Flag``."""
    finding = "Der Erwartungshorizont bildet die vom Operator 'bewerten' verlangte Bewertung nicht ab."
    assert flag(finding=finding).finding == finding


# ---- not-checked and results -------------------------------------------------


def test_not_checked_requires_a_reason() -> None:
    """Silent skipping is a bug (tech doc 9)."""
    with pytest.raises(ValidationError):
        NotChecked(rule_id="FORM-07", reason="")
    entry = NotChecked(
        rule_id="FORM-07",
        reason="nicht pruefbar: Erwartungshorizont fehlt noch",
        missing=["teilaufgabe.erwartungshorizont"],
    )
    assert entry.missing == ["teilaufgabe.erwartungshorizont"]


def test_check_result_reports_mechanism_split() -> None:
    result = CheckResult(
        aufgabe_id="A-01",
        flags=[flag(), flag(flag_id="f_002", mechanism="llm", rule_id="FORM-07")],
        not_checked=[NotChecked(rule_id="QUELL-01", reason="Quelle nicht im Korpus")],
    )
    assert result.coverage == {
        "flags": 2, "rules_not_checked": 1, "deterministic_flags": 1, "llm_flags": 1,
    }
    assert len(result.by_severity("hinweis")) == 2


# ---- catalogue schema --------------------------------------------------------


def rule_payload(**overrides) -> dict:
    payload = {
        "id": "TEST-01",
        "family": "A",
        "title": "Testregel",
        "rule_text": "Eine Regel.",
        "source": {"document": "PflAPrV", "locator": "§ 14 Abs. 3", "quote": "Zitat"},
        "authority": "binding_federal",
        "check_type": "deterministic",
        "scope": "teilaufgabe",
        "input_slice": ["teilaufgabe.text"],
        "requires": ["teilaufgabe.text"],
        "severity_default": "blocker",
        "mutation": {"id": "MUT-TEST-01", "operation": "op", "description": "d"},
        "suggestion_template": ["Etwas tun."],
    }
    return {**payload, **overrides}


def test_rule_requires_a_mutation() -> None:
    """A rule without a mutation is not testable and does not ship."""
    payload = rule_payload()
    del payload["mutation"]
    with pytest.raises(ValidationError):
        Rule.model_validate(payload)


def test_blocker_severity_needs_binding_federal_authority() -> None:
    with pytest.raises(ValidationError, match="exceeds what"):
        Rule.model_validate(rule_payload(authority="third_party_advisory"))


def test_construction_principle_can_reach_pruefen_but_not_blocker() -> None:
    Rule.model_validate(rule_payload(authority="construction_principle", severity_default="pruefen"))
    with pytest.raises(ValidationError):
        Rule.model_validate(rule_payload(authority="construction_principle"))


def test_requires_outside_input_slice_is_rejected() -> None:
    with pytest.raises(ValidationError, match="not covered by input_slice"):
        Rule.model_validate(rule_payload(requires=["fallsituation.text"]))


def test_family_a_rule_needs_a_suggestion() -> None:
    with pytest.raises(ValidationError, match="must offer at least one suggestion"):
        Rule.model_validate(rule_payload(suggestion_template=[]))


def test_rule_without_quote_must_declare_what_blocks_it() -> None:
    payload = rule_payload(family="C", scope="erwartungshorizont", suggestion_template=[])
    payload["source"] = {"document": "DNQP", "locator": "Kriterien"}
    with pytest.raises(ValidationError, match="source.quote is required"):
        Rule.model_validate(payload)
    blocked = Rule.model_validate({**payload, "blocked_on": "corpus source not acquired"})
    assert not blocked.runnable


def test_ruleset_rejects_duplicate_ids() -> None:
    with pytest.raises(ValidationError, match="duplicate rule ids"):
        RuleSet.model_validate({"rules": [rule_payload(), rule_payload()]})


def test_ruleset_rejects_duplicate_mutation_ids() -> None:
    second = rule_payload(id="TEST-02")
    with pytest.raises(ValidationError, match="duplicate mutation ids"):
        RuleSet.model_validate({"rules": [rule_payload(), second]})


# ---- anchoring ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Frau K. ist 82. Sie stuerzt nachts. Sie hat Angst.", 3),
        ("Herr M. nimmt z. B. Marcumar ein. Es sind ca. 3 Haematome sichtbar.", 2),
        ("Die Bewohnerin ist immobil.", 1),
        ("", 0),
    ],
)
def test_sentence_anchoring_survives_abbreviations(text: str, expected: int) -> None:
    """Abbreviated surnames and "z. B." saturate this domain, and every false
    sentence boundary shifts the anchors after it (tech doc 7.3)."""
    assert len(Fallsituation(text=text).saetze()) == expected


def test_ids_identify_position_not_text() -> None:
    """The author rewrites the text; the ID still points at the same element."""
    aufgabe = Aufsichtsarbeit.model_validate(
        {"aufgaben": [{"teilaufgaben": [{"text": "Nennen Sie 3 Massnahmen."}, {"text": "Begruenden Sie 2 Schritte."}]}]}
    )
    assert aufgabe.resolve("ag.1.ta.2").text == "Begruenden Sie 2 Schritte."
    aufgabe.aufgaben[0].teilaufgaben[1].text = "Voellig anderer Text."
    assert aufgabe.resolve("ag.1.ta.2").text == "Voellig anderer Text."


def test_ids_nest_under_the_correct_aufgabe_block() -> None:
    """ag.1.ta.1 and ag.2.ta.1 are different Teilaufgaben: the block a Teilaufgabe
    sits in is part of its identity, not just its position within that block."""
    aufgabe = Aufsichtsarbeit.model_validate(
        {
            "aufgaben": [
                {"teilaufgaben": [{"text": "Aufgabe 1, Teilaufgabe 1"}]},
                {"teilaufgaben": [{"text": "Aufgabe 2, Teilaufgabe 1"}]},
            ]
        }
    )
    assert aufgabe.resolve("ag.1.ta.1").text == "Aufgabe 1, Teilaufgabe 1"
    assert aufgabe.resolve("ag.2.ta.1").text == "Aufgabe 2, Teilaufgabe 1"


def test_unknown_anchors_resolve_to_none_rather_than_raising() -> None:
    aufgabe = Aufsichtsarbeit.model_validate({"aufgaben": [{"teilaufgaben": [{"text": "x"}]}]})
    for anchor in ("ag.9", "ag.1.ta.9", "ag.1.ta.1.eh.4", "nonsense", "ag", "ag.x", "ag.1.ta.x"):
        assert aufgabe.resolve(anchor) is None
