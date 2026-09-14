"""KOMP-04: the declared Anforderungsniveaus across a whole Aufsichtsarbeit
must span more than one level. All-level-I tests reproduction, not
competency in Anlage 2's sense.

``input_slice`` also lists ``teilaufgabe.punkte``, but neither the
rule_text nor its mutation (MUT-KOMP-04, "set every Anforderungsniveau to
I") calls for weighting the distribution by Punkte -- only for it to be
non-degenerate at all. This check deliberately does not use punkte; the
rule's own `notes` flag that a points-weighted reading is a judgement call
for later, not something to invent here without a real drafted item to
calibrate against.
"""
from __future__ import annotations

from checks.catalogue import rule
from schemas.aufgabe import Aufsichtsarbeit
from schemas.flag import Evidence, Flag, NotChecked


def check_komp_04(aufgabe: Aufsichtsarbeit) -> list[Flag] | list[NotChecked]:
    levels = [t.anforderungsniveau for t in aufgabe.alle_teilaufgaben() if t.anforderungsniveau]
    if not levels:
        return [
            NotChecked(
                rule_id="KOMP-04",
                reason="keine Teilaufgabe mit Anforderungsniveau vorhanden",
                missing=["aufgabe.aufgaben[].teilaufgaben[].anforderungsniveau"],
            )
        ]

    distinct = sorted(set(levels))
    if len(distinct) > 1:
        return []

    komp04 = rule("KOMP-04")
    return [
        Flag(
            flag_id="komp04-aufgabe",
            rule_id="KOMP-04",
            anchor="aufgabe",
            severity=komp04.severity_default,
            mechanism="deterministic",
            finding=(
                f"Alle {len(levels)} Teilaufgaben mit Anforderungsniveau liegen auf Stufe "
                f"{distinct[0]}; die Verteilung ueber die gesamte Aufsichtsarbeit ist degeneriert."
            ),
            evidence=Evidence(rule_quote=komp04.source.quote, source=f"{komp04.source.document}, {komp04.source.locator}"),
        )
    ]
