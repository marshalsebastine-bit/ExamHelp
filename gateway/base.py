"""The provider-agnostic surface every model backend implements.

Everything outside gateway/ -- checks/llm/komp_01.py, every test, the README
-- talks to gateway/model_gateway.py's task-level functions (e.g.
``classify_kompetenz``), never to a backend directly. A backend's only job is
turning one prompt into one string of model output; provider-specific
concerns (auth, request shape, JSON-mode incantations, SDK client
construction) stay inside the backend that has them. Swapping providers
means writing one new class here and registering it in
gateway/model_gateway.py's ``BACKENDS`` -- nothing above that layer changes.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ModelBackend(Protocol):
    """One provider's chat-completion call, reduced to the one thing every
    task in this codebase actually needs: text in, text out.

    ``json_mode`` asks the backend to constrain its output to valid JSON
    where the provider supports that natively (e.g. Mistral's
    ``response_format``) -- callers still parse and validate the result
    themselves; this is a hint to the provider, not a guarantee.
    """

    def complete(self, prompt: str, *, json_mode: bool = False, temperature: float = 0.0) -> str: ...
