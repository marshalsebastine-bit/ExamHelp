"""The provider-agnostic model gateway.

Everything outside this module -- checks/llm/komp_01.py (via its injected
``classify`` parameter), every test, the README -- talks to
``classify_kompetenz`` here, never to a specific backend. This module owns:
which backend is active (``get_backend``, via ``MODEL_PROVIDER``), the
prompt this task sends, and parsing/validating what comes back. A backend
(gateway/backends/*.py) owns only "one prompt in, one string out" for its
provider; everything task-shaped lives here exactly once, so it does not
have to be re-implemented per provider.

**Adding a new provider:** write a class implementing
``gateway.base.ModelBackend`` under gateway/backends/, add it to ``BACKENDS``
below. Nothing else in this file, and nothing outside gateway/, changes.
"""
from __future__ import annotations

import json
import os

from gateway.base import ModelBackend
from gateway.cache import cached_call

BACKENDS: dict[str, type] = {}


def _register_default_backends() -> None:
    # Imported inside a function rather than at module level, so a backend
    # that a caller never selects still doesn't have to be imported before
    # its class object is needed. Both mistralai and groq are unconditional
    # entries in requirements.txt, though (not optional extras), so both
    # SDKs are expected to be installed together, same footing as Mistral
    # alone had before this second backend existed.
    from gateway.backends.groq import GroqBackend
    from gateway.backends.mistral import MistralBackend

    BACKENDS["mistral"] = MistralBackend
    BACKENDS["groq"] = GroqBackend


_register_default_backends()

DEFAULT_PROVIDER = "mistral"

PROMPT_TEMPLATE = """\
Du bewertest eine Teilaufgabe einer staatlichen Pflegeprüfung (PflAPrV Anlage 2).
{fallsituation_block}
Teilaufgabe:
\"\"\"{text}\"\"\"

Wähle aus der folgenden Liste ausschließlich die Kompetenzcodes, die diese \
Teilaufgabe tatsächlich prüft. Wähle keinen Code, der nicht in der Liste steht, \
und erfinde keinen eigenen Code. Wenn keiner der Codes passt, gib eine leere Liste zurück.

Kompetenzen:
{kompetenzen}

Antworte ausschließlich mit JSON in der Form {{"codes": ["<code>", ...]}}.
"""


def get_backend(provider: str | None = None) -> ModelBackend:
    """Resolve which backend to talk to.

    Precedence: explicit ``provider`` argument, then the ``MODEL_PROVIDER``
    environment variable, then ``DEFAULT_PROVIDER``. Model names are a
    separate axis (each backend reads its own env var, e.g.
    ``MISTRAL_MODEL``) -- provider and model do not have to change together.
    """
    name = provider or os.environ.get("MODEL_PROVIDER") or DEFAULT_PROVIDER
    try:
        backend_cls = BACKENDS[name]
    except KeyError:
        raise ValueError(f"unknown MODEL_PROVIDER {name!r}; registered backends: {sorted(BACKENDS)}") from None
    return backend_cls()


def _build_prompt(
    teilaufgabe_text: str,
    candidates: list[str],
    kompetenz_text: dict[str, str],
    *,
    fallsituation_text: str | None = None,
) -> str:
    kompetenzen = "\n".join(f"- {code}: {kompetenz_text.get(code, '(kein Text verfügbar)')}" for code in candidates)
    fallsituation_block = (
        f'\nFallsituation, auf die sich diese Teilaufgabe bezieht:\n"""{fallsituation_text}"""\n'
        if fallsituation_text
        else ""
    )
    return PROMPT_TEMPLATE.format(text=teilaufgabe_text, kompetenzen=kompetenzen, fallsituation_block=fallsituation_block)


def classify_kompetenz(
    teilaufgabe_text: str,
    candidates: list[str],
    *,
    kompetenz_text: dict[str, str],
    fallsituation_text: str | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> list[str]:
    """Ask the active backend which of ``candidates`` the Teilaufgabe tests.

    ``fallsituation_text`` is the owning Aufgabe block's case scenario, given
    as extra context: a Teilaufgabe's own text often only makes sense read
    against it (e.g. "Erläutern Sie anhand der Fallsituation..."), and
    without it the model has to guess at details the Teilaufgabe never
    restates. Optional because a draft's Fallsituation may not be written
    yet -- omitting it falls back to the original text-only prompt.

    Cached on (text, candidates, fallsituation_text, provider, model) so
    repeated dev/test runs against the same Teilaufgabe don't re-pay for the
    call. The result is filtered to ``candidates`` before returning --
    defense in depth: the prompt already constrains the model to this list,
    but a check must never trust raw model output on its own, prompt
    constraints included.
    """
    if not candidates:
        return []

    resolved_provider = provider or os.environ.get("MODEL_PROVIDER") or DEFAULT_PROVIDER
    backend = get_backend(resolved_provider)
    resolved_model = model or getattr(backend, "model", None)
    cache_key = {
        "text": teilaufgabe_text,
        "candidates": sorted(candidates),
        "fallsituation_text": fallsituation_text,
        "provider": resolved_provider,
        "model": resolved_model,
    }

    def compute() -> list[str]:
        prompt = _build_prompt(teilaufgabe_text, candidates, kompetenz_text, fallsituation_text=fallsituation_text)
        raw = backend.complete(prompt, json_mode=True, temperature=0.0)
        try:
            parsed = json.loads(raw)
            codes = parsed.get("codes", [])
        except (json.JSONDecodeError, AttributeError):
            codes = []
        return sorted(set(codes) & set(candidates))

    return cached_call("kompetenz", cache_key, compute)
