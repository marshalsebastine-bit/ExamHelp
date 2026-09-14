"""FORM-03, FORM-04, FORM-11, FORM-13: the four Family A rules that all turn
on the same question -- which catalogue operator, if any, does a
Teilaufgabe's text actually use. Grouped for that shared extraction step.

**Extraction, not lookup.** rules/operators.yaml lists each operator's
infinitive ("ableiten") and a stylised `task_formulation` ("Leiten Sie ...
ab"), but the formulation field is inconsistent about where a separable
verb's particle sits (compare "Zaehlen Sie auf ..." in the YAML with the
same operator's own example_task, "Zaehlen Sie 3 ... auf" -- particle at the
end). Matching against `task_formulation` literally would miss real usage.
Instead: German's formal imperative is *always* "Infinitiv + Sie" with no
exception, so the lead phrase is derived from the operator's own root
(stripping a separable prefix via `_SEPARABLE`, hand-verified against all
27 operators rather than guessed from a generic prefix list -- a naive
prefix strip misreads "zusammenfassen" as prefix "zu" + "sammenfassen",
which is wrong). A separable verb only counts as a match when its particle
also appears somewhere after the lead phrase; the lead alone (e.g. "Stellen
Sie") is too generic a German verb to attribute to one catalogue operator
without it, and the particle is what real usage always includes eventually
("Stellen Sie ... gegenueber").

**Zero matches vs. an unlisted operator.** FORM-03 asks "is the operator on
the list" -- if extraction finds nothing at all, there is no operator to
judge against the list, so this is NotChecked, not a flag (confirmed
against items/manifest.json's C-01 fixture: ag.1.ta.2's nominalised
"Es sollte eine Beschreibung ... erfolgen" has no operator at all and is a
FORM-11 defect, explicitly *not* a FORM-03 one). FORM-04 and FORM-13 read
the same way. FORM-11 is the one rule where zero is itself the violation:
"genau ein Operator" fails on zero exactly as it fails on two.
"""
from __future__ import annotations

import re

from checks.catalogue import load_operator_explanations, load_operators, rule
from checks.deterministic._german_text import flex, flex_word
from schemas.aufgabe import Aufsichtsarbeit
from schemas.flag import Evidence, Flag, NotChecked

# Hand-verified against every operator in rules/operators.yaml: operator ->
# (root the imperative is built from, its trailing separable particle).
_SEPARABLE: dict[str, tuple[str, str]] = {
    "aufzählen": ("zählen", "auf"),
    "einordnen": ("ordnen", "ein"),
    "zuordnen": ("ordnen", "zu"),
    "ableiten": ("leiten", "ab"),
    "gegenüberstellen": ("stellen", "gegenüber"),
    "zusammenfassen": ("fassen", "zusammen"),
}
# "stellung nehmen" is a Funktionsverbgefuege (verb + fixed object), not a
# separable-prefix verb: its lead is "Nehmen Sie", with no trailing particle
# to require.
_SPECIAL_LEAD: dict[str, str] = {"stellung nehmen": "nehmen"}


def _lead_and_particle(operator: str) -> tuple[str, str | None]:
    if operator in _SPECIAL_LEAD:
        return _SPECIAL_LEAD[operator], None
    if operator in _SEPARABLE:
        root, particle = _SEPARABLE[operator]
        return root, particle
    return operator, None


def find_operator_matches(text: str | None) -> list[dict]:
    """Every catalogue operator whose imperative form appears in `text`,
    ordered by first appearance. Each match is
    {"operator": str, "start": int, "end": int} (end of the lead phrase,
    for an "is it at the very start of the text" check)."""
    if not text:
        return []
    matches: list[dict] = []
    for operator in load_operators():
        root, particle = _lead_and_particle(operator)
        lead_re = re.compile(rf"\b{flex(root)}\s+[Ss]ie\b", re.IGNORECASE)
        for m in lead_re.finditer(text):
            if particle and not flex_word(particle).search(text[m.end():]):
                continue
            matches.append({"operator": operator, "start": m.start(), "end": m.end()})
    matches.sort(key=lambda m: m["start"])
    return matches


def _distinct_operators(matches: list[dict]) -> list[str]:
    seen: list[str] = []
    for m in matches:
        if m["operator"] not in seen:
            seen.append(m["operator"])
    return seen


# FORM-03 needs something find_operator_matches() cannot give it: the verb
# actually used, even when it is not a catalogue operator at all ("Erfinden
# Sie ..."). find_operator_matches() only ever recognises known operators,
# so it returns nothing for an unlisted verb -- indistinguishable from "no
# operator at all". A second, more permissive extraction captures whichever
# word leads the sentence as "<Word> Sie", known or not, so an unlisted verb
# has a name to flag rather than just failing to be found.
_LEADING_VERB = re.compile(r"^\s*([A-ZÄÖÜ][A-Za-zÄÖÜäöüß]*)\s+[Ss]ie\b")


