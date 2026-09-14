"""KOMP-01's candidate-set construction: which Anlage-2 Einzelkompetenzen a
Teilaufgabe's declared curriculare Einheit(en) make it plausible to test.

This is deliberately deterministic and separate from the LLM call itself
(gateway/model_gateway.py, provider-agnostic -- see gateway/base.py): the LLM
only ever chooses *among* these candidates, never invents a code outside
them, which is what keeps KOMP-06 meaningful as a guardrail rather than a
formality.
"""
from __future__ import annotations

from checks.catalogue import load_anlage_2_codes, load_kompetenzen


def candidate_kompetenzen(curriculare_einheit: list[str]) -> list[str]:
    """Anlage-2 codes a Teilaufgabe's declared CE(s) make plausible.

    Three cases, not two -- the middle one is the one worth getting right:

    - No CE declared at all: we don't know where to look, so fall back to
      every Anlage-2 code (all 85) and let the model search broadly.
    - CE(s) declared, and at least one maps to real Anlage-2 competencies:
      the union of those competencies. Most Teilaufgaben land here.
    - CE(s) declared, but *all* of them map to zero Anlage-2 competencies:
      CE 01/02/03 are 1st/2nd-Ausbildungsdrittel units with
      ``kompetenzen_anlage_2: []`` in rules/kompetenzen.yaml -- they carry no
      staatliche-Prüfungs-relevant competency at all. This is not "unknown,"
      it is a real, correct answer: return the empty list, do NOT fall back
      to the full 85-code set. A Teilaufgabe tied only to such a CE cannot
      test an Anlage-2 competency through that CE, and KOMP-01 firing on it
      is the textually defensible outcome, not a false negative to work
      around.
    """
    if not curriculare_einheit:
        return sorted(load_anlage_2_codes())

    einheiten = {entry["ce"]: entry for entry in load_kompetenzen()["curriculare_einheiten"]}
    codes: set[str] = set()
    for ce in curriculare_einheit:
        entry = einheiten.get(ce)
        if entry is not None:
            codes.update(entry["kompetenzen_anlage_2"])
    return sorted(codes)
