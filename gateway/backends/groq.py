"""Groq backend: the second implementation of gateway.base.ModelBackend.

Added so a rate-limited Mistral key (tech doc Sec 6.1's original plan, before
the mid-Week-2 switch to Mistral -- see the tech doc's Sec 6.1 update note)
has a fallback: set ``MODEL_PROVIDER=groq`` to switch, no call-site changes
anywhere in checks/llm/ or the tests (tests/test_gateway_model_registry.py
proves this holds for any registered backend). Groq's chat-completions API
is OpenAI-compatible, so this mirrors mistral.py's shape closely; the two
backends are not identical because their SDKs are not identical (different
client construction, different JSON-mode incantation).

Loads the same local ``.env`` as mistral.py (idempotent: python-dotenv's
``load_dotenv()`` is safe to call from more than one module).
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# The model tech doc Sec 6.1 originally specified: the larger of two
# open-weight candidates, chosen so a weak PoC result could be attributed to
# the approach rather than the model. Configurable via GROQ_MODEL, same
# "model names are configuration" rule as MISTRAL_MODEL.
DEFAULT_MODEL = "openai/gpt-oss-120b"


class GroqBackend:
    """Reads GROQ_API_KEY / GROQ_MODEL from the environment.

    Client construction is lazy, on first ``complete()`` call, not in
    ``__init__`` -- same reasoning as MistralBackend: constructing a backend
    for provider selection or in a test that never calls it must not require
    a key to already be set.
    """

    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.environ.get("GROQ_MODEL") or DEFAULT_MODEL
        self._client = None

    def _get_client(self):
        if self._client is None:
            from groq import Groq

            api_key = os.environ.get("GROQ_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "GROQ_API_KEY is not set. Get one at https://console.groq.com/ -- the free "
                    "tier publishes its RPM/RPD limits; check current numbers on the console "
                    "before relying on it for anything beyond dev/test."
                )
            self._client = Groq(api_key=api_key)
        return self._client

    def complete(self, prompt: str, *, json_mode: bool = False, temperature: float = 0.0) -> str:
        client = self._get_client()
        response = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"} if json_mode else None,
            temperature=temperature,
        )
        return response.choices[0].message.content