def _normalize(word: str) -> str:
    """Casefold plus ae/oe/ue/ss -> ä/ö/ü/ß normalisation, so a leading verb
    extracted verbatim from (possibly transliterated) text compares equal
    to a root written with literal umlauts in `_SEPARABLE`."""
    word = word.casefold()
    for umlaut, digraph in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        word = word.replace(umlaut, digraph)
    return word


def _leading_verb(text: str) -> str | None:
    match = _LEADING_VERB.match(text)
    return match.group(1) if match else None


def _known_roots() -> frozenset[str]:
    roots = {_normalize(_lead_and_particle(op)[0]) for op in load_operators()}
    return frozenset(roots)


def check_form_03(aufgabe: Aufsichtsarbeit) -> list[Flag | NotChecked]:
    """Zero leading-verb match (e.g. C-01's nominalised 'Es sollte eine
    Beschreibung ... erfolgen') is NotChecked, not a flag: there is no verb
    here to judge against the list at all. That case is FORM-11's to catch.

    Known limitation, accepted rather than engineered around: an unlisted
    leading verb also makes find_operator_matches() return nothing, so
    FORM-11 (built on that function) reads it as "no operator" too, even
    though syntactically there is exactly one, just not an approved one.
    No fixture in items/*.json exercises this overlap, so it is recorded
    here rather than fixed blind.
    """
    form03 = rule("FORM-03")
    known = _known_roots()
    results: list[Flag | NotChecked] = []

    for ai, block in enumerate(aufgabe.aufgaben):
        for ti, teilaufgabe in enumerate(block.teilaufgaben):
            anchor = aufgabe.teilaufgabe_id(ai, ti)
            if not teilaufgabe.text:
                results.append(
                    NotChecked(rule_id="FORM-03", reason="Teilaufgabentext fehlt", missing=["teilaufgabe.text"], anchor=anchor)
                )
                continue

            leading = _leading_verb(teilaufgabe.text)
            if leading is None:
                results.append(
                    NotChecked(
                        rule_id="FORM-03",
                        reason="kein Verb-Sie-Muster am Satzanfang erkannt",
                        missing=["teilaufgabe.text"],
                        anchor=anchor,
                    )
                )
                continue

            if _normalize(leading) in known:
                continue

            results.append(
                Flag(
                    flag_id=f"form03-{anchor}",
                    rule_id="FORM-03",
                    anchor=anchor,
                    severity=form03.severity_default,
                    mechanism="deterministic",
                    finding=f"Der verwendete Operator {leading!r} steht nicht auf der Operatorenliste.",
                    evidence=Evidence(rule_quote=form03.source.quote, source=f"{form03.source.document}, {form03.source.locator}"),
                    suggestions=list(form03.suggestion_template),
                )
            )

    return results


def check_form_04(aufgabe: Aufsichtsarbeit) -> list[Flag | NotChecked]:
    form04 = rule("FORM-04")
    operators = load_operators()
    results: list[Flag | NotChecked] = []

    for ai, block in enumerate(aufgabe.aufgaben):
        for ti, teilaufgabe in enumerate(block.teilaufgaben):
            anchor = aufgabe.teilaufgabe_id(ai, ti)
            if not teilaufgabe.text or not teilaufgabe.anforderungsniveau:
                missing = []
                if not teilaufgabe.text:
                    missing.append("teilaufgabe.text")
                if not teilaufgabe.anforderungsniveau:
                    missing.append("teilaufgabe.anforderungsniveau")
                results.append(NotChecked(rule_id="FORM-04", reason="Praeambel unvollstaendig", missing=missing, anchor=anchor))
                continue

            distinct = _distinct_operators(find_operator_matches(teilaufgabe.text))
            if not distinct:
                results.append(
                    NotChecked(
                        rule_id="FORM-04",
                        reason="kein Operator aus der Liste erkannt, Niveauabgleich nicht moeglich",
                        missing=["teilaufgabe.text"],
                        anchor=anchor,
                    )
                )
                continue

            niveau = teilaufgabe.anforderungsniveau
            niveau_value = niveau.value if hasattr(niveau, "value") else niveau
            erlaubte_niveaus = {level for op in distinct for level in operators[op]}
            if niveau_value in erlaubte_niveaus:
                continue

            results.append(
                Flag(
                    flag_id=f"form04-{anchor}",
                    rule_id="FORM-04",
                    anchor=anchor,
                    severity=form04.severity_default,
                    mechanism="deterministic",
                    finding=(
                        f"Operator {', '.join(distinct)} traegt Anforderungsbereich(e) "
                        f"{', '.join(sorted(erlaubte_niveaus))}, die Teilaufgabe deklariert "
                        f"Anforderungsniveau {niveau_value}."
                    ),
                    evidence=Evidence(rule_quote=form04.source.quote, source=f"{form04.source.document}, {form04.source.locator}"),
                    suggestions=list(form04.suggestion_template),
                )
            )

    return results


