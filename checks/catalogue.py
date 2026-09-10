"""Load the rule catalogue and its lookup tables.

The catalogue is data (tech doc 9), so this module is the only place that knows
where the YAML lives.  Checks receive a ``Rule`` and the lookup tables they need;
no check parses YAML itself, and no check hardcodes a rule's text.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from schemas.rule import Rule, RuleSet

RULES_DIR = Path(__file__).resolve().parents[1] / "rules"

RULE_FILES = ("form.yaml", "kompetenz.yaml", "quellenbindung.yaml")


def _load_yaml(name: str) -> dict:
    path = RULES_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"catalogue file missing: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_ruleset() -> RuleSet:
    """Load and validate every rule file into one RuleSet."""
    rules: list[Rule] = []
    for name in RULE_FILES:
        rules.extend(RuleSet.model_validate(_load_yaml(name)).rules)
    return RuleSet(rules=rules)


@lru_cache(maxsize=1)
def load_operators() -> dict[str, list[str]]:
    """Operator -> the Anforderungsbereiche it may carry.

    A dict, not a vector index: FORM-03 has to be able to answer "this operator
    is not on the list at all", which a similarity search cannot do
    (repo review 2.1).
    """
    document = _load_yaml("operators.yaml")
    index: dict[str, list[str]] = {}
    for entry in document["operators"]:
        index.setdefault(entry["operator"], []).append(entry["anforderungsbereich"])
    return index


@lru_cache(maxsize=1)
def load_kompetenzen() -> dict:
    """The competency catalogue.

    ``anlage_2_authoritative`` is parsed from PflAPrV's own Anlage 2 text and is
    what KOMP-06 tests membership against.  The Lehrplan-derived list is a
    strict subset and must not be used for that (see the file's meta).
    """
    return _load_yaml("kompetenzen.yaml")


@lru_cache(maxsize=1)
def load_anlage_2_codes() -> frozenset[str]:
    return frozenset(load_kompetenzen()["anlage_2_authoritative"])


@lru_cache(maxsize=1)
def load_anlage_1_codes() -> frozenset[str]:
    return frozenset(load_kompetenzen()["anlage_1_authoritative"])


@lru_cache(maxsize=1)
def load_pruefungsbereiche() -> dict[int, dict]:
    """Pruefungsbereich number -> its Kompetenzschwerpunkte, per PflAPrV § 14 (1)."""
    document = _load_yaml("pruefungsbereiche.yaml")
    return {entry["nummer"]: entry for entry in document["pruefungsbereiche"]}


@lru_cache(maxsize=1)
def load_situationsmerkmale() -> dict[str, dict]:
    """CE -> its Situationsmerkmale, for KOMP-07."""
    document = _load_yaml("situationsmerkmale.yaml")
    return {entry["ce"]: entry for entry in document["curriculare_einheiten"]}


def rule(rule_id: str) -> Rule:
    for candidate in load_ruleset().rules:
        if candidate.id == rule_id:
            return candidate
    raise KeyError(f"unknown rule id: {rule_id}")
