"""KOMP-03 and KOMP-03B: does the item's competency claims relate to its
declared Prüfungsbereich at all, and if so, by how much.

Both rules run the same lookup and the same set arithmetic; they differ only in
the threshold applied to the result, which is why they are one module.  See the
`notes` field of each rule in rules/kompetenz.yaml for why the threshold split
exists rather than one rule with one bar.
"""
from __future__ import annotations

from checks.catalogue import load_pruefungsbereiche
from schemas.aufgabe import Aufsichtsarbeit
from schemas.flag import Evidence, Flag, NotChecked


def schwerpunkt(code: str) -> str:
    """Reduce an Einzelkompetenz code to its Kompetenzschwerpunkt: 'I.3.a' -> 'I.3'."""
    bereich, nummer, _ = code.split(".")
    return f"{bereich}.{nummer}"


def claimed_schwerpunkte(aufgabe: Aufsichtsarbeit) -> set[str]:
    codes = {code for t in aufgabe.teilaufgaben for code in t.kompetenzzuordnung}
    return {schwerpunkt(code) for code in codes}


def _gate(aufgabe: Aufsichtsarbeit, rule_id: str) -> tuple[set[str], dict] | list[NotChecked]:
    """Shared precondition check: both rules need the same two fields."""
    missing = []
    if not aufgabe.metadaten.pruefungsbereich:
        missing.append("aufgabe.metadaten.pruefungsbereich")
    claimed = claimed_schwerpunkte(aufgabe)
    if not any(t.kompetenzzuordnung for t in aufgabe.teilaufgaben):
        missing.append("teilaufgabe.kompetenzzuordnung")
    if missing:
        return [NotChecked(rule_id=rule_id, reason="Praeambel unvollstaendig", missing=missing)]

    bereiche = load_pruefungsbereiche()
    nummer = int(aufgabe.metadaten.pruefungsbereich)
    if nummer not in bereiche:
        return [
            NotChecked(
                rule_id=rule_id,
                reason=f"unbekannter Pruefungsbereich {nummer!r}",
                missing=["aufgabe.metadaten.pruefungsbereich"],
            )
        ]
    return claimed, bereiche[nummer]


def check_komp_03(aufgabe: Aufsichtsarbeit) -> list[Flag] | list[NotChecked]:
    """Blocker: fires only when the item touches NONE of its required Schwerpunkte.

    The narrow, textually defensible reading -- see the rule's `notes`.
    """
    result = _gate(aufgabe, "KOMP-03")
    if isinstance(result, list):
        return result
    claimed, bereich = result

    covered = claimed & set(bereich["kompetenzschwerpunkte"])
    if covered:
        return []

    return [
        Flag(
            flag_id="komp03-aufgabe",
            rule_id="KOMP-03",
            anchor="aufgabe",
            severity="blocker",
            mechanism="deterministic",
            finding=(
                f"Keine der ausgewiesenen Kompetenzzuordnungen beruehrt einen der "
                f"Kompetenzschwerpunkte, die § 14 Absatz 1 PflAPrV fuer Pruefungsbereich "
                f"{bereich['nummer']} benennt ({', '.join(bereich['kompetenzschwerpunkte'])})."
            ),
            evidence=Evidence(rule_quote=bereich["quote"], source=f"PflAPrV § 14 Absatz 1, Nr. {bereich['nummer']}"),
        )
    ]


def check_komp_03b(aufgabe: Aufsichtsarbeit) -> list[Flag] | list[NotChecked]:
    """Pruefen: fires when covered Schwerpunkte are strictly fewer than half the
    required set. A construction-quality signal, not a binding-law violation."""
    result = _gate(aufgabe, "KOMP-03B")
    if isinstance(result, list):
        return result
    claimed, bereich = result

    required = set(bereich["kompetenzschwerpunkte"])
    covered = claimed & required
    if len(covered) >= len(required) / 2:
        return []

    return [
        Flag(
            flag_id="komp03b-aufgabe",
            rule_id="KOMP-03B",
            anchor="aufgabe",
            severity="pruefen",
            mechanism="deterministic",
            finding=(
                f"Nur {len(covered)} von {len(required)} Kompetenzschwerpunkten des "
                f"Pruefungsbereichs {bereich['nummer']} werden beruehrt "
                f"({', '.join(sorted(covered)) or '-'} von {', '.join(sorted(required))})."
            ),
            evidence=Evidence(
                rule_quote=(
                    "Die Kompetenzzuordnungen einer Aufsichtsarbeit sollen mehr als die "
                    "Haelfte der fuer ihren Pruefungsbereich benannten Kompetenzschwerpunkte "
                    "beruehren."
                ),
                source="KOMP-03B (Konstruktionsprinzip)",
            ),
        )
    ]
