# Week 1 results

**Scope:** the seven week-1 tasks in the handdown (tech doc §8, week 1).
**Status:** all seven complete. 124 tests pass with no network and no model call
(63 at week 1's original close; see §6 for the post-week-1 correction that
accounts for the rest).

---

## 1. What was built

| # | Task | Outcome |
|---|---|---|
| 1 | Fix the Anlage chunking defect | Fixed and verified. Chunks cited as `§ 62` dropped from 62 to 2, and both survivors are genuinely § 62. |
| 2 | Freeze the operator table | `rules/operators.yaml`, 28 entries / 27 distinct operators. PDF parsing retired to a one-shot migration. |
| 3 | Extract the Lehrplan taxonomy | `rules/kompetenzen.yaml` (85 Anlage-2 codes, 11 CEs, Zeitrichtwerte), `rules/situationsmerkmale.yaml`. Cross-checked against PflAPrV — see §2.1. |
| 4 | Item schema | `schemas/aufgabe.py`. Every field optional; stable structural IDs; resolves anchors back to elements. |
| 5 | Rule catalogue | 25 rules across three families, 13 deterministic. Plus `schemas/rule.py` and `schemas/flag.py` as the output contract. |
| 6 | 12 synthetic base items | `items/`, 4 exam sets of 3. All 6 Versorgungsbereiche, all 4 Altersgruppen, Prüfungsbereiche 1–3 evenly. |
| 7 | Word template tag spec | `docio/word_template_spec.md`, with the tag table generated from the schema. |

Cleanup from the repo review's remove list is done: FAISS, `chunk_text()`,
`example_rules.yaml`, the `source_id` alias, the unwired config constants, the
`.vscode` noise, and the phase-1 `app/` package are gone. `rag_phase1/` no longer
exists; what was worth keeping moved into `corpus/`, `eval/` and `scripts/` with
git history preserved.

---

## 2. Findings

### 2.1 KOMP-06 can now be a real check, not a demonstration

This was tech doc §12's open verification item, and it turned out to be resolvable
in week 1 because PflAPrV's Anlage 2 is already in the corpus as structured HTML.

Parsing Anlage 2 directly gives **85 competency codes**. The Lehrplan-derived list
the planning session used gives **79** — and this run reproduces both of the
planning doc's figures exactly (79 under Anlage-2 headings, 76 under Anlage-1),
which is good evidence the two extractions are comparable.

The relationship matters more than the counts:

- Every code the Lehrplan cites **does** exist in Anlage 2. The curriculum invents nothing.
- But it is a **strict subset**. Six Anlage-2 competencies are never cited by the
  Lehrplan at the Anlage-2 level: `I.1.a`, `I.1.f`, `I.1.h`, `I.1.i`, `I.2.d`, `I.2.f`.

So KOMP-06 built on the Lehrplan list would have raised a **false flag** against
any item legitimately claiming one of those six — including `I.1.h`, which tech
doc §3.3.1 uses as its own worked example. Since the false-flag rate is the
headline evaluation metric, that would have been a bad way to find out.

KOMP-06 therefore reads `anlage_2_authoritative` in `rules/kompetenzen.yaml`, and
a test pins the count at 85 so an amendment to PflAPrV fails loudly instead of
silently staling the list.

One caveat on what the check catches: exactly **one** code (`I.2.g`) exists in
Anlage 1 but not Anlage 2, so the "claimed a Zwischenprüfungs-Kompetenz" case is
narrow. The common real defect will be a code that exists in neither — a mistyped
or invented reference. Both are set-membership failures and fire the same rule.

### 2.2 KOMP-03 became deterministic

PflAPrV **§ 14 (1)** names, for each of the three written Prüfungsbereiche, the
Kompetenzschwerpunkte it draws on:

| Prüfungsbereich | Kompetenzschwerpunkte | additionally |
|---|---|---|
| 1 | I.1, I.5, I.6, II.1 | Kontextbedingungen of Bereich IV |
| 2 | I.2, II.2, V.1 | — |
| 3 | I.3, I.4, II.3, III.2 | — |

