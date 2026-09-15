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
from datetime import datetime, timezone
from pathlib import Path

from gateway.base import ModelBackend
from gateway.cache import cached_call

BACKENDS: dict[str, type] = {}

LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
_log_path: Path | None = None


def _get_log_path() -> Path:
    """One log file per process, created lazily on the first real model call.

    Not the response cache (gateway/cache.py) -- this is a plain, append-only,
    human-readable transcript for manual inspection (tech doc 6.5's "German
    quality is an assumption to test, not to hold" applies to every
    judgement-type check, not just KOMP-01), never read back by any check.
    Same "regenerable, not a deliverable" posture as scripts/smoke_run.py's
    own logs/ output -- logs/ is gitignored.
    """
    global _log_path
    if _log_path is None:
        LOG_DIR.mkdir(exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        _log_path = LOG_DIR / f"model_gateway_calls_{stamp}.txt"
    return _log_path


def _log_call(task: str, *, provider: str, model: str | None, prompt: str, response: str) -> None:
    """Append one real model call's exact prompt and raw response to the log.

    Called once per cache *miss* (i.e. once per actual network call) from
    each task function's ``compute()`` -- a cache hit already has a logged
    entry from whenever it was first computed, so logging it again would
    just be noise, not a more complete record.
    """
    entry = (
        f"{'=' * 88}\n"
        f"timestamp: {datetime.now(timezone.utc).isoformat()}\n"
        f"task: {task}\n"
        f"provider: {provider}\n"
        f"model: {model}\n"
        f"{'-' * 88}\n"
        f"PROMPT:\n{prompt}\n"
        f"{'-' * 88}\n"
        f"RESPONSE:\n{response}\n\n"
    )
    with _get_log_path().open("a", encoding="utf-8") as f:
        f.write(entry)


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
        _log_call("classify_kompetenz", provider=resolved_provider, model=resolved_model, prompt=prompt, response=raw)
        try:
            parsed = json.loads(raw)
            codes = parsed.get("codes", [])
        except (json.JSONDecodeError, AttributeError):
            codes = []
        return sorted(set(codes) & set(candidates))

    return cached_call("kompetenz", cache_key, compute)


FORM_07_PROMPT_TEMPLATE = """\
Du prüfst die Konstruktion einer Prüfungsaufgabe (staatliche Pflegeprüfung, PflAPrV Anlage 2). \
Es gibt hier keinen Prüfling und keine Prüfungsleistung zu beurteilen.

WICHTIG -- was ein Erwartungshorizont ist: eine Korrekturhilfe in Stichpunktform. Er ist IMMER \
knapp und listenförmig notiert, auch bei anspruchsvollen Operatoren. Knappheit oder Listenform \
sind daher NIEMALS ein Hinweis auf einen Widerspruch. Entscheidend ist allein, welche ART von \
Leistung die Stichpunkte inhaltlich bepunkten.

Zu prüfende Regel: {rule_text}

Teilaufgabe (die Aufgabenstellung, wie ein Prüfling sie liest):
\"\"\"{teilaufgabe_text}\"\"\"

Erkannter Operator der Teilaufgabe: {operator_liste} ({anforderungsbereich_beschreibung}).

Erwartungshorizont (die bepunkteten Erwartungspunkte):
\"\"\"{erwartungshorizont_text}\"\"\"

Beispiel A (Widerspruch): Operator 'nennen' (bloßes Aufzählen), der Erwartungshorizont verlangt \
"Begründen Sie, warum ..." -> mismatch=true, denn der Erwartungshorizont fordert eine \
Begründungsleistung, die die Teilaufgabe gar nicht verlangt.
Beispiel B (KEIN Widerspruch): Operator 'begründen', der Erwartungshorizont notiert stichpunktartig \
"Maßnahme X, weil Y" -> mismatch=false, denn das "weil" bepunktet genau die Begründung; die knappe \
Notation ändert daran nichts.

Prüfe: Bepunktet der Erwartungshorizont eine ANDERE Art von Leistung als der Operator verlangt? \
Im Zweifel mismatch=false. Setze mismatch=true nur, wenn du einen konkreten Stichpunkt wörtlich \
zitieren kannst, der eine andere Leistungsart bepunktet.

Tonfall der Begründung: Du berätst die Autorin oder den Autor der Aufgabe, du benotest nicht. \
Beschreibe sachlich, was die Teilaufgabe verlangt und was der Erwartungshorizont bepunktet. \
Vermeide Urteile über Qualität wie "Fehler", "fehlerhaft", "mangelhaft", "ungenügend" oder \
"Note". Operatoren dürfen selbstverständlich beim Namen genannt werden -- "eine Bewertung \
fehlt" ist eine sachliche Beschreibung, wenn der Operator 'bewerten' lautet.

Antworte ausschließlich mit JSON in der Form {{"beleg_zitat": "<wörtliches Zitat aus dem \
Erwartungshorizont oder leer>", "mismatch": <true|false>, "begruendung": "<ein sachlicher Satz>"}}.
"""


def _build_form_07_prompt(
    teilaufgabe_text: str,
    teilaufgabe_operatoren: list[str],
    erwartungshorizont_text: str,
    *,
    operators: dict[str, list[str]],
    rule_text: str,
) -> str:
    operator_liste = ", ".join(repr(op) for op in teilaufgabe_operatoren)
    anforderungsbereiche = sorted({level for op in teilaufgabe_operatoren for level in operators.get(op, [])})
    anforderungsbereich_beschreibung = (
        f"Anforderungsbereich {', '.join(anforderungsbereiche)}" if anforderungsbereiche else "Anforderungsbereich unbekannt"
    )
    return FORM_07_PROMPT_TEMPLATE.format(
        rule_text=rule_text.strip(),
        teilaufgabe_text=teilaufgabe_text,
        operator_liste=operator_liste,
        anforderungsbereich_beschreibung=anforderungsbereich_beschreibung,
        erwartungshorizont_text=erwartungshorizont_text,
    )


def judge_form_07(
    teilaufgabe_text: str,
    teilaufgabe_operatoren: list[str],
    erwartungshorizont_text: str,
    *,
    operators: dict[str, list[str]],
    rule_text: str,
    provider: str | None = None,
    model: str | None = None,
) -> dict:
    """FORM-07: does the Erwartungshorizont reward the performance the
    Teilaufgabe's own operator actually demands?

    Returns ``{"mismatch": bool, "beleg_zitat": str, "begruendung": str}``.

    **This prompt's exact wording is load-bearing and was arrived at by
    measurement, not taste** -- see docs/week3-form07-quality-spot-check.md §3
    for the numbers. Measured against the corpus's own ground truth
    (items/manifest.json's ``known_weaknesses``: C-02 ag.1.ta.1 is the one
    planted FORM-07 defect; A-01/A-02/A-03 carry none), an earlier version of
    this prompt scored 1 true positive but **23 false positives out of 25
    labelled-clean Teilaufgaben**. This version, same model
    (``open-mistral-nemo``) and same items, scores 1 true positive and **0
    false positives**. Three things in here cause that difference, so do not
    quietly drop any of them:

    1. **Both examples, not just the mismatch one.** The earlier prompt gave
       one worked example -- a mismatch -- and none of a legitimate match.
       The model then echoed that example's own vocabulary back as
       justification for false positives, at one point asserting an
       Erwartungshorizont had "keine Ursache-Wirkungs-Zusammenhänge" about
       text that literally read "..., weil erhaltene Mobilität die
       Selbstversorgung trägt". One-sided priming, not a model limitation.
    2. **Saying what an Erwartungshorizont *is*.** It is a marking scheme in
       note form: always terse, always list-shaped, even for
       Anforderungsbereich-III operators. Without being told that, the model
       read normal note-form brevity as missing cognitive depth and flagged
       essentially everything.
    3. **Requiring a quote, and defaulting to false.** ``beleg_zitat`` makes
       the model point at the specific Erwartungspunkt it objects to. This is
       the project's own "no flag without evidence" rule
       (schemas/flag.py) applied one step earlier -- to the reasoning step,
       not only to the Flag built afterwards. ``checks/llm/form_07.py``
       enforces it structurally: no quote, no flag.

    The Teilaufgabe's own operator is *given* to the model, not asked of it --
    it comes from the deterministic, already-verified
    ``checks/deterministic/form_operators.py::find_operator_matches``. An even
    earlier version asked the model to derive that too and it misread an
    explicit "Beschreiben Sie" as "Aufzählung", which a keyword match never
    gets wrong.

    The advisory register ("flags advise, they never grade", tech doc 1.5.4)
    is this prompt's responsibility -- the "Tonfall" paragraph. There is no
    longer a word-list validator on ``Flag.finding`` to catch a slip: one used
    to exist and it rejected a *correct* finding because "Bewertung" is both
    grading vocabulary and the honest name for what the catalogue operator
    "bewerten" demands. A wrong word occasionally reaching the author is the
    better failure than a correct finding never reaching them.

    Cached on (teilaufgabe_text, teilaufgabe_operatoren, erwartungshorizont_text, provider, model).

    Malformed model output degrades to no mismatch rather than raising -- a
    judgement call defaulting to "no flag" on a parse failure is the same
    posture ``classify_kompetenz`` takes for unparseable output (empty codes).
    """
    resolved_provider = provider or os.environ.get("MODEL_PROVIDER") or DEFAULT_PROVIDER
    backend = get_backend(resolved_provider)
    resolved_model = model or getattr(backend, "model", None)
    cache_key = {
        "teilaufgabe_text": teilaufgabe_text,
        "teilaufgabe_operatoren": sorted(teilaufgabe_operatoren),
        "erwartungshorizont_text": erwartungshorizont_text,
        "provider": resolved_provider,
        "model": resolved_model,
    }

    def compute() -> dict:
        prompt = _build_form_07_prompt(
            teilaufgabe_text, teilaufgabe_operatoren, erwartungshorizont_text, operators=operators, rule_text=rule_text
        )
        raw = backend.complete(prompt, json_mode=True, temperature=0.0)
        _log_call("judge_form_07", provider=resolved_provider, model=resolved_model, prompt=prompt, response=raw)
        try:
            parsed = json.loads(raw)
            return {
                "mismatch": bool(parsed.get("mismatch", False)),
                "beleg_zitat": str(parsed.get("beleg_zitat") or ""),
                "begruendung": str(parsed.get("begruendung") or ""),
            }
        except (json.JSONDecodeError, AttributeError):
            return {"mismatch": False, "beleg_zitat": "", "begruendung": ""}

    return cached_call("form_07", cache_key, compute)
