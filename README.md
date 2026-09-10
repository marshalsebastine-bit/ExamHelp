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

`checks/`, `gateway/`, `service/`, `report/` are scaffolded but empty: they are
weeks 2–5.

## The rule catalogue

25 rules across three families, of which **13 need no model at all**.

| File | Family | Rules | Deterministic |
|---|---|---|---|
| [`rules/form.yaml`](rules/form.yaml) | A — Form und Konstruktion | 15 | 10 |
| [`rules/kompetenz.yaml`](rules/kompetenz.yaml) | B — Kompetenzzuordnung | 7 | 3 |
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

## Setup

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest          # 63 tests, no network, no model
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
