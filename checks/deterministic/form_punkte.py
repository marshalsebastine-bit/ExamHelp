"""FORM-02, FORM-06, FORM-16: the three Family A rules that are pure Punkte
arithmetic, no text parsing involved. Grouped for that shared shape, the
way komp_03.py groups KOMP-03/03B for their shared lookup.

FORM-02 (Bearbeitungsumfang vs. Bearbeitungszeit) and FORM-16 (Aufgabe 1 /
Aufgabe 2 balance) are aufsichtsarbeit-scoped and fire once per item.
FORM-06 (Erwartungshorizont sums to Punktzahl) is teilaufgabe-scoped and
fires once per Teilaufgabe.
"""
from __future__ import annotations

from checks.catalogue import rule
from schemas.aufgabe import Aufsichtsarbeit
from schemas.flag import Evidence, Flag, NotChecked

# PflAPrV Sec 14 (3) fixes Bearbeitungszeit at 120 minutes; it is binding, not
# a plausibility choice. What *is* this project's own choice, with no
# external source stating a number (same footing as FORM-06/16's
# construction_principle thresholds): how many minutes a Pruefungsausschuss
# member should expect a Punkt to take to answer, on average, across a whole
# Aufsichtsarbeit. 1.5 min/Punkt gives every one of the 12 real fixtures
# (max 65 Punkte on 120 minutes, i.e. ~1.85 min/Punkt) a comfortable margin
# while still catching MUT-FORM-02's doubling (~130 Punkte -> ~0.92
# min/Punkt) cleanly. Not from PflAPrV; the flag's evidence carries the
# computed numbers so a reader can judge the threshold itself, same
# reasoning as FORM-06.
MIN_MINUTES_PER_PUNKT = 1.5
DEFAULT_BEARBEITUNGSZEIT = 120

# FORM-16: the smaller Aufgabe block's share of the whole paper's Punkte
# must not fall below this floor. See rules/kompetenz.yaml's FORM-16 `notes`
# for why 40 percent (not 50) is the bar this project settled on.
MIN_SHARE = 0.4


def check_form_02(aufgabe: Aufsichtsarbeit) -> list[Flag] | list[NotChecked]:
    # A plausibility judgement about "the whole paper's workload" is not
    # meaningful against a draft with only one Aufgabe block written --
    # fewer Punkte than a complete paper would carry is simply incomplete,
    # not evidence of an implausible scope. Confirmed against D-01 (the
    # deliberately incomplete fixture, items/manifest.json): the gap here
    # is aufgaben.vollstaendig, the same completeness fact FORM-16 gates on.
    if len(aufgabe.aufgaben) < 2:
        return [
            NotChecked(
                rule_id="FORM-02",
                reason="Aufsichtsarbeit ist nicht vollstaendig (nicht beide Aufgabe-Bloecke vorhanden)",
                missing=["aufgabe.aufgaben[2]"],
            )
        ]

    teilaufgaben = aufgabe.alle_teilaufgaben()
    if not teilaufgaben or not any(t.punkte is not None for t in teilaufgaben):
        return [
            NotChecked(
                rule_id="FORM-02",
                reason="keine Teilaufgaben mit Punktzahl vorhanden",
                missing=["aufgabe.aufgaben[].teilaufgaben[].punkte"],
            )
        ]

    zeit = aufgabe.metadaten.bearbeitungszeit_minuten or DEFAULT_BEARBEITUNGSZEIT
    punkte_summe = aufgabe.punkte_summe or 0.0
    schwelle = zeit / MIN_MINUTES_PER_PUNKT
    if punkte_summe <= schwelle:
        return []

    form02 = rule("FORM-02")
    return [
        Flag(
            flag_id="form02-aufgabe",
            rule_id="FORM-02",
            anchor="aufgabe",
            severity=form02.severity_default,
            mechanism="deterministic",
            finding=(
                f"{punkte_summe:g} Punkte auf {len(teilaufgaben)} Teilaufgaben stehen "
                f"{zeit} Minuten Bearbeitungszeit gegenueber; das setzt weniger als "
                f"{MIN_MINUTES_PER_PUNKT:g} Minuten pro Punkt an."
            ),
            evidence=Evidence(rule_quote=form02.source.quote, source=f"{form02.source.document}, {form02.source.locator}"),
            suggestions=list(form02.suggestion_template),
        )
    ]


