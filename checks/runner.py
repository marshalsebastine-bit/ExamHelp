"""Sequences every runnable rule in the catalogue against one Aufsichtsarbeit
and collects the result into one CheckResult (Flag[] + NotChecked[]).

This is the "known gap" every check module and the README have been
pointing at: KOMP-03/03B/06 are decoupled readers of
``teilaufgabe.kompetenzzuordnung_abgeleitet``, the field KOMP-01 populates
by mutating the Teilaufgaben it is handed. Nothing decided "run KOMP-01
first" until this module existed. It still does not decide anything clever
-- it just runs KOMP-01 before the deterministic sweep, once, so the field
is populated (or visibly not, via KOMP-01's own NotChecked) before anything
reads it.

**Every runnable catalogue rule appears in the result, one way or another**
-- silent skipping is a bug (tech doc 4.3, 9), and that applies just as much
to "this rule has no check function yet" as to an unmet `requires`:

- Implemented and its preconditions hold -> Flag or nothing (the check's
  own call).
- Implemented but its preconditions don't hold -> NotChecked (the check's
  own call; several checks report finer-grained reasons than the
  catalogue's static `requires` list captures, e.g. FORM-06's "no
  Erwartungshorizont" or KOMP-03's "no Pruefungsbereich").
- `blocked_on` set in the catalogue (not `rule.runnable`) -> NotChecked
  citing the block, from this module.
- Runnable but no check function is registered here yet (FORM-01/07/08/09/10,
  KOMP-02/05/07, every QUELL-* rule) -> NotChecked "kein Check
  implementiert", from this module. This is expected today, not a bug --
  see README's Family A/B status -- but it must be visible, not absent.

``classify`` is injected, never imported from ``gateway`` directly (same
rule ``checks/llm/komp_01.py`` already follows): pass
``gateway.model_gateway.classify_kompetenz`` for the real thing, or leave
it ``None`` to skip KOMP-01 offline, the same "no key, no network call"
posture as ``tests/test_gateway_integration.py``. ``model`` is a plain
label for ``CheckResult.model`` -- the runner never asks the gateway what
backend or model resolved, since that decision is the caller's.
"""
from __future__ import annotations

from typing import Callable

from checks.catalogue import load_ruleset
from checks.deterministic.form_operators import check_form_03, check_form_04, check_form_11, check_form_13
from checks.deterministic.form_punkte import check_form_02, check_form_06, check_form_16
from checks.deterministic.form_sprache import check_form_05, check_form_12, check_form_14, check_form_15
from checks.deterministic.komp_03 import check_komp_03, check_komp_03b
from checks.deterministic.komp_04 import check_komp_04
from checks.deterministic.komp_06 import check_komp_06
from checks.llm.komp_01 import check_komp_01
from schemas.aufgabe import Aufsichtsarbeit
from schemas.flag import CheckResult, Flag, NotChecked

Classifier = Callable[..., list[str]]

# Every rule with a check function, deterministic and LLM together. Rules
# absent from this dict are handled by the "not yet implemented" branch in
# run_checks -- see the module docstring for exactly which those are today.
CHECKS: dict[str, Callable[[Aufsichtsarbeit], list]] = {
    "FORM-02": check_form_02,
    "FORM-03": check_form_03,
    "FORM-04": check_form_04,
    "FORM-05": check_form_05,
    "FORM-06": check_form_06,
    "FORM-11": check_form_11,
    "FORM-12": check_form_12,
    "FORM-13": check_form_13,
    "FORM-14": check_form_14,
    "FORM-15": check_form_15,
    "FORM-16": check_form_16,
    "KOMP-03": check_komp_03,
    "KOMP-03B": check_komp_03b,
    "KOMP-04": check_komp_04,
    "KOMP-06": check_komp_06,
}


def run_checks(
    aufgabe: Aufsichtsarbeit,
    *,
    classify: Classifier | None = None,
    model: str | None = None,
) -> CheckResult:
    flags: list[Flag] = []
    not_checked: list[NotChecked] = []

    # KOMP-01 first, always -- it is the only thing that populates
    # teilaufgabe.kompetenzzuordnung_abgeleitet, which KOMP-03/03B/06 read.
    if classify is not None:
        for result in check_komp_01(aufgabe, classify=classify):
            (flags if isinstance(result, Flag) else not_checked).append(result)
    else:
        not_checked.append(
            NotChecked(
                rule_id="KOMP-01",
                reason="kein Modell verfuegbar (classify=None); Kompetenzableitung nicht durchgefuehrt",
                missing=["teilaufgabe.kompetenzzuordnung_abgeleitet"],
            )
        )

    for rule in load_ruleset().rules:
        if rule.id == "KOMP-01":
            continue  # already handled above

        if not rule.runnable:
            not_checked.append(
                NotChecked(rule_id=rule.id, reason=f"blockiert: {rule.blocked_on}", missing=[])
            )
            continue

        check_fn = CHECKS.get(rule.id)
        if check_fn is None:
            not_checked.append(NotChecked(rule_id=rule.id, reason="kein Check implementiert", missing=[]))
            continue

        for result in check_fn(aufgabe):
            (flags if isinstance(result, Flag) else not_checked).append(result)

    return CheckResult(
        aufgabe_id=aufgabe.aufgabe_id,
        flags=flags,
        not_checked=not_checked,
        model=model if classify is not None else None,
    )
