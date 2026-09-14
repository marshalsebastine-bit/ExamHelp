# ExamHelp — KI-gestütztes Flagging von Prüfungsaufgaben

A flagging tool for German nursing-exam Aufsichtsarbeiten (case-based written exam
items). It checks a drafted item against a rule catalogue derived from binding and
semi-official German sources and produces **flags** — never scores, never gates,
never automatic rewrites. Every flag carries the rule it derives from and a quoted
source.

Primary user: the Prüfungsausschuss members who *author* items, during drafting.
Secondary: whoever reviews an item before submission.

**This is a proof of concept.** It validates a mechanism. It is not deployable
infrastructure, it is not DSGVO/BSI-compliant, and it must not be used with real
exam content — every input in this repository is synthetic, which is what makes
the free-tier, non-EU model providers acceptable at all.

## Specification

The two planning documents are the specification; this README is a map.

- [`docs/planning/pflege-aufgaben-flagging-poc.md`](docs/planning/pflege-aufgaben-flagging-poc.md) — the technical plan.
- [`docs/planning/examhelp-repo-review.md`](docs/planning/examhelp-repo-review.md) — audit of the phase-1 code against that plan.
- [`docs/week1-results.md`](docs/week1-results.md) — what week 1 built, what it found, and what is still open.

## Layout

```
rules/          the rule catalogue and its lookup tables. Data, not code.
schemas/        Pydantic models: Aufgabe, Flag, RuleSet
corpus/         raw sources, structure-aware ingestion, chunked output, retrieval
items/          12 synthetic base Aufsichtsarbeiten, as JSON
checks/         deterministic/ one module per rule · llm/ one prompt per rule
gateway/        model interface, backends, cache
service/        stateless JSON-in/JSON-out entry point over the check runner
docio/          .docx read + comment writeback; Word template spec
report/         Jinja2 templates, golden-file tests
eval/           retrieval eval; mutation harness
mutations/      generated variants + ground truth (gitignored, seed-reproducible)
scripts/        one-shot migrations and corpus builds
docs/           planning documents and results
```

