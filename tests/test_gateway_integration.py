"""One real call against whichever backend is currently the default provider
-- never runs by default.

Everything else in this repo's test suite is offline by design (checks/llm's
own tests use a fake classifier, tests/test_gateway_model_registry.py proves
the provider abstraction with a fake backend). This module is the single
exception that hits a real network API, and it stays skipped unless
MISTRAL_API_KEY is set, so `pytest -q` never needs network access or a key,
in this sandbox or in CI.

Coupled to Mistral today only because gateway/model_gateway.py::DEFAULT_PROVIDER
is "mistral" -- if that default ever changes, this test's skip condition and
the key it checks for should move with it.
"""
from __future__ import annotations

import os

import pytest

from checks.catalogue import load_anlage_2_text
from checks.llm.kompetenz_candidates import candidate_kompetenzen
from gateway.model_gateway import classify_kompetenz

pytestmark = pytest.mark.skipif(
    not os.environ.get("MISTRAL_API_KEY"),
    reason="MISTRAL_API_KEY not set -- this test makes a real call to Mistral AI's API",
)


def test_classify_kompetenz_returns_codes_confined_to_the_candidate_set() -> None:
    teilaufgabe_text = (
        "Planen Sie 3 Schritte fuer ein Beratungsgespraech mit der Tochter von Frau Ostermann "
        "zur Frage des Umzugs in eine Pflegeeinrichtung, unter Beruecksichtigung ihres Wunsches, "
        "moeglichst selbststaendig zu bleiben."
    )
    candidates = candidate_kompetenzen(["CE 09"])
    result = classify_kompetenz(teilaufgabe_text, candidates, kompetenz_text=load_anlage_2_text())

    assert isinstance(result, list)
    assert set(result) <= set(candidates)
