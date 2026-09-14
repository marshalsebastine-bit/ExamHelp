"""KOMP-01: derives which Anlage-2 Einzelkompetenzen a Teilaufgabe tests, and
flags a Teilaufgabe that tests none of them.

This is also the step that populates
``Teilaufgabe.kompetenzzuordnung_abgeleitet`` for the deterministic checks
downstream (KOMP-03, KOMP-03B, KOMP-06 in checks/deterministic/) to read.
Those checks are decoupled readers of that field -- they do not call this
module themselves -- so whatever sequences rule execution must run KOMP-01
before them, or the field is simply empty for an artifact this run has not
yet derived. ``checks/runner.py::run_checks`` is that sequencer: it runs
KOMP-01 first, always, before the deterministic sweep.
"""
from __future__ import annotations

from typing import Callable

from checks.catalogue import load_anlage_2_text, rule
from checks.llm.kompetenz_candidates import candidate_kompetenzen
from schemas.aufgabe import Aufsichtsarbeit, Teilaufgabe
from schemas.flag import Evidence, Flag, NotChecked

Classifier = Callable[..., list[str]]


def derive_kompetenzzuordnung(
    teilaufgabe: Teilaufgabe, *, classify: Classifier, fallsituation_text: str | None = None
) -> list[str]:
    """The candidate set is deterministic; only the choice among it is not.

    ``classify`` is injected so this function -- and everything that calls
    it -- never has to know which provider is behind it: production code
    passes ``gateway.model_gateway.classify_kompetenz`` (itself
    provider-agnostic, see gateway/base.py), tests pass a fake.

    ``fallsituation_text`` is the owning Aufgabe block's case scenario. Many
    Teilaufgaben only make sense read against it ("Erläutern Sie anhand der
    Fallsituation..."), so it is passed through as required context for the
    classifier rather than left out and re-derived from the Teilaufgabe text
    alone. ``check_komp_01`` treats a missing Fallsituation as unmet
    precondition and never calls this function without one; this function's
    own default of ``None`` is only for callers (tests, ad-hoc scripts) that
    invoke it directly and knowingly want the text-only behaviour.
    """
    candidates = candidate_kompetenzen(teilaufgabe.situationsmerkmale.curriculare_einheit)
    if not candidates:
        return []
    kompetenz_text = load_anlage_2_text()
    derived = classify(teilaufgabe.text, candidates, kompetenz_text=kompetenz_text, fallsituation_text=fallsituation_text)
    # Defense in depth: never trust the classifier's output on its own, even
    # though gateway/model_gateway.py already filters to the candidate set.
    return sorted(set(derived) & set(candidates))


def check_komp_01(aufgabe: Aufsichtsarbeit, *, classify: Classifier) -> list[Flag | NotChecked]:
    """Derive per Teilaufgabe, write the result back onto the artifact, and
    flag any Teilaufgabe whose derived set is empty.

    Two hard preconditions, both gated the same way (NotChecked, not a
    guess): ``teilaufgabe.text`` and the owning Aufgabe block's
    ``fallsituation.text``. The latter is required, not merely used when
    present, because a Teilaufgabe's derivation without its case scenario is
    a worse-quality guess this project would rather surface as "not yet
    checkable" than silently produce.
    """
    komp01 = rule("KOMP-01")
    results: list[Flag | NotChecked] = []

    for ai, block in enumerate(aufgabe.aufgaben):
        for ti, teilaufgabe in enumerate(block.teilaufgaben):
            anchor = aufgabe.teilaufgabe_id(ai, ti)
            if not teilaufgabe.text:
                results.append(
                    NotChecked(
                        rule_id="KOMP-01",
                        reason="Teilaufgabentext fehlt noch",
                        missing=["teilaufgabe.text"],
                        anchor=anchor,
                    )
                )
                continue

            fallsituation_text = block.fallsituation.text if block.fallsituation else None
            if not fallsituation_text:
                results.append(
                    NotChecked(
                        rule_id="KOMP-01",
                        reason="Fallsituation fehlt noch",
                        missing=["aufgabe.aufgaben[].fallsituation.text"],
                        anchor=anchor,
                    )
                )
                continue

            derived = derive_kompetenzzuordnung(teilaufgabe, classify=classify, fallsituation_text=fallsituation_text)
            teilaufgabe.kompetenzzuordnung_abgeleitet = derived
            if derived:
                continue

            results.append(
                Flag(
                    flag_id=f"komp01-{anchor}",
                    rule_id="KOMP-01",
                    anchor=anchor,
                    severity=komp01.severity_default,
                    mechanism="llm",
                    finding=(
                        "Fuer diese Teilaufgabe laesst sich keine Anlage-2-Kompetenz ableiten, "
                        "weder aus der ausgewiesenen curricularen Einheit noch aus dem Aufgabentext."
                    ),
                    evidence=Evidence(
                        rule_quote=komp01.rule_text,
                        source=f"{komp01.source.document}, {komp01.source.locator}",
                    ),
                )
            )

    return results
