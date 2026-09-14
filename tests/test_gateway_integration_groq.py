"""One real call against the Groq backend specifically -- never runs by
default. The Mistral equivalent (test_gateway_integration.py) is coupled to
whichever provider is DEFAULT_PROVIDER; this one pins provider="groq"
explicitly instead, so it stays meaningful regardless of which backend is
the default at any given time.

Added as Groq's fallback role only makes sense if it is actually verified
to work end-to-end, not just registered (gateway/backends/groq.py,
tests/test_gateway_model_registry.py covers registration/protocol
satisfaction with a fake, not a real call).
"""
from __future__ import annotations

import os

import pytest

from checks.catalogue import load_anlage_2_text
from checks.llm.kompetenz_candidates import candidate_kompetenzen
from gateway.model_gateway import classify_kompetenz

pytestmark = pytest.mark.skipif(
    not os.environ.get("GROQ_API_KEY"),
    reason="GROQ_API_KEY not set -- this test makes a real call to Groq's API",
)


def test_classify_kompetenz_returns_codes_confined_to_the_candidate_set() -> None:
    teilaufgabe_text = (
        "Planen Sie 3 Schritte fuer ein Beratungsgespraech mit der Tochter von Frau Ostermann "
        "zur Frage des Umzugs in eine Pflegeeinrichtung, unter Beruecksichtigung ihres Wunsches, "
        "moeglichst selbststaendig zu bleiben."
    )
    candidates = candidate_kompetenzen(["CE 09"])
    result = classify_kompetenz(teilaufgabe_text, candidates, kompetenz_text=load_anlage_2_text(), provider="groq")

    assert isinstance(result, list)
    assert set(result) <= set(candidates)
