"""FORM-05, FORM-12, FORM-14, FORM-15: the four Family A rules that flag a
linguistic pattern in Fallsituation/Teilaufgabe prose rather than anything
structural. All four are ``requires: []`` in rules/form.yaml -- the
catalogue author's own choice, not this module's: with no precondition,
"nothing found" is a pass, never a NotChecked.

Every marker list here is a deliberately narrow, high-precision reading,
not a linguist's complete one -- tech doc 7.2 is explicit that a false flag
on a clean item costs more than a missed one on this tool. Two examples:
FORM-15 uses only wuerde-/waere-/haette-family Konjunktiv II forms, never
"koennte/muesste/sollte/moechte", because those are common, unambiguous
modal hedging in ordinary German (and "moechte" already appears in the real
A-01 fixture) and would false-flag constantly if included; FORM-05's
subordinator list omits "als" and "da", both of which have a common
non-subordinating reading ("groesser als", "da" meaning "there").

Every marker here is verified against items/manifest.json's known_weaknesses
for C-01 (which was deliberately constructed to trip every one of these
four rules at once) and against a clean-item sweep of the other 11 items,
so a marker choice is checked against real text, not just plausible in
theory.
"""
from __future__ import annotations

import re

from checks.catalogue import rule
from checks.deterministic._german_text import count_matches, flex
from schemas.aufgabe import Aufsichtsarbeit, Fallsituation
from schemas.flag import Evidence, Flag


def _sentences(text: str | None) -> list[str]:
    """Reuses Fallsituation.saetze()'s abbreviation-aware splitter for any
    text, Teilaufgabe included -- it is a pure function of ``.text``."""
    return Fallsituation(text=text).saetze()


def _block_sentences(block) -> list[str]:
    sentences: list[str] = []
    if block.fallsituation:
        sentences.extend(_sentences(block.fallsituation.text))
    for teilaufgabe in block.teilaufgaben:
        sentences.extend(_sentences(teilaufgabe.text))
    return sentences


# ---- FORM-05: Schachtelsaetze, doppelte Negation ---------------------------

_SUBORDINATORS = (
    "dass", "weil", "obwohl", "während", "nachdem", "bevor", "sodass", "so dass",
    "damit", "wenn", "ob", "indem", "obgleich", "wobei",
    "welche", "welcher", "welches", "welchem", "welchen",
)
_NEGATIONS = (
    "nicht", "kein", "keine", "keinen", "keinem", "keiner", "keines",
    "nie", "niemals", "nichts", "niemand", "nirgends", "nirgendwo", "weder",
)
MIN_SUBORDINATORS_FOR_SCHACHTELSATZ = 3
MIN_NEGATIONS_FOR_DOPPELTE_NEGATION = 2


def check_form_05(aufgabe: Aufsichtsarbeit) -> list[Flag]:
    form05 = rule("FORM-05")
    flags: list[Flag] = []

    for ai, block in enumerate(aufgabe.aufgaben):
        block_id = aufgabe.aufgabe_block_id(ai)
        findings = []
        for satz in _block_sentences(block):
            subordinators = count_matches(_SUBORDINATORS, satz)
            if len(subordinators) >= MIN_SUBORDINATORS_FOR_SCHACHTELSATZ:
                findings.append(
                    f"Verschachtelter Satz ({len(subordinators)} Nebensatz-Marker: "
                    f"{', '.join(subordinators)}): \"{satz}\""
                )
                break
        for satz in _block_sentences(block):
            negations = count_matches(_NEGATIONS, satz)
            if len(negations) >= MIN_NEGATIONS_FOR_DOPPELTE_NEGATION:
                findings.append(f"Doppelte Negation ({', '.join(negations)}): \"{satz}\"")
                break

        for i, finding in enumerate(findings):
            flags.append(
                Flag(
                    flag_id=f"form05-{block_id}-{i}",
                    rule_id="FORM-05",
                    anchor=block_id,
                    severity=form05.severity_default,
                    mechanism="deterministic",
                    finding=finding,
                    evidence=Evidence(rule_quote=form05.source.quote, source=f"{form05.source.document}, {form05.source.locator}"),
                    suggestions=list(form05.suggestion_template),
                )
            )

    return flags


# ---- FORM-12: Ziffern statt Zahlwoerter ------------------------------------

_ONES = {2: "zwei", 3: "drei", 4: "vier", 5: "fünf", 6: "sechs", 7: "sieben", 8: "acht", 9: "neun"}
_TEENS = {
    10: "zehn", 11: "elf", 12: "zwölf", 13: "dreizehn", 14: "vierzehn", 15: "fünfzehn",
    16: "sechzehn", 17: "siebzehn", 18: "achtzehn", 19: "neunzehn",
}
_TENS = {20: "zwanzig", 30: "dreißig", 40: "vierzig", 50: "fünfzig", 60: "sechzig", 70: "siebzig", 80: "achtzig", 90: "neunzig"}
_UNIT_PREFIX = {1: "ein", **_ONES}


