"""KOMP-06: every derived competency code actually exists in Anlage 2.

Never had a code implementation before this schema's competency evidence was
LLM-derived (checks/llm/komp_01.py) rather than author-declared. Since the
derivation already filters to a candidate set that is itself always a subset
of Anlage 2 (checks/llm/kompetenz_candidates.py), this should rarely fire in
practice -- but it stays valuable as a guardrail against a candidate-set
construction bug or a gateway that stops filtering correctly, the same
"cheapest high-value check" role it would have had against an author's claim.
"""
from __future__ import annotations

from checks.catalogue import load_anlage_2_codes, rule
from schemas.aufgabe import Aufsichtsarbeit
from schemas.flag import Evidence, Flag, NotChecked


def check_komp_06(aufgabe: Aufsichtsarbeit) -> list[Flag | NotChecked]:
    komp06 = rule("KOMP-06")
    anlage_2 = load_anlage_2_codes()
    results: list[Flag | NotChecked] = []

    for ai, block in enumerate(aufgabe.aufgaben):
        for ti, teilaufgabe in enumerate(block.teilaufgaben):
            anchor = aufgabe.teilaufgabe_id(ai, ti)
            if not teilaufgabe.kompetenzzuordnung_abgeleitet:
                results.append(
                    NotChecked(
                        rule_id="KOMP-06",
                        reason="keine abgeleitete Kompetenzzuordnung vorhanden",
                        missing=["teilaufgabe.kompetenzzuordnung_abgeleitet"],
                        anchor=anchor,
                    )
                )
                continue

            invalid = sorted(set(teilaufgabe.kompetenzzuordnung_abgeleitet) - anlage_2)
            if not invalid:
                continue

            results.append(
                Flag(
                    flag_id=f"komp06-{anchor}",
                    rule_id="KOMP-06",
                    anchor=anchor,
                    severity=komp06.severity_default,
                    mechanism="deterministic",
                    finding=(
                        f"Abgeleiteter Code {', '.join(invalid)} kommt nicht in Anlage 2 PflAPrV vor, "
                        "liegt also ausserhalb der erwarteten Kandidatenmenge fuer diese Teilaufgabe."
                    ),
                    evidence=Evidence(
                        rule_quote=komp06.rule_text,
                        source=f"{komp06.source.document}, {komp06.source.locator}",
                    ),
                )
            )

    return results
