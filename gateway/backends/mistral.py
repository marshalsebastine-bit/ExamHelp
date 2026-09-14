"""Mistral AI backend: one implementation of gateway.base.ModelBackend.

Everything Mistral-specific lives here -- the SDK import, the API key env
var, the JSON-mode request shape. gateway/model_gateway.py never imports
``mistralai`` directly; it only ever calls ``.complete()``.

Loads a local ``.env`` (gitignored, see README) into the environment on
import, so ``MISTRAL_API_KEY``/``MISTRAL_MODEL`` don't have to be exported by
hand every session. ``load_dotenv()`` never overrides a variable already set
in the real environment, so an explicit ``export`` still wins.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# Not the original default: mistral-small-latest returned 429 rate_limited
# on every single call under this project's free-tier key (2026-09-14),
# while the console showed an active plan, an active key, and non-zero
# published limits -- i.e. specifically that model was rate-limited to
# zero for this key/tier, not the account as a whole. open-mixtral-8x7b
# hit the same wall; open-mistral-7b, ministral-3b/8b-latest, mistral-tiny,
# open-mistral-nemo and codestral-latest all worked immediately, JSON mode
# included. open-mistral-nemo was picked from that working set: Apache-2.0
# genuinely open-weight (mistral-small-latest was not), 12B, a reasonable
# capability level for this task. If a future key's free tier rejects this
# one too, re-run the same probe against the working-model list above
# before assuming the account itself is broken.
DEFAULT_MODEL = "open-mistral-nemo"


class MistralBackend:
    """Reads MISTRAL_API_KEY / MISTRAL_MODEL from the environment.

    The client is constructed lazily, on first ``complete()`` call, not in
    ``__init__``: constructing a backend (e.g. for provider selection, or in
    a test that never calls it) must not require a key to already be set.
    """

    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.environ.get("MISTRAL_MODEL") or DEFAULT_MODEL
        self._client = None

    def _get_client(self):
        if self._client is None:
            from mistralai.client import Mistral

            api_key = os.environ.get("MISTRAL_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "MISTRAL_API_KEY is not set. Get one at https://console.mistral.ai/ -- the free "
                    "Experiment tier covers this PoC's volume, but check current rate limits on the "
                    "console before relying on it for anything beyond dev/test."
                )
            self._client = Mistral(api_key=api_key)
        return self._client

    def complete(self, prompt: str, *, json_mode: bool = False, temperature: float = 0.0) -> str:
        client = self._get_client()
        response = client.chat.complete(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"} if json_mode else None,
            temperature=temperature,
        )
        return response.choices[0].message.content