The plan scoped KOMP-03 as a "deterministic aggregate over KOMP-01", i.e. dependent
on the LLM mapping. It does not have to be: coverage is decidable directly against
binding law, which is also why the rule can carry `blocker` severity. Extracted to
`rules/pruefungsbereiche.yaml`.

### 2.3 The operator table had a latent false-flag defect

The repo review verified 26 operator records with zero nulls, which held. What it
did not surface is that **one source row carries three operators** —
`Operator entwickeln, planen, ableiten` — sharing a single description. Phase 1
stored that as one record keyed on the literal string `"entwickeln, planen, ableiten"`.

A FORM-03 lookup for `planen` would therefore have missed and flagged a perfectly
valid operator as not-on-the-list. Now split into one entry per operator, with
`source_row` recording the grouping. Two consequences for the checks:

- 28 entries, 27 distinct operators.
- `ableiten` legitimately appears at **two** Anforderungsbereiche (II and III), so
  FORM-04 must pass if the declared level matches *any* of an operator's levels,
  not the first one found.

### 2.4 Corrections to the planning documents

None of these change a decision; they correct facts the documents assert.

| Document | Claim | Actual |
|---|---|---|
| tech doc §3.2.1, handdown §5.3 | The Lehrplan "is plain UTF-8 text (~19,300 lines), not a PDF, despite the extension" | It **is** a PDF (v1.6, 507 pages). No `.txt` copy exists. `pypdf` extracts it cleanly, and the documented cleaning quirks still apply. The ~19,300-line figure matches a text extraction of it (this run: 21,417 lines). |
| tech doc §3.2.1 | "691 code occurrences across 88 unique codes" | Correct for the **whole document** — but that includes the Anlage 3 (Kinderkrankenpflege) and Anlage 4 (Altenpflege) curricula the same section says to filter out. Generalistische part only: **370 occurrences, 84 unique**. |
| repo review §4.2 | The StMUK operator list is skipped because of a magic character offset | The offset is real, but **§ 3.1 is scanned images** — 1 character of extractable text across its three pages. Fixing the offset recovers nothing; the list needs OCR or first-hand acquisition. |
| tech doc §3.2.1 | Zeitrichtwerte "from 50 to 200 hours" | 60 to 200 hours; eleven CEs totalling 1260 h. The "eight continuing into the third Ausbildungsdrittel" figure is confirmed exactly. |
| tech doc §3.2.1 | Situationsmerkmale include `Akteure` "alongside" the three | Confirmed as written, and worth making explicit: only **Handlungsanlässe, Kontextbedingungen and Handlungsmuster** are structured as table rows per CE. Akteure and Erleben/Deuten/Verarbeiten are prose in the introduction and the didaktischer Kommentar, so KOMP-07 can only compare the three structured dimensions. The item schema keeps an `akteure` field regardless, because authors do describe who appears in a case. |

### 2.5 Two smaller things worth knowing

**Sentence anchoring.** Anchor accuracy is a measured metric (§7.3), and a naive
split on `". "` puts a false sentence boundary inside `Frau K. ist 82 Jahre alt`
and `z. B.` — both saturate this domain, and every false boundary shifts the
anchors after it. `Fallsituation.saetze()` handles initials and a German
abbreviation list.

**The evidence rule needed an escape hatch that fails loudly.** QUELL-01 and
QUELL-02 depend on the DNQP Expertenstandard, which is not acquired. Rather than
give them a placeholder quote, `Rule.blocked_on` marks them unshippable and
`RuleSet.runnable` excludes them. The catalogue reports 25 rules, 23 runnable.

---

## 3. Scope flag: 25 rules, not ~20

The handdown asks for this to be raised by day 3 rather than discovered in week 4.