`service/`, `report/` are scaffolded but empty: they are weeks 2–5. `checks/`
and `gateway/` are no longer empty: `checks/llm/komp_01.py` derives a
Teilaufgabe's Anlage-2 competencies via `gateway/model_gateway.py` (a
provider-agnostic gateway, Mistral AI the default backend), and
`checks/deterministic/komp_03.py`/`komp_06.py`/`komp_04.py` read the result
(the last independently, not from KOMP-01's output). See "Model gateway"
below and "Runner" further down.

All 11 deterministic Family A (Form und Konstruktion) rules are implemented,
grouped by shared mechanism rather than one-module-per-rule:
`checks/deterministic/form_operators.py` (FORM-03/04/11/13, all built on the
same operator-extraction step — see its docstring for why that needs more
than a literal lookup against `rules/operators.yaml`), `form_punkte.py`
(FORM-02/06/16, Punkte arithmetic), `form_sprache.py` (FORM-05/12/14/15,
linguistic-pattern checks on Fallsituation/Teilaufgabe prose). All eleven are
verified against the 12 real items in `items/`, not just synthetic
fixtures — `items/manifest.json`'s `known_weaknesses` is the ground truth
for what each should and should not catch. Together with KOMP-03/03B/04/06,
this is **every `check_type: deterministic` rule in the catalogue** —
`load_ruleset().counts` confirms 15/15. The four `llm`-typed FORM rules
(07/08/09/10), the one `hybrid` FORM rule (01), and Family B's KOMP-05
(hybrid) / KOMP-07 (llm) are not yet implemented; KOMP-02 is retired, not
pending (see `rules/kompetenz.yaml`'s migration note).
`checks/deterministic/_german_text.py` is a shared, private helper: the
corpus is written almost entirely in the ae/oe/ue/ss ASCII transliteration
of ä/ö/ü/ß, so every regex in these modules has to tolerate both spellings.

## The item model

One Aufsichtsarbeit is one 120-minute paper for one Prüfungsbereich, composed of
**exactly two Aufgabe blocks** ("Aufgabe 1" / "Aufgabe 2") — each with its own
Fallsituation and its own Teilaufgaben, sharing one Bearbeitungszeit and one
Punktzahl budget (PflAPrV § 14 (1)–(3)). Anchors are `ag.<N>.ta.<M>` /
`ag.<N>.ta.<M>.eh.<K>`. The curriculare-Einheit claim and its Situationsmerkmale
live per Teilaufgabe (`teilaufgaben.situationsmerkmale.curriculare_einheit`),
not per Aufgabe block. See `schemas/aufgabe.py`.

## The rule catalogue

27 rules across three families (24 runnable — 2 in Family C are `blocked_on` an
unacquired source, and 1 in Family B, KOMP-02, is retired: its premise needs an
author-facing competency claim this schema no longer has), of which **15 need
no model at all**.

| File | Family | Rules | Deterministic |
|---|---|---|---|
| [`rules/form.yaml`](rules/form.yaml) | A — Form und Konstruktion | 16 | 11 |
| [`rules/kompetenz.yaml`](rules/kompetenz.yaml) | B — Kompetenzzuordnung | 8 | 4 |
| [`rules/quellenbindung.yaml`](rules/quellenbindung.yaml) | C — Quellenbindung | 3 | 0 |

Lookup tables the rules read, all generated from primary sources and frozen to
reviewed YAML:

| File | Contents | Derived from |
|---|---|---|
| [`rules/kompetenzen.yaml`](rules/kompetenzen.yaml) | 85 Anlage-2 and 79 Anlage-1 competency codes; 11 curriculare Einheiten with Zeitrichtwerte | PflAPrV Anlagen 1–2 · Bavarian Lehrplan |
| [`rules/operators.yaml`](rules/operators.yaml) | 27 operators across Anforderungsbereiche I–III | PflegePlus Handreichung 01 |
| [`rules/pruefungsbereiche.yaml`](rules/pruefungsbereiche.yaml) | the three written Prüfungsbereiche and their Kompetenzschwerpunkte | PflAPrV § 14 (1) |
| [`rules/situationsmerkmale.yaml`](rules/situationsmerkmale.yaml) | Situationsmerkmale per CE | Bavarian Lehrplan |

A rule change is a YAML edit. It never requires a code change.

## Model gateway

KOMP-01 (`checks/llm/komp_01.py`) is the one rule so far that calls a model:
it derives which Anlage-2 Einzelkompetenzen a Teilaufgabe tests, choosing
among a deterministically-built candidate set (`checks/llm/kompetenz_candidates.py`,
from the Teilaufgabe's curriculare Einheit) rather than free-form.

The call is behind a **provider-agnostic gateway**, deliberately, so the
underlying API partner can change without touching anything outside
`gateway/`:

- `gateway/base.py` — `ModelBackend`, the entire interface a provider must
  implement: one method, `complete(prompt) -> str`.
- `gateway/backends/mistral.py` — the default backend. Mistral-specific
  concerns (the SDK, the API key, the JSON-mode request shape) live here and
  nowhere else.
- `gateway/backends/groq.py` — second backend, added so a rate-limited or
  down Mistral key has a fallback (`gpt-oss-120b`, tech doc §6.1's original
  model choice before the mid-Week-2 switch to Mistral). Same shape as
  `mistral.py`; Groq's chat-completions API is OpenAI-compatible.
- `gateway/model_gateway.py` — `classify_kompetenz`, the task-level function
  everything else calls. Owns the prompt and the response parsing once, not
  once per provider. Resolves which backend to use via `get_backend()` /
  `BACKENDS`, precedence: explicit argument, then `MODEL_PROVIDER`, then the
  default (`"mistral"`).

**Adding a provider:** write a class implementing `ModelBackend` under
`gateway/backends/`, register it in `model_gateway.BACKENDS`. Nothing in
`checks/llm/` or any test changes — `tests/test_gateway_model_registry.py`
proves this with a fake backend.

```bash
export MODEL_PROVIDER=mistral     # optional, default is mistral -- "groq" switches backend
export MISTRAL_API_KEY=...        # required to actually call Mistral
export MISTRAL_MODEL=...          # optional, defaults to mistral-small-latest
export GROQ_API_KEY=...           # required to actually call Groq
export GROQ_MODEL=...             # optional, defaults to openai/gpt-oss-120b
```

Or drop the same variables into a `.env` file at the repo root (gitignored,
never committed) — both `gateway/backends/mistral.py` and `.../groq.py` load
it automatically via `python-dotenv` on import. An explicit `export` still
takes precedence over `.env`.

Switching is currently manual, not automatic failover: set
`MODEL_PROVIDER=groq` when Mistral is rate-limited, back to `mistral`
(or unset) when it recovers. Nothing tries a second backend within one call
if the first fails — that would be a real feature (retry/backoff across
backends is tech doc §5.2's stated design for a production gateway,
explicitly not built yet), not a side effect of registering a second class.

`classify` is injected everywhere it's used (`checks/llm/komp_01.py`'s
`classify` parameter), so nothing in the test suite touches the network by
default — only `tests/test_gateway_integration.py` does, and only when
`MISTRAL_API_KEY` is set (that test is coupled to Mistral specifically since
it exercises `DEFAULT_PROVIDER`, not whichever provider `MODEL_PROVIDER`
currently selects).

Mistral's free "Experiment" tier (console.mistral.ai, phone verification
required to activate) covers this PoC's volume — it is rate-limited and
explicitly for evaluation, not production; confirm current limits on the
console before relying on it for anything beyond dev/test. **Not every
model is actually reachable on it, though**: as of 2026-09-14, this
project's free-tier key returned `429 rate_limited` on *every* call to
`mistral-small-latest` (the original default) and `open-mixtral-8x7b`
specifically, while an active plan, active key and non-zero published
limits showed in the console — i.e. those two models were rate-limited to
zero for this tier, not the account as a whole. `open-mistral-7b`,
`ministral-3b-latest`, `ministral-8b-latest`, `mistral-tiny`,
`open-mistral-nemo` and `codestral-latest` all worked immediately, JSON
mode included; the default is now `open-mistral-nemo` (also a genuinely
open-weight model, unlike `mistral-small-latest`). If a future key hits the
same wall, re-probe that model list with a plain SDK call per model before
assuming the account is broken — Groq (`MODEL_PROVIDER=groq`) is the
fallback either way. Groq's free tier (console.groq.com, no card) publishes
its own RPM/RPD limits, same "confirm on the console, non-EU, prompts may
train the provider's models" caveats as tech doc §6.2 states for Mistral —
acceptable here only because every input is synthetic. Responses are cached
under `build/cache/kompetenz/` (`gateway/cache.py`) so repeated runs against
the same Teilaufgabe don't re-pay for the call, regardless of which
provider answered it.

**Runner:** `checks/runner.py::run_checks` closes the gap above — it runs
KOMP-01 first (populating `teilaufgabe.kompetenzzuordnung_abgeleitet` before
anything reads it), then every other runnable rule, and returns one
`CheckResult`. Every catalogue rule is accounted for one way or another: a
blocked rule (`blocked_on` set) or one with no check function yet reports
`NotChecked` with a clear reason, rather than being silently absent.
`scripts/smoke_run.py` runs it over a 3-item set (A-01 clean, C-03 the
deliberate-defect fixture, D-01 the incomplete draft) and logs the result
under `logs/`.

## Setup

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest          # 152 tests + 1 skipped without MISTRAL_API_KEY, no network by default
```

## Rebuilding the derived data

The YAML in `rules/` is committed and reviewed, so none of this is needed to run
the checks. Re-run it when a source document changes.

```bash
.venv/bin/python scripts/download_sources.py           # refresh PflBG / PflAPrV HTML
.venv/bin/python scripts/build_corpus.py               # chunk the legal corpus (591 chunks)
.venv/bin/python scripts/build_corpus.py --embed       # + dense index (week 4 only)
.venv/bin/python scripts/migrate_operators.py          # -> rules/operators.yaml
.venv/bin/python scripts/extract_lehrplan.py           # -> rules/kompetenzen.yaml, situationsmerkmale.yaml
.venv/bin/python scripts/extract_pruefungsbereiche.py  # -> rules/pruefungsbereiche.yaml
.venv/bin/python scripts/generate_template_spec.py     # -> docio/template_tags.md
```

Nothing at runtime parses a PDF. The extraction scripts are one-shot migration
tools; the check runner reads only the frozen YAML.

## Non-negotiables

Enforced as tests in [`tests/test_catalogue.py`](tests/test_catalogue.py), not as prose.

- **Rules live in YAML, never in Python.**
- **No flag without evidence.** Every flag carries a `rule_id` and a quoted
  source. A check that cannot produce that does not ship — and a rule whose
  source is not yet in the corpus is marked `blocked_on` and does not run.
- **Deterministic first, model second.** The output labels which mechanism
  produced each flag.
- **One prompt per rule**, seeing only the fragment that rule's `input_slice` declares.
- **Every rule ships with its `mutation`**, so the evaluation harness is generated
  from the catalogue and cannot drift from it.
- **`requires` unmet means skip visibly.** Silent skipping is a bug; every unmet
  precondition produces an explicit `NotChecked` entry.
- **Severity derives from source authority.** `blocker` is reserved for binding
  PflAPrV requirements.
- **No real exam content, ever.** A compliance boundary, not a convenience.
- **The docx writer never modifies the input file.**
- **Model names are configuration.** Free-tier catalogues shift monthly.
