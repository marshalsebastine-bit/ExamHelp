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

**The Teilaufgabe's own operator is extracted deterministically**, via
``checks/deterministic/form_operators.py::find_operator_matches`` -- the same
extraction FORM-03/04/11/13 already trust -- rather than asked of the model.
An earlier version asked the model to label that side too, and it visibly
misread a Teilaufgabe opening with the explicit operator "Beschreiben Sie" as
"Aufzählung": a plain misread a keyword match never gets wrong.

**No quote, no flag.** The model must return ``beleg_zitat`` -- a literal
quote of the Erwartungspunkt it objects to -- and this module drops any
``mismatch: true`` verdict that arrives without one. That is the project's
"no flag without evidence" rule (schemas/flag.py) pushed one step earlier,
into the reasoning step, and it is not decoration: measured against the
corpus's own ground truth, requiring the quote (together with the two prompt
fixes described in ``gateway.model_gateway.judge_form_07``) took this check
from 23 false positives on 25 labelled-clean Teilaufgaben down to 0, same
model, same items. See docs/week3-form07-quality-spot-check.md §3.

``judge`` is injected the same way ``checks/llm/komp_01.py``'s ``classify``
is: production code passes ``gateway.model_gateway.judge_form_07``, tests
pass a fake. ``checks/runner.py`` follows the same "no model, no NotChecked
per Teilaufgabe" posture it already uses for KOMP-01 when the caller has no
judge to inject.
"""
from __future__ import annotations

from typing import Callable

from checks.catalogue import load_operators, rule
from checks.deterministic.form_operators import _distinct_operators, find_operator_matches
from schemas.aufgabe import Aufsichtsarbeit, Erwartungshorizont
from schemas.flag import Evidence, Flag, NotChecked

Judge = Callable[..., dict]


def _erwartungshorizont_text(erwartungshorizont: Erwartungshorizont) -> str:
    zeilen = [p.text for p in erwartungshorizont.erwartungspunkte if p.text]
    if erwartungshorizont.freitext:
        zeilen.append(erwartungshorizont.freitext)
    return "\n".join(zeilen)


def check_form_07(aufgabe: Aufsichtsarbeit, *, judge: Judge) -> list[Flag | NotChecked]:
    form07 = rule("FORM-07")
    operators = load_operators()
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

            verdict = judge(
                teilaufgabe.text,
                teilaufgabe_operatoren,
                eh_text,
                operators=operators,
                rule_text=form07.rule_text,
            )
            if not verdict.get("mismatch"):
                continue

            # No quote, no flag. The prompt already tells the model to answer
            # mismatch=false unless it can cite the offending Erwartungspunkt;
            # this enforces that structurally rather than trusting it, the same
            # defense-in-depth posture checks/llm/komp_01.py applies to the
            # classifier's codes.
            beleg_zitat = (verdict.get("beleg_zitat") or "").strip()
            if not beleg_zitat:
                continue

            begruendung = verdict.get("begruendung") or ""
            finding = (
                f"Der Erwartungshorizont bepunktet nicht die Leistung, die der Operator "
                f"{', '.join(teilaufgabe_operatoren)!r} von der Teilaufgabe verlangt: {beleg_zitat!r}."
            )
            if begruendung:
                finding = f"{finding} {begruendung}"

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