The plan targets ~20 (A ≈ 10, B 7, C 2–3). The catalogue has **25**: Family A grew
to 15 because the 27-item checklist yielded five more genuinely deterministic
rules — FORM-11 (one operator, at the sentence start), FORM-12 (digits not number
words), FORM-13 (count of expected answers given), FORM-14 (active voice),
FORM-15 (indicative). The repo review anticipated this (§6.2: Family A "can
plausibly reach 15–20 rules with genuine source backing").

Why I let it grow rather than trimming to 20:

- All five are regex-or-lookup checks against a cited source. Each is roughly an
  hour of week-2 work plus a unit test, not a prompt to iterate on.
- They shift the deterministic share to **13 of 25**, so "more than half the
  checks require no model at all" is now literally true rather than nearly true.
- They add nothing to the week-3 LLM budget, which is the scarce resource.

**If that is the wrong call, the five to cut are FORM-11 through FORM-15**, and
cutting them costs no other rule. Family A then has 10 rules and the total is 20,
exactly as planned. This is a scope decision, so it is yours rather than mine —
say the word and I will trim.

---

## 4. Open items

Blocking nothing this week; several block later weeks.

| Item | Blocks | Note |
|---|---|---|
| **DNQP Mobilität-Expertenstandard not acquired** | QUELL-01, QUELL-02 (week 4) | Free full text from gs-qsa-pflege.de. Marked `blocked_on`; the rules exist but will not run. |
| **Official Bay. StMUK Operatorenliste** | FORM-03/04 provenance | Currently standing on the third-party extended list, tagged `binding_status: unverified`. § 3.1 of the Handreichung is images, so this needs a request to StMUK. |
| **PflegePlus licence** | shipping the corpus | Both Handreichungen are **already committed to this repository** (they were committed before week 1) with the licence unresolved. Their prose and example pairs are held out of the retrieval corpus and out of all prompts, since prompt content reaches non-EU providers. Family A rule text is independently worded and cites rather than reproduces. Worth resolving early — the review's §5 argument that Anna Kamm at Diakoneo is a plausible ally rather than an obstacle still stands. |
| **Lehrplan version currency** | taxonomy validity | July 2020, declared binding "zur Erprobung". Confirm with ISB Bayern that no revision followed. |
| **Free-tier availability of `gpt-oss-120b`** | week 2 gateway | Not re-verified this week; no model call has been made yet. Verify before building the gateway. |
| **Situationsmerkmale extraction quality** | KOMP-07 (week 3) | Extracted from a PDF table set in narrow columns. All 11 CEs have content on all three structured dimensions, but it needs a spot review against the document before KOMP-07 is scored. |
| **MCP connectors unauthorised** | nothing yet | Gmail, Miro and Notion connectors are configured but not authorised, and this session cannot run the OAuth flow. Authorise via claude.ai connector settings if any of them is meant to be used. |

---

## 5. Week 2 entry conditions

Everything week 2 depends on is in place: the item schema validates all 12
synthetic items including the unfinished draft, the catalogue validates and every
rule carries a mutation, the lookup tables the ten deterministic Family A checks
need are frozen and tested, and the output contract (`Flag`, `NotChecked`,
`CheckResult`) is defined so the runner and its consumers can be built against it
rather than around it.

The one thing to do before writing the gateway is the free-tier verification in
§4, since the token-budget arithmetic in tech doc §6.3 assumes it.

---

## 6. Post-week-1 correction: the two-Aufgabe-block structure (2026-09-10)

Before starting week 2, a review of why every file exists surfaced that the
week-1 item schema modelled **one** Fallsituation per Aufsichtsarbeit. That is
wrong: a candidate's 120-minute paper for one Prüfungsbereich is composed of
**two independently-themed Aufgabe blocks** ("Aufgabe 1" / "Aufgabe 2" — the
Prüfungsausschuss's own terms), each with its own Fallsituation, its own
`ce_bezug`, and its own Teilaufgaben, sharing one Bearbeitungszeit and one
Punktzahl budget. Confirmed against domain knowledge, not derivable from
PflAPrV's text: § 14 fixes the Aufsichtsarbeit–Prüfungsbereich correspondence
and the 120-minute/three-Werktage administration, but says nothing about an
internal two-block split, so this is a Land/school-level practice this
project's corpus did not otherwise have access to.

This is a correction to a week-1 foundational assumption, not a week-2 feature,
so it was fixed before week 2 could build checks on top of the wrong shape.

### What changed

- **`schemas/aufgabe.py`** — new `Aufgabe` model (`ce_bezug`, `fallsituation`,
  `teilaufgaben`); `Aufsichtsarbeit.aufgaben: list[Aufgabe]` replaces the old
  top-level `ce_bezug` / `fallsituation` / `teilaufgaben` fields. Not pinned to
  length 2 at the pydantic level — an in-progress draft with only Aufgabe 1
  written must still validate (tech doc 1.5.1) — so `completeness()` reports
  `aufgaben.vollstaendig` instead.
- **Anchor grammar** — `ta.2` → `ag.1.ta.2`; `fs.satz.3` → `ag.1.fs.satz.3`.
  `Aufsichtsarbeit.anchors()` / `.resolve()` rewritten; `alle_teilaufgaben()`
  added for whole-paper rules that must pool across both blocks.
- **`schemas/rule.py`** — `Scope.aufgabe` used to mean "the whole paper"; that
  collided with real vocabulary once "Aufgabe" turned out to mean the block.
  Renamed: `Scope.aufsichtsarbeit` is now the whole-paper scope, `Scope.aufgabe`
  is the per-block scope.
- **Every rule's `scope` reclassified** against what it actually operates on,
  which surfaced two rules (FORM-06, QUELL-03) that were already over-scoped at
  week 1 — both fire per-Teilaufgabe, not per-paper, independent of this
  restructuring. Whole-paper rules (FORM-02, FORM-16, KOMP-03, KOMP-03B,
  KOMP-04, KOMP-05) now explicitly flatten across both blocks via
  `alle_teilaufgaben()`. KOMP-07 (Situationsmerkmale vs. claimed CE) turned out
  to be a *better* fit after the split: each block now compares its own
  Fallsituation against its own `ce_bezug`, rather than one paper-level
  `ce_bezug` standing in for two blocks that might claim different CEs.
- **`checks/deterministic/komp_03.py`** — `claimed_schwerpunkte()` pools across
  both blocks, matching the corrected scope.
- **New rule, FORM-16** — "Aufgabe 1 and Aufgabe 2 contribute roughly equal
  Punkte." Confirmed as a real construction expectation in the same
  conversation that surfaced the block structure (illustrated with a 100-point,
  50/50 example). Deterministic, `construction_principle` authority, fires
  below a 40% floor rather than demanding exact equality. Catalogue-only for
  now — `checks/deterministic/form_16.py` is week-2 implementation work, same
  as the other 25 unimplemented rules.
- **All 12 synthetic items rewritten** with a genuine second Aufgabe block
  (D-01 is the deliberate exception — see below). Three fixed corpus facts
  existing tests depend on were preserved exactly through the rewrite:
  - **C-03 still covers exactly 1 of Prüfungsbereich 3's 4 Kompetenzschwerpunkte**
    pooled across both blocks (the KOMP-03B demonstration), and **I.2.g remains
    the sole Anlage-1-only code claimed** (the KOMP-06 demonstration). Aufgabe
    2's codes were deliberately drawn from Bereiche outside {I.3, I.4, II.3,
    III.2} so pooling could only add coverage if it happened to touch those —
    it doesn't.
  - **D-01 stays a genuine single-Aufgabe-block draft** rather than getting a
    second block authored. This is a better fit for "the tool works on an
    in-progress draft" than before: it now exercises two independent, correct
    completeness gaps at once (`aufgaben.vollstaendig` is `False`, and Aufgabe
    1's Erwartungshorizont is still missing).
  - **D-01/D-02/D-03 stay homogeneous** across all five of their Aufgabe blocks
    (`stationaer_langzeit` / `alter_mensch`), so KOMP-05's demonstration still
    fires on the sibling set.
  - C-01 and C-02 pick up **FORM-16 as an additional organic defect** (Aufgabe
    2 carries 37% and 32% of the paper's Punkte respectively) — not engineered
    for that purpose, but a plausible extension of "organically weak
    construction" that the manifest now documents alongside each item's other
    known weaknesses.
- **`items/manifest.json`, `docio/word_template_spec.md`,
  `docio/template_tags.md`, `README.md`** updated to match.

### What this means for week 2

The entry conditions in §5 still hold, updated for the corrected shape: 12
items validate (124 tests, up from 63), the catalogue validates with 27 rules
(25 runnable, 15 deterministic), and the output contract is unchanged. Nothing
in week 2's scope (permissive parser, deterministic checks, model gateway,
German-quality spot check, smoke run) depended on the old flat shape in a way
that would have been cheaper to fix later — this was worth catching now.