def check_form_06(aufgabe: Aufsichtsarbeit) -> list[Flag | NotChecked]:
    form06 = rule("FORM-06")
    results: list[Flag | NotChecked] = []

    for ai, block in enumerate(aufgabe.aufgaben):
        for ti, teilaufgabe in enumerate(block.teilaufgaben):
            anchor = aufgabe.teilaufgabe_id(ai, ti)
            if teilaufgabe.punkte is None:
                results.append(
                    NotChecked(
                        rule_id="FORM-06",
                        reason="keine Punktzahl fuer die Teilaufgabe angegeben",
                        missing=["teilaufgabe.punkte"],
                        anchor=anchor,
                    )
                )
                continue

            horizont = teilaufgabe.erwartungshorizont
            summe = horizont.punkte_summe if horizont else None
            if summe is None:
                results.append(
                    NotChecked(
                        rule_id="FORM-06",
                        reason="kein Erwartungshorizont vorhanden",
                        missing=["teilaufgabe.erwartungshorizont"],
                        anchor=anchor,
                    )
                )
                continue

            if abs(summe - teilaufgabe.punkte) < 1e-6:
                continue

            results.append(
                Flag(
                    flag_id=f"form06-{anchor}",
                    rule_id="FORM-06",
                    anchor=anchor,
                    severity=form06.severity_default,
                    mechanism="deterministic",
                    finding=(
                        f"Teilaufgabe deklariert {teilaufgabe.punkte:g} Punkte, ihr "
                        f"Erwartungshorizont summiert sich auf {summe:g} Punkte."
                    ),
                    evidence=Evidence(rule_quote=form06.source.quote, source=f"{form06.source.document}, {form06.source.locator}"),
                    suggestions=list(form06.suggestion_template),
                )
            )

    return results


def check_form_16(aufgabe: Aufsichtsarbeit) -> list[Flag] | list[NotChecked]:
    if len(aufgabe.aufgaben) < 2:
        return [
            NotChecked(
                rule_id="FORM-16",
                reason="weniger als zwei Aufgabe-Bloecke vorhanden",
                missing=["aufgabe.aufgaben[2]"],
            )
        ]

    block_summen = []
    for block in aufgabe.aufgaben:
        werte = [t.punkte for t in block.teilaufgaben if t.punkte is not None]
        block_summen.append(sum(werte) if werte else None)

    if any(summe is None for summe in block_summen):
        return [
            NotChecked(
                rule_id="FORM-16",
                reason="mindestens ein Aufgabe-Block hat keine Teilaufgabe mit Punktzahl",
                missing=["aufgabe.aufgaben[].teilaufgaben[].punkte"],
            )
        ]

    gesamt = sum(block_summen)
    if gesamt <= 0:
        return [
            NotChecked(
                rule_id="FORM-16",
                reason="Gesamtpunktzahl ist 0",
                missing=["aufgabe.aufgaben[].teilaufgaben[].punkte"],
            )
        ]

    anteile = [summe / gesamt for summe in block_summen]
    if min(anteile) >= MIN_SHARE:
        return []

    form16 = rule("FORM-16")
    kleinster_index = anteile.index(min(anteile))
    kleinster_block = aufgabe.aufgabe_block_id(kleinster_index)
    return [
        Flag(
            flag_id="form16-aufgabe",
            rule_id="FORM-16",
            anchor="aufgabe",
            severity=form16.severity_default,
            mechanism="deterministic",
            finding=(
                f"{kleinster_block} traegt {block_summen[kleinster_index]:g} von "
                f"{gesamt:g} Punkten der Aufsichtsarbeit ({anteile[kleinster_index]:.0%}), "
                f"unter der {MIN_SHARE:.0%}-Schwelle fuer eine ausgewogene Verteilung."
            ),
            evidence=Evidence(rule_quote=form16.source.quote, source=f"{form16.source.document}, {form16.source.locator}"),
            suggestions=list(form16.suggestion_template),
        )
    ]