def _number_words() -> tuple[str, ...]:
    """German cardinal number words 2-100, spelled out. Deliberately
    excludes bare 'eins'/'ein': that is also the indefinite article
    ('ein Rollator'), and flagging every indefinite article as a
    Mengenangabe would swamp this hinweis-severity check with noise far
    beyond what it is worth -- a known, accepted false-negative for 1,
    not an oversight."""
    words = list(_ONES.values()) + list(_TEENS.values()) + list(_TENS.values())
    for tens_value, tens_word in _TENS.items():
        for unit_value, unit_word in _UNIT_PREFIX.items():
            words.append(f"{unit_word}und{tens_word}")
    words.append("hundert")
    return tuple(words)


def _number_word_pattern() -> re.Pattern[str]:
    return re.compile(r"\b(?:" + "|".join(flex(w) for w in _number_words()) + r")\b", re.IGNORECASE)


def check_form_12(aufgabe: Aufsichtsarbeit) -> list[Flag]:
    form12 = rule("FORM-12")
    pattern = _number_word_pattern()
    flags: list[Flag] = []

    for ai, block in enumerate(aufgabe.aufgaben):
        block_id = aufgabe.aufgabe_block_id(ai)
        texts = ([block.fallsituation.text] if block.fallsituation else []) + [t.text for t in block.teilaufgaben]
        found = [m.group(0) for text in texts if text for m in pattern.finditer(text)]
        if not found:
            continue

        flags.append(
            Flag(
                flag_id=f"form12-{block_id}",
                rule_id="FORM-12",
                anchor=block_id,
                severity=form12.severity_default,
                mechanism="deterministic",
                finding=f"Zahlwort statt Ziffer verwendet: {', '.join(sorted(set(found)))}.",
                evidence=Evidence(rule_quote=form12.source.quote, source=f"{form12.source.document}, {form12.source.locator}"),
                suggestions=list(form12.suggestion_template),
            )
        )

    return flags


# ---- FORM-14: Aktiv statt Passiv -------------------------------------------

_WERDEN_AUX = ("wird", "werden", "wurde", "wurden", "worden")


def _looks_like_partizip_ii(word: str) -> bool:
    """A blunt, deliberately permissive shape test, not real morphology:
    starts with 'ge' (the common case, 'gefunden') or ends in a participle-
    shaped suffix long enough not to catch short unrelated words. Paired
    with requiring a werden-auxiliary in the same sentence, the combination
    stays precise enough for a hinweis-severity check to be worth running
    (verified against every real item, not just the C-01 fixture it targets:
    see the module docstring)."""
    stripped = word.strip(".,;:!?")
    if len(stripped) < 5:
        return False
    lower = stripped.casefold()
    return lower.startswith("ge") or lower.endswith("t") or (lower.endswith("en") and len(stripped) >= 6)


def check_form_14(aufgabe: Aufsichtsarbeit) -> list[Flag]:
    form14 = rule("FORM-14")
    flags: list[Flag] = []

    for ai, block in enumerate(aufgabe.aufgaben):
        block_id = aufgabe.aufgabe_block_id(ai)
        for satz in _block_sentences(block):
            aux_matches = count_matches(_WERDEN_AUX, satz)
            if not aux_matches:
                continue
            if any(_looks_like_partizip_ii(word) for word in satz.split()):
                flags.append(
                    Flag(
                        flag_id=f"form14-{block_id}",
                        rule_id="FORM-14",
                        anchor=block_id,
                        severity=form14.severity_default,
                        mechanism="deterministic",
                        finding=f"Passivkonstruktion (\"{aux_matches[0]}\" ...): \"{satz}\"",
                        evidence=Evidence(rule_quote=form14.source.quote, source=f"{form14.source.document}, {form14.source.locator}"),
                        suggestions=list(form14.suggestion_template),
                    )
                )
                break  # one flag per block is enough signal

    return flags


# ---- FORM-15: Indikativ statt Konjunktiv -----------------------------------

# wuerde-/waere-/haette-family Konjunktiv II only -- see module docstring for
# why "koennte/muesste/sollte/moechte" are deliberately excluded.
_KONJUNKTIV_II = (
    "würde", "würdest", "würden", "würdet",
    "wäre", "wärst", "wärest", "wären", "wärt", "wäret",
    "hätte", "hättest", "hätten", "hättet",
)


def check_form_15(aufgabe: Aufsichtsarbeit) -> list[Flag]:
    form15 = rule("FORM-15")
    flags: list[Flag] = []

    for ai, block in enumerate(aufgabe.aufgaben):
        block_id = aufgabe.aufgabe_block_id(ai)
        found: list[str] = []
        for satz in _block_sentences(block):
            found.extend(count_matches(_KONJUNKTIV_II, satz))
        if not found:
            continue

        flags.append(
            Flag(
                flag_id=f"form15-{block_id}",
                rule_id="FORM-15",
                anchor=block_id,
                severity=form15.severity_default,
                mechanism="deterministic",
                finding=f"Konjunktiv-II-Form statt Indikativ verwendet: {', '.join(sorted(set(found)))}.",
                evidence=Evidence(rule_quote=form15.source.quote, source=f"{form15.source.document}, {form15.source.locator}"),
                suggestions=list(form15.suggestion_template),
            )
        )

    return flags