def check_form_11(aufgabe: Aufsichtsarbeit) -> list[Flag | NotChecked]:
    form11 = rule("FORM-11")
    results: list[Flag | NotChecked] = []

    for ai, block in enumerate(aufgabe.aufgaben):
        for ti, teilaufgabe in enumerate(block.teilaufgaben):
            anchor = aufgabe.teilaufgabe_id(ai, ti)
            if not teilaufgabe.text:
                results.append(NotChecked(rule_id="FORM-11", reason="Teilaufgabentext fehlt", missing=["teilaufgabe.text"], anchor=anchor))
                continue

            matches = find_operator_matches(teilaufgabe.text)
            distinct = _distinct_operators(matches)

            if len(distinct) == 1 and matches[0]["start"] == 0:
                continue

            if not distinct:
                finding = "Die Teilaufgabe enthaelt keinen erkennbaren Operator."
            elif len(distinct) > 1:
                finding = f"Die Teilaufgabe enthaelt mehr als einen Operator: {', '.join(distinct)}."
            else:
                finding = f"Der Operator {distinct[0]!r} steht nicht am Satzanfang."

            results.append(
                Flag(
                    flag_id=f"form11-{anchor}",
                    rule_id="FORM-11",
                    anchor=anchor,
                    severity=form11.severity_default,
                    mechanism="deterministic",
                    finding=finding,
                    evidence=Evidence(rule_quote=form11.source.quote, source=f"{form11.source.document}, {form11.source.locator}"),
                    suggestions=list(form11.suggestion_template),
                )
            )

    return results


def _is_enumerierend(operator: str) -> bool:
    """'Stichpunkte'-type operators (nennen, aufzaehlen, benennen,
    bezeichnen) are the ones whose explanation in operators.yaml says
    "Informationen in Form von Stichpunkten schreiben" -- i.e. a bare
    listing, which is what "Aufzaehlung" in FORM-13's rule_text means.
    Derived from the catalogue's own explanation text rather than a
    hardcoded operator-name list, so a future addition to operators.yaml
    is picked up without a code change."""
    explanation = load_operator_explanations().get(operator, "")
    # Word-start boundary only: the YAML text inflects to "Stichpunkten"
    # (dative plural), so a full \b...\b match on "Stichpunkte" would miss it.
    return bool(re.search(rf"\b{flex('Stichpunkt')}", explanation, re.IGNORECASE))


_DIGIT = re.compile(r"\d")


def check_form_13(aufgabe: Aufsichtsarbeit) -> list[Flag | NotChecked]:
    form13 = rule("FORM-13")
    results: list[Flag | NotChecked] = []

    for ai, block in enumerate(aufgabe.aufgaben):
        for ti, teilaufgabe in enumerate(block.teilaufgaben):
            anchor = aufgabe.teilaufgabe_id(ai, ti)
            if not teilaufgabe.text:
                results.append(NotChecked(rule_id="FORM-13", reason="Teilaufgabentext fehlt", missing=["teilaufgabe.text"], anchor=anchor))
                continue

            distinct = _distinct_operators(find_operator_matches(teilaufgabe.text))
            if not distinct:
                results.append(
                    NotChecked(
                        rule_id="FORM-13",
                        reason="kein Operator aus der Liste erkannt, Aufzaehlungscharakter nicht feststellbar",
                        missing=["teilaufgabe.text"],
                        anchor=anchor,
                    )
                )
                continue

            if not any(_is_enumerierend(op) for op in distinct):
                continue  # not an enumerating operator: FORM-13 does not apply
            if _DIGIT.search(teilaufgabe.text):
                continue

            results.append(
                Flag(
                    flag_id=f"form13-{anchor}",
                    rule_id="FORM-13",
                    anchor=anchor,
                    severity=form13.severity_default,
                    mechanism="deterministic",
                    finding=(
                        f"Die Teilaufgabe verlangt mit dem Operator {', '.join(distinct)} eine "
                        "Aufzaehlung, nennt aber keine Anzahl der erwarteten Nennungen."
                    ),
                    evidence=Evidence(rule_quote=form13.source.quote, source=f"{form13.source.document}, {form13.source.locator}"),
                    suggestions=list(form13.suggestion_template),
                )
            )

    return results
