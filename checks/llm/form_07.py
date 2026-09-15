"""FORM-07: flags a Teilaufgabe whose Erwartungshorizont bepunktet a
different performance than the one its operator actually demands.

The tool's most compelling single check (rules/form.yaml's own `notes`) --
this mismatch is common, consequential, and invisible to a checklist. It is
also the first judgement-type LLM check this project has built (KOMP-01 is a
code-selection prompt, not a judgement one): anchor granularity is simply the
Teilaufgabe itself, since both halves of the comparison -- the operator in
`teilaufgabe.text` and the points in `teilaufgabe.erwartungshorizont` -- live
at that same scope. No sentence-level anchor is needed here the way FORM-09/10
will need one into the Fallsituation.

**Only half of the comparison is a model judgement.** The Teilaufgabe's own
operator is extracted deterministically via
``checks/deterministic/form_operators.py::find_operator_matches`` -- the same
extraction FORM-03/04/11/13 already trust -- rather than asked of the model.
An earlier version asked the model to label *both* sides as free-form
keywords, and it visibly misread a Teilaufgabe opening with the explicit
operator "Beschreiben Sie" as "Aufzählung": a plain misread a keyword match
never gets wrong. The model is asked only the genuinely judgement-shaped
half: which catalogue operator best describes the performance the
Erwartungshorizont actually rewards. The two operators are then compared by
Anforderungsbereich (the same I/II/III levels FORM-04 already compares an
operator against), not by exact identity: two different operators that both
carry Anforderungsbereich I are not a FORM-07 violation, only operators whose
Anforderungsbereich sets share no level are.

``judge`` is injected the same way ``checks/llm/komp_01.py``'s ``classify``
is: production code passes ``gateway.model_gateway.judge_form_07``, tests
pass a fake. ``checks/runner.py`` follows the same "no model, no NotChecked
per Teilaufgabe" posture it already uses for KOMP-01 when the caller has no
judge to inject.
"""
from __future__ import annotations

from typing import Callable

from checks.catalogue import load_operator_explanations, load_operators, rule
from checks.deterministic.form_operators import _distinct_operators, find_operator_matches
from schemas.aufgabe import Aufsichtsarbeit, Erwartungshorizont
from schemas.flag import Evidence, Flag, NotChecked

Judge = Callable[..., str]


def _erwartungshorizont_text(erwartungshorizont: Erwartungshorizont) -> str:
    zeilen = [p.text for p in erwartungshorizont.erwartungspunkte if p.text]
    if erwartungshorizont.freitext:
        zeilen.append(erwartungshorizont.freitext)
    return "\n".join(zeilen)


def check_form_07(aufgabe: Aufsichtsarbeit, *, judge: Judge) -> list[Flag | NotChecked]:
    form07 = rule("FORM-07")
    operators = load_operators()
    explanations = load_operator_explanations()
    results: list[Flag | NotChecked] = []

    for ai, block in enumerate(aufgabe.aufgaben):
        for ti, teilaufgabe in enumerate(block.teilaufgaben):
            anchor = aufgabe.teilaufgabe_id(ai, ti)

            if not teilaufgabe.text:
                results.append(
                    NotChecked(
                        rule_id="FORM-07",
                        reason="Teilaufgabentext fehlt noch",
                        missing=["teilaufgabe.text"],
                        anchor=anchor,
                    )
                )
                continue

            eh_text = _erwartungshorizont_text(teilaufgabe.erwartungshorizont) if teilaufgabe.erwartungshorizont else ""
            if not eh_text:
                results.append(
                    NotChecked(
                        rule_id="FORM-07",
                        reason="Erwartungshorizont fehlt noch",
                        missing=["teilaufgabe.erwartungshorizont"],
                        anchor=anchor,
                    )
                )
                continue

            teilaufgabe_operatoren = _distinct_operators(find_operator_matches(teilaufgabe.text))
            if not teilaufgabe_operatoren:
                results.append(
                    NotChecked(
                        rule_id="FORM-07",
                        reason="kein Operator aus der Liste erkannt, Leistungsabgleich nicht moeglich",
                        missing=["teilaufgabe.text"],
                        anchor=anchor,
                    )
                )
                continue

            teilaufgabe_niveaus = {level for op in teilaufgabe_operatoren for level in operators[op]}

            eh_operator = judge(eh_text, list(operators), operator_explanations=explanations)
            if not eh_operator:
                continue  # model could not identify a matching operator -- no defensible flag

            eh_niveaus = set(operators.get(eh_operator, []))
            if teilaufgabe_niveaus & eh_niveaus:
                continue

            finding = (
                f"Die Teilaufgabe verlangt mit dem Operator {', '.join(teilaufgabe_operatoren)!r} "
                f"Anforderungsbereich {', '.join(sorted(teilaufgabe_niveaus))}, der Erwartungshorizont "
                f"bepunktet jedoch eine Leistung vom Typ {eh_operator!r} "
                f"(Anforderungsbereich {', '.join(sorted(eh_niveaus))})."
            )

            results.append(
                Flag(
                    flag_id=f"form07-{anchor}",
                    rule_id="FORM-07",
                    anchor=anchor,
                    severity=form07.severity_default,
                    mechanism="llm",
                    finding=finding,
                    evidence=Evidence(
                        rule_quote=form07.source.quote, source=f"{form07.source.document}, {form07.source.locator}"
                    ),
                    suggestions=list(form07.suggestion_template),
                )
            )

    return results
