"""checks/runner.py: sequences KOMP-01 before the deterministic sweep, and
accounts for every rule in the catalogue -- implemented, blocked, or not
yet implemented -- so nothing is silently missing from a CheckResult.
"""
from __future__ import annotations

import json
from pathlib import Path

from checks.catalogue import load_ruleset
from checks.runner import CHECKS, run_checks
from schemas.aufgabe import Aufsichtsarbeit
from schemas.flag import Flag, NotChecked

ITEMS_DIR = Path(__file__).resolve().parents[1] / "items"


def load(name: str) -> Aufsichtsarbeit:
    return Aufsichtsarbeit.model_validate(json.loads((ITEMS_DIR / f"{name}.json").read_text(encoding="utf-8")))


def fake_classify(
    text: str, candidates: list[str], *, kompetenz_text: dict, fallsituation_text: str | None = None
) -> list[str]:
    return candidates[:1]


def test_every_catalogue_rule_is_dispatchable_or_reported_missing() -> None:
    """A rule that finds nothing wrong legitimately produces neither a Flag
    nor a NotChecked (that is how every check module here has always
    worked, runner or not), so "every rule appears in one run's output"
    cannot hold in general. What must hold: every rule neither implemented
    (CHECKS or KOMP-01) nor blocked (not `rule.runnable`) is reported via
    "kein Check implementiert" when actually run -- so a truly-missing
    check can never be silently invisible."""
    all_ids = {r.id for r in load_ruleset().rules}
    implemented = set(CHECKS) | {"KOMP-01"}
    blocked = {r.id for r in load_ruleset().rules if not r.runnable}
    residual = all_ids - implemented - blocked
    assert residual, "sanity: the catalogue should still have some unimplemented rules"

    result = run_checks(load("A-01"), classify=fake_classify)
    reported_missing = {n.rule_id for n in result.not_checked if n.reason == "kein Check implementiert"}
    assert residual <= reported_missing


def test_blocked_rules_are_not_checked_with_the_block_reason() -> None:
    result = run_checks(load("A-01"), classify=fake_classify)
    blocked = {r.id for r in load_ruleset().rules if not r.runnable}
    assert blocked  # sanity: the catalogue actually has some
    not_checked_ids = {n.rule_id: n.reason for n in result.not_checked}
    for rule_id in blocked:
        assert rule_id in not_checked_ids
        assert "blockiert" in not_checked_ids[rule_id]


def test_unimplemented_rules_are_not_checked() -> None:
    result = run_checks(load("A-01"), classify=fake_classify)
    not_checked_ids = {n.rule_id: n.reason for n in result.not_checked}
    assert "kein Check implementiert" in not_checked_ids["FORM-07"]


def test_komp_01_runs_before_the_deterministic_sweep_reads_its_output() -> None:
    """fake_classify always returns the first candidate, so every Teilaufgabe
    with a curriculare Einheit gets a derived code -- KOMP-06 (which reads
    kompetenzzuordnung_abgeleitet) must see it, not an empty field."""
    result = run_checks(load("A-01"), classify=fake_classify)
    komp06_not_checked = [n for n in result.not_checked if n.rule_id == "KOMP-06"]
    assert komp06_not_checked == []


def test_classify_none_skips_komp_01_and_reports_no_model() -> None:
    result = run_checks(load("A-01"), classify=None, model="should-be-ignored")
    assert result.model is None
    komp01 = [n for n in result.not_checked if n.rule_id == "KOMP-01"]
    assert len(komp01) == 1
    assert "classify=None" in komp01[0].reason


def test_classify_none_still_runs_the_deterministic_checks() -> None:
    """A missing classifier must not take deterministic Family A checks
    down with it -- they do not depend on KOMP-01 at all."""
    result = run_checks(load("C-01"), classify=None)
    form_ids = {f.rule_id for f in result.flags}
    assert "FORM-05" in form_ids


def test_model_label_is_reported_when_classify_is_given() -> None:
    result = run_checks(load("A-01"), classify=fake_classify, model="fake-model")
    assert result.model == "fake-model"


def test_result_carries_the_aufgabe_id() -> None:
    result = run_checks(load("A-01"), classify=fake_classify)
    assert result.aufgabe_id == "A-01"
