"""Load the rule catalogue and its lookup tables.

The catalogue is data (tech doc 9), so this module is the only place that knows
where the YAML lives.  Checks receive a ``Rule`` and the lookup tables they need;
no check parses YAML itself, and no check hardcodes a rule's text.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import yaml

from schemas.rule import Rule, RuleSet

RULES_DIR = Path(__file__).resolve().parents[1] / "rules"
CORPUS_CHUNKS_DIR = Path(__file__).resolve().parents[1] / "corpus" / "chunks"

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
def load_operator_explanations() -> dict[str, str]:
    """Operator -> its explanation text (e.g. 'Informationen in Form von
    Stichpunkten schreiben...'). Lets FORM-13 identify which operators are
    bare-listing ("Stichpunkte") type from the catalogue's own wording
    rather than a hardcoded operator-name list in Python.
    """
    document = _load_yaml("operators.yaml")
    index: dict[str, str] = {}
    for entry in document["operators"]:
        index.setdefault(entry["operator"], entry["explanation"])
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


@lru_cache(maxsize=1)
def load_anlage_2_text() -> dict[str, str]:
    """Anlage-2 Einzelkompetenz code -> its actual PflAPrV wording.

    KOMP-01's derivation prompt needs to show the model what each candidate
    code actually says, not just the bare code -- a code like "I.1.h" alone
    is meaningless to classify against. Sourced from
    corpus/chunks/metadata.json's "kompetenz" chunks, filtered to
    ``anlage == "2"``: the same code (e.g. "I.1.h") recurs under Anlage 1/3/4
    with *different* wording for each Ausbildungsziel, so anlage must be
    filtered, not just kompetenz_code matched. Deliberately does not go
    through corpus/retrieval.py's search() -- that needs an embeddings index
    (corpus/chunks/embeddings.npy) that does not currently exist on disk, and
    this needs an exact by-code lookup, not similarity search, so the missing
    index is not in this function's way at all.
    """
    path = CORPUS_CHUNKS_DIR / "metadata.json"
    if not path.exists():
        raise FileNotFoundError(f"corpus chunk metadata missing: {path}")
    chunks = json.loads(path.read_text(encoding="utf-8"))
    return {
        chunk["kompetenz_code"]: chunk["text"]
        for chunk in chunks
        if chunk.get("content_type") == "kompetenz" and chunk.get("anlage") == "2"
    }


def rule(rule_id: str) -> Rule:
    for candidate in load_ruleset().rules:
        if candidate.id == rule_id:
            return candidate
    raise KeyError(f"unknown rule id: {rule_id}")
