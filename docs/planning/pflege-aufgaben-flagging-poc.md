# Technical Documentation: PoC — KI-gestütztes Flagging von Prüfungsaufgaben

## Generalistische Pflegeausbildung · schriftliche Abschlussprüfung

**Prepared for:** P-team / Digitalschmiede
**Date:** September 2, 2026
**Constraints:** ~5 weeks · zero budget (no API spend, no hardware, no paid services) · no team GPU · implementation by Claude Code
**Nature of deliverable:** proof of concept. This validates a mechanism. It is not a deployable system and is not DSGVO/BSI-compliant infrastructure.

---

## 1. Product definition

### 1.1 What the tool does

Takes a drafted Aufsichtsarbeit as input. Returns a list of **flags**, each anchored to a specific span of the artifact, each carrying the rule it derives from, the quoted source text for that rule, and where applicable a suggested revision. It advises. It does not decide, score, or gate.

### 1.2 What the tool explicitly does not do

- No pass/fail verdict, no aggregate quality score. A single number invites misuse as a gate and cannot be defended.
- No statistical difficulty or discrimination estimate.
- No exam delivery, proctoring, or candidate-facing anything.
- No autonomous rewriting. Suggested revisions are proposals attached to flags, never applied.

**These are not just good manners; with an author-facing tool they are liability protection.** Exam-result challenges are common in German vocational exams. If the tool sits inside the construction process, the record must show that a qualified professional made every decision, with documented reference to PflAPrV and the Leitfaden. A tool that "approved" or "scored" an item creates a far worse position to defend than one that demonstrably advised a human who decided. This should be raised with a Land Justiziariat alongside the AI-content copyright question (§11).

### 1.3 Positioning: build the critic before the generator

The strategic argument, worth stating explicitly because it shapes the architecture:

A generator without a validator produces items nobody can defend, which is precisely the objection a Prüfungsausschuss or a Regierung will raise about AI-authored exam content. A validator is useful on day one against items that already exist, and it is the component that makes a later generator trustworthy, because it becomes the scoring function in a generate → check → revise loop.

So the extension path to draft generation is not a hope bolted onto the end of this project. It is the same rule catalogue, the same retrieval corpus, and the same evaluation harness, pointed at generated input instead of human input. Every artifact this PoC produces is reusable for that phase.

### 1.4 Users, in priority order

**Primary: the Prüfungsausschuss — the people who author the Aufgaben.** Formative use, during drafting, in the tool they already work in. Practically this means Lehrende who serve as Fachprüferinnen and Fachprüfer; the BW Leitfaden is addressed to exactly this audience.

**Secondary: the compliance/review checkpoint** — whoever inspects a proposed Aufgabe before it becomes an exam. A concrete existing example: in Bavaria's Altenpflege Schulversuch, each participating school submits a complete Aufgabenvorschlag with its solution to the responsible Regierung by 15 January, and the Regierung then constructs two equivalent proposals for each of the three written exams. That desk handles many submissions against one shared standard.

Same engine, same rule catalogue, different output presentation (§4.3).

### 1.5 Consequences of being author-facing

The primary user being the author rather than the reviewer changes four things. None of them touch the rule catalogue or the evaluation, but all four are load-bearing for whether the tool gets used.

**1. It must work on incomplete drafts.** An author has three of five Teilaufgaben written and no Erwartungshorizont yet. A reviewer always sees a finished artifact; an author almost never does. Every rule therefore declares its preconditions (`requires`, §3.3) and the runner **skips visibly rather than flags** when they are unmet. Without this, most of the catalogue fires spuriously during exactly the phase when the tool is most useful.

**2. Suggestions matter more than flags.** A reviewer needs to know what is wrong. An author needs to know what to do. The `suggestion` field is therefore expected, not optional, for family A. This also brings the generation extension forward honestly: a proposed rewrite of a single Teilaufgabe, grounded in a specific rule, is a small and well-constrained generation task, and a better first step than drafting whole Fallsituationen.

**3. False flags are more costly than the doc's precision-over-recall argument already implies.** A reviewer meets the tool once per artifact. An author meets it repeatedly while drafting, so per-session exposure to false flags multiplies. A tool that cries wolf during drafting gets switched off and never reaches the review desk.

**4. Tone is a design constraint, not polish.** These are qualified professionals who will reasonably resent software second-guessing their pedagogical judgement. Flags advise; they never grade. No "Fehler", no scores, no red. `hinweis` framing by default, `blocker` reserved strictly for violations of binding PflAPrV requirements where the rule text does the talking.

**Note on the committee.** The Prüfungsausschuss is a body, not a person, so several people touch one Aufgabe and there is an internal agreement moment before any external one. Flags become a shared discussion object. Multi-author workflow, comment threading, and sign-off stay out of scope for this PoC (§11), but the flag schema's stable IDs and the run log are what a later version would build that on.

---

## 2. The input artifact

### 2.1 Structure

An Aufsichtsarbeit is a compound artifact, not a question. This drives most of the design.

```
Aufsichtsarbeit
├── Metadaten (Prüfungsbereich, Ausbildungsabschluss, Bearbeitungszeit, Autor, Version)
├── ce_bezug []               ← curriculare Einheit(en) the item draws on
├── Fallsituation
│   ├── text                   ← the narrative as written
│   └── situationsmerkmale     ← per the Lehrplan's Situationsprinzip (§3.2.1)
│       ├── handlungsanlässe
│       ├── kontextbedingungen
│       ├── handlungsmuster
│       └── akteure
└── Teilaufgaben [1..n]
    ├── Aufgabentext          ← contains the Operator (Handlungsverb)
    ├── ausgewiesenes Anforderungsniveau
    ├── Punkte
    ├── ausgewiesene Kompetenzzuordnung   ← Anlage 2 codes, e.g. I.1.h, V.2.c
    └── Erwartungshorizont
        └── Erwartungspunkte [1..m] (content point + Punkte)
```

Structuring the Fallsituation by Situationsmerkmale rather than by invented fields means the schema mirrors a binding document. It also means the fields are things a Prüfungsausschuss member already thinks in, which matters for the tone constraint in §1.5.4.

### 2.2 Item schema (`schemas/aufgabe.schema.json`)

Structured JSON is the internal representation. Parsing free-form Word input into it is a week-2 task and deliberately shallow: a permissive parser plus a manual correction step, since input format normalisation is not what this PoC is testing.

Key design points:

- **Every flaggable element carries a stable ID** (`ta.2`, `ta.2.eh.3`, `fs.satz.7`). Flags reference these IDs. Without stable anchoring the output is a wall of unlocatable prose.

  The ID identifies a **structural position**, not the text at that position. `ta.2` means "the second Teilaufgabe of this Aufsichtsarbeit", regardless of what it currently says. This is deliberate: the author rewrites the text, the ID still points at the same element, and two runs of the checker can therefore be compared to see whether a flag was resolved or persisted. Character offsets or text hashes would be invalidated by any edit and cannot do this.

  Known limitation: ordinal IDs shift if the author *reorders* or *inserts* a Teilaufgabe, since the old `ta.2` becomes `ta.3`. Acceptable for this PoC, where each run is one-shot against a submitted draft. It becomes a real problem in the Word add-in (§4.4), where the fix is natural: a content control carries its own tag through edits, so the tag becomes an opaque identifier and the visible number is display only.
- **Claimed vs. derived is kept separate.** The schema stores the author's *claimed* Kompetenzzuordnung and Anforderungsniveau. The tool derives its own and flags divergence. Conflating the two makes the most valuable check impossible.
- **Cross-item context is a first-class field.** Some rules apply across the set of three Aufsichtsarbeiten, not within one (PflAPrV expects the three Fallsituationen to be varied overall). The schema supports an optional sibling reference.
- **Every field is optional.** Follows directly from §1.5.1: the schema must validate a half-written draft. Completeness is computed, not required, and drives which checks can run. A schema that rejects incomplete input locks out the primary user.

---

## 3. The rule catalogue

This is the single most important deliverable. It has standalone value even if no code ships: a structured, citable rule set for Pflege exam item construction does not currently exist in machine-readable form anywhere.

### 3.1 Sources, by layer

| Layer | Instrument | Status | Role |
|---|---|---|---|
| Federal, binding | **PflAPrV** (esp. §§ 9, 14; §§ 26, 27 for the specialised Abschlüsse) | Public, stable | Hard constraints: three Aufsichtsarbeiten, fallbezogen construction, 120 min each, Prüfungsbereiche from Kompetenzbereiche I–V |
| Federal, binding | **Anlage 2 PflAPrV** | Public, stable | The competency target. Closest thing to an official blueprint. |
| **State, binding** | **Lehrpläne und Ausbildungspläne für die Berufsfachschule für Pflege** (StMUK / ISB Bayern, July 2020; binding by Verfügung 21.07.2020, Az. VI.5-BS9600.1-3-7a.67273, from school year 2020/21) | Public, stable | **The operative source for a Bavarian pilot.** Reproduces Anlage 1 and Anlage 2 competencies verbatim with hierarchical codes, organised into eleven curriculare Einheiten, and supplies the Situationsmerkmale taxonomy. See §3.2.1. |
| State, official | **Liste der Operatoren des Bay. StMUK** | Public | The citable operator list for FORM-03 and FORM-04. Obtain from StMUK directly rather than via secondary reproduction. |
| National curriculum | **Rahmenpläne der Fachkommission (§ 53 PflBG)**, via BIBB | Public, stable | Federal cross-check. The Bavarian Lehrplan is explicitly built on these, so for a Bavarian pilot the Lehrplan is the operative rendering and the Rahmenpläne are the reference against which state-specific narrowing can be spotted. |
| Third-party guidance | **PflegePlus Handreichungen** (Operatoren; Sprachsensibel Prüfen), Kamm / Roche, 2025 | Public but copyrighted | Rule sources for Family A: an extended operator list, a 27-item checklist for Fallsituationen and Aufgabenstellungen, and 15 paired hard/easy formulation examples. Licence must be resolved (§12). |
| State guidance | **BW: Leitfaden zur Erstellung von Prüfungsaufgaben** (ZSL / MKJS / Sozialministerium BW) | Public | Cross-check and jurisdiction-portability test, no longer the primary rule text. Contains formal and fachliche requirements plus Musterprüfungsaufgaben. |
| Reference | Item-writing guidance from assessment literature | Public | Fills gaps no German source addresses (ambiguity, cueing, negation) |

### 3.2 Bavaria: no item-writing Leitfaden, but a strong binding corpus

Checked September 2026. Bavaria has **no published guidance on written-exam item construction** comparable to Baden-Württemberg's Leitfaden. The document that appears Bavarian is BW's, authored by ZSL and attributed to the BW Kultus- and Sozialministerium; it surfaces on HubbS because that platform aggregates material across Länder. Bavaria's StMGP has published a Handreichung for the **practical** Abschlussprüfung (2024), not the written one.

That gap is narrower than it first looks, because Bavaria does supply the two things a rule catalogue actually needs:

- a **binding state curriculum** (the StMUK / ISB Lehrplan, §3.2.1) that carries the competency taxonomy and a situation-description schema, and
- an **official operator list** (Bay. StMUK), which is the citable authority for the operator checks.

**Consequences for the catalogue:**

1. Build on the **federally uniform layer** (PflAPrV + Anlage 2) as the backbone of binding constraints. Identical in all 16 Länder.
2. Use the **Bavarian Lehrplan as the operative curricular source** and the StMUK Operatorenliste as the operator authority. Together these make Bavaria the *better* jurisdiction to build for, not a compromise.
3. Use **BW's Leitfaden as a cross-check** on the formal/didactic rules, and as the portability test for the `jurisdiction` mechanism.
4. Keep **state pluggability from day one** anyway: a `jurisdiction` field on every rule and a profile selecting the active subset. Cheap now, and the difference between a Bavarian demo and a national product.
5. The absence of Bavarian written-exam item guidance remains a **market argument**. Bavaria produces this kind of guidance when it decides a process needs it, has done so for the practical exam, and has not for the written one.

### 3.2.1 What the Bavarian Lehrplan supplies

Verified by extraction against the document.

**A citable competency taxonomy with stable IDs.** The Lehrplan reproduces the Anlage 1 and Anlage 2 PflAPrV competencies verbatim, each followed by a hierarchical code in parentheses covering Kompetenzbereich, Kompetenzschwerpunkt and Einzelkompetenz — `I.1.h`, `II.3.a`, `V.2.c`. Extraction found **691 code occurrences across 88 unique codes**, distributed over all five Kompetenzbereiche (36 in I, 14 in II, 18 in III, 9 in IV, 11 in V). This is what Family B tags against, and it arrives with identifiers rather than requiring the team to invent them.

**An explicit Anlage 1 versus Anlage 2 split.** Competency blocks are headed either `Kompetenzen – 1./2. Ausbildungsdrittel (Anlage 1 PflAPrV)` or `Kompetenzen – 3. Ausbildungsdrittel (Anlage 2 PflAPrV)`. These are not two disjoint competency lists: Anlage 1 is what the Zwischenprüfung (end of year 2) tests and Anlage 2 is what the staatliche Prüfung tests, and they largely reuse the same competency codes at a deepened level of mastery — e.g. code I.1.a-h reads "Menschen mit überschaubaren Pflegebedarfen" under Anlage 1 and drops that qualifier for "komplexen gesundheitlichen Problemlagen" under Anlage 2. Across the Lehrplan's eleven curriculare Einheiten, 79 distinct codes appear under an Anlage-2-labeled heading and 76 under Anlage 1, with 71 appearing under both. **This count reflects what the Lehrplan's curriculum designers chose to cite for year-3 deepening, not a direct read of PflAPrV's Anlage 2 text itself**, so it is a starting point for KOMP-06 rather than its authoritative source — see the verification item in §12. With that caveat, an item claiming a competency that the Lehrplan never revisits at the Anlage 2 level is a real signal worth surfacing (KOMP-06), even if confirming it as a hard defect requires the official Anlage 2 catalogue.

**Eleven curriculare Einheiten with time weightings.** CE 01 through CE 11 for the generalistische Ausbildung, with Zeitrichtwerte from 50 to 200 hours, eight continuing into the third Ausbildungsdrittel in a spiral structure, and CE 02 splitting into A (Mobilität) and B (Selbstversorgung). Each CE selects a defined competency subset, and Kompetenzbereiche I and II appear in every CE by design.

**A Fallsituation construction schema.** The Lehrplan's Situationsprinzip organises each CE's content into **Situationsmerkmale**: `Handlungsanlässe` (what makes the situation call for nursing action), `Kontextbedingungen`, and `Handlungsmuster`, with `Akteure` and Erleben/Deuten/Verarbeiten alongside. Binding content within these is marked in the source by italic bold.

This is the most useful unanticipated find in the corpus. A Fallsituation *is* a nursing situation, so the Lehrplan already specifies the vocabulary for describing one, in a binding document. It should structure the item schema (§2.2) rather than the ad-hoc setting and Altersgruppe fields, it enables KOMP-07, and it is the natural template for the later generation extension.

**Extraction notes for implementation.** The file is plain UTF-8 text (~19,300 lines), not a PDF, despite the extension. It needs cleaning for `\x02` soft-hyphen artifacts, `\r\n` endings, and words hyphenated across line breaks. Code formatting is inconsistent in places — `(II 3.b.)` appears alongside `(II.3.b)` — so the code parser must be tolerant. It also contains the Anlage 3 and Anlage 4 competencies for the besondere Abschlüsse in Kinderkranken- and Altenpflege; these must be filtered out for the generalistische exam rather than ingested wholesale.

Chunking should follow CE and Situationsmerkmal boundaries, never character counts, so that a retrieved passage carries a meaningful citation.

### 3.3 Catalogue schema (`rules/*.yaml`)

The catalogue is **data, not code**. YAML files, one per family, version-controlled, editable by a non-programmer.

```yaml
- id: FORM-04
  family: A                      # A=Form/Konstruktion, B=Kompetenz, C=Quellenbindung
  title: Operator passt zum ausgewiesenen Anforderungsniveau
  rule_text: >                   # close paraphrase; verbatim only where short
    Der in der Teilaufgabe verwendete Operator muss dem ausgewiesenen
    Anforderungsniveau entsprechen.
  source:
    document: leitfaden_bw_2022
    locator: "Kap. Operatoren"
  jurisdiction: BW               # or: federal
  check_type: deterministic      # deterministic | llm | hybrid
  scope: teilaufgabe
  input_slice: [teilaufgabe.text, teilaufgabe.anforderungsniveau]
  requires:                      # preconditions; unmet → skip visibly, never flag
    - teilaufgabe.text
    - teilaufgabe.anforderungsniveau
  severity_default: pruefen      # blocker | pruefen | hinweis
  mutation:                      # the defect this rule must catch (see §7)
    id: MUT-FORM-04
    operation: swap_operator_level
    description: >
      Replace the Operator with one from a lower Anforderungsniveau
      while leaving the declared level unchanged.
```

The `mutation` field is the load-bearing trick: **every rule ships with the defect it is supposed to catch**, so the evaluation harness is generated from the catalogue rather than maintained separately. A rule without a mutation is not testable and does not ship.

The `input_slice` field is equally load-bearing: it declares the minimum artifact fragment a check needs. This is what keeps prompts small enough to fit free-tier token budgets (§6.3) and small models' reliable context.

The `requires` field is what makes the tool usable on a work-in-progress draft (§1.5.1). If a precondition is absent, the check does not run and the output says so. Silent omission and spurious flagging are both worse than an honest "nicht prüfbar: Erwartungshorizont fehlt noch."

### 3.3.1 `input_slice` and `mutation`, worked through

These two fields do most of the work in the catalogue, so an end-to-end example using FORM-04 above.

**`input_slice` — the projection from artifact to prompt.**

The full Aufsichtsarbeit runs to perhaps 2,500 words. FORM-04 asks a narrow question: does this Teilaufgabe's Operator match its declared Anforderungsniveau? To answer that, the check needs the Teilaufgabe's text and its declared level. Nothing else. So `input_slice: [teilaufgabe.text, teilaufgabe.anforderungsniveau]` sends roughly forty words instead of 2,500.

Two effects, and the second is the more important one:

- *Budget.* Sending the whole artifact to every check would roughly triple the token figures in §6.3 and break the daily caps.
- *Correctness.* A check that cannot see the Fallsituation cannot produce a flag about the Fallsituation. Narrowing the input narrows the failure surface. This is why `input_slice` is a per-rule declaration rather than a global truncation setting: FORM-08 ("Fallsituation supplies all information needed") legitimately needs both the Fallsituation and the Teilaufgabe, and says so.

**`mutation` — the rule's own test case.**

Used only by the evaluation harness (§7.2), never at runtime. It names a deterministic transformation that introduces exactly the defect this rule exists to catch, so ground truth is known by construction.

```
Clean base item, ta.2:
  text:               "Begründen Sie zwei Maßnahmen zur Sturzprophylaxe für Frau K."
  anforderungsniveau: III
  punkte:             8

Apply MUT-FORM-04 (operation: swap_operator_level):
  text:               "Nennen Sie zwei Maßnahmen zur Sturzprophylaxe für Frau K."
  anforderungsniveau: III        ← unchanged, now inconsistent
  punkte:             8

Ground truth recorded by the harness:
  expected_flag:  rule FORM-04, anchor ta.2
  expected_other: no other rule should fire on this change
```

The harness applies the mutation, runs the checker, and records whether FORM-04 fired at `ta.2` (detection) and whether anything else fired (false flag). The `expected_other` line is why the same variant is also run against a sample of unrelated rules.

Three reasons the mutation lives in the rule file rather than in a separate test suite:

1. Adding a rule automatically adds its test case. There is no second artifact to keep in sync, so catalogue and tests cannot drift.
2. It forces the rule to be stated falsifiably. If you cannot write a concrete transformation that the rule must catch, the rule is too vague to implement, and you find that out during week 1 curation rather than week 4 evaluation.
3. It makes the evaluation table generated rather than authored, which is what keeps §7 affordable at this scale.

A rule with no mutation is not testable and does not ship.

### 3.4 The three flag families

**Family A — Form und Konstruktion** (target: ~10 rules, majority deterministic)

Highest precision, best demo, lowest risk. Indicative rules:

| ID | Check | Type |
|---|---|---|
| FORM-01 | Fallsituation present and load-bearing for every Teilaufgabe | hybrid |
| FORM-02 | Scope plausible for 120 minutes given Punktzahl and Teilaufgaben count | deterministic |
| FORM-03 | Each Teilaufgabe contains exactly one unambiguous Operator from the list | deterministic |
| FORM-04 | Operator matches declared Anforderungsniveau | deterministic |
| FORM-05 | No double negation, no excessive subordinate-clause nesting | deterministic |
| FORM-06 | Punkte arithmetic consistent (Teilaufgaben sum to total; Erwartungshorizont sums to Teilaufgabe) | deterministic |
| FORM-07 | Erwartungshorizont actually answers what the Teilaufgabe asks | llm |
| FORM-08 | Fallsituation supplies all information needed to answer | llm |
| FORM-09 | No unused or misleading detail in the Fallsituation | llm |
| FORM-10 | Fachsprachliche Angemessenheit; no stereotyping in the Fallsituation | llm |

FORM-07 deserves a note: mismatch between what a Teilaufgabe asks and what its Erwartungshorizont rewards is a common, consequential, and entirely invisible-to-checklist defect. It is also well suited to a language model. This is the most compelling single check in the tool and should lead the demo.

**B. Kompetenzzuordnung** (target: ~7 rules)

Materially stronger than originally scoped, because the Lehrplan supplies coded competencies, the Anlage 1/2 split, and the CE structure (§3.2.1).

| ID | Check | Type |
|---|---|---|
| KOMP-01 | Each Teilaufgabe is mappable to at least one Anlage 2 competency code | llm + retrieval |
| KOMP-02 | Derived mapping agrees with the author's claimed code | llm |
| KOMP-03 | The Aufsichtsarbeit covers its intended Prüfungsbereich | deterministic aggregate over KOMP-01 |
| KOMP-04 | Anforderungsniveau distribution across the Aufsichtsarbeit is not degenerate | deterministic aggregate |
| KOMP-05 | Across sibling Aufsichtsarbeiten, Fallsituationen vary by CE, Versorgungsbereich and Altersgruppe | hybrid, cross-item |
| KOMP-06 | Every claimed competency code exists in the **Anlage 2** set, not only in Anlage 1 | **deterministic** |
| KOMP-07 | The Fallsituation's Situationsmerkmale correspond to those the Lehrplan specifies for the claimed CE | llm + retrieval |

KOMP-06 is the cheapest high-value check in the catalogue, once its source is right: a set-membership test against the Anlage 2 code list, no model involved. Built from the Lehrplan's citations for the PoC (§3.2.1's caveat), and worth re-deriving from PflAPrV's Anlage 2 text directly before this ships as anything more than a demonstration (§12). An Abschlussprüfung item testing a competency the exam-relevant Anlage doesn't cover is a substantive defect, and it is currently invisible to any manual review that does not cross-reference both Anlagen line by line.

KOMP-07 is the most differentiating check in the whole tool. Nothing on the market checks whether a case scenario's Handlungsanlass and Kontextbedingungen actually match the curricular unit whose competencies the item claims to assess, and it is defensible because both sides of the comparison come from a binding document.

**Family C — Quellenbindung** (target: 2–3 rules, narrow corpus slice only)

The most differentiating and the least mature anywhere, per the August research doc. Scoped honestly as a demonstration, not a capability.

| ID | Check | Type |
|---|---|---|
| QUELL-01 | Each fachliche assertion in the Erwartungshorizont is supported by a retrievable passage | llm + retrieval |
| QUELL-02 | No assertion contradicts the retrieved passage | llm + retrieval |
| QUELL-03 | Normative references (e.g. Vorbehaltsaufgaben under PflBG) are correctly cited | llm + retrieval |

Corpus for family C is the freely usable legal, curricular, and professional-normative text: PflAPrV, Anlage 2, the Bavarian Lehrplan, and — the concrete addition from source research (September 2026) — the DNQP-line **Expertenstandard "Erhaltung und Förderung der Mobilität in der Pflege"** (Aktualisierung 2020), which is the one Expertenstandard published in full and free of charge by the Geschäftsstelle Qualitätsausschuss Pflege rather than sold. It maps cleanly onto CE 02 A (§3.2.1), giving QUELL-01/02 a concrete, unambiguous demonstration target: does an Erwartungshorizont's guidance on mobility promotion match what the Expertenstandard's Struktur-/Prozess-/Ergebniskriterien actually specify. **No copyrighted Fachliteratur, and no standard textbook (Pflege Heute, I care, Thiemes Pflege — all commercial, no open edition found), is ingested in this PoC.** A stretch goal for Week 5, not a commitment, is adding one freely accessible AWMF S3-Leitlinie to show the approach generalises beyond a single document. Family C stays a demonstration, but on real, citable ground.

Approximate final tally: **~20 rules, of which 10–11 are deterministic** — Family A around 10, Family B 7, Family C 2–3. "Half the checks require no model at all" is a credibility line worth being able to say to a public-sector reviewer. Family A may grow further once the 27-item PflegePlus checklist is worked through in Week 1.

---

## 4. Output contract

### 4.1 Two architectural rules

**Rule 1 — No flag without evidence.** Every flag must carry its rule ID and the quoted source text that rule derives from. A check that cannot produce that does not ship. This is the entire difference between this tool and pasting an item into a chatbot, and it is the only part of legal defensibility a 5-week PoC can honestly deliver.

**Rule 2 — Deterministic first, model second.** Anything decidable by rule, word list, or arithmetic is decided that way, and the output labels which mechanism produced each flag. Cheaper, reproducible, and it lets the report distinguish "this violates a stated rule" from "a model thinks this may be a problem."

### 4.2 Flag schema

```yaml
flag_id: f_017
rule_id: FORM-07
anchor: ta.2.eh.3              # stable ID from the item schema
severity: pruefen
mechanism: llm                 # deterministic | llm
finding: >                     # what is wrong, in one or two sentences
  Der Erwartungshorizont verlangt eine Begründung, die Teilaufgabe
  fragt nach einer Aufzählung.
evidence:
  rule_quote: "..."            # short quote from the rule source
  source: leitfaden_bw_2022, Kap. Erwartungshorizont
  retrieved_passage: null      # populated for family C
suggestion: >                  # expected for family A, never auto-applied
  Operator der Teilaufgabe auf "begründen" anheben, oder den
  Erwartungshorizont auf die Aufzählung reduzieren.
confidence: null               # deliberately omitted, see below
```

**On suggestions.** For the primary user these carry most of the value (§1.5.2), so a family A rule without a usable suggestion is an incomplete rule. Two constraints: a suggestion must be derivable from the same rule the flag cites, and it is never applied automatically. Where a rule admits two legitimate fixes (as above), offer both rather than picking one — the choice is a pedagogical judgement that belongs to the author.

**On severity levels.** Three: `blocker` (violates a binding rule from PflAPrV), `pruefen` (violates state guidance or a construction principle), `hinweis` (advisory). Severity is a property of the *rule*, not a model judgement, so it is deterministic and defensible.

**On confidence scores.** Deliberately omitted. A model-generated confidence number would be unfounded, and reviewers would over-trust it. The `mechanism` field carries the honest version of the same information.

### 4.3 Two outputs, matching the two users

**Primary — Word comments written back into the author's own document.** Read the `.docx`, run the checks, write each flag back as a **native Word comment** anchored to the offending range, and save a copy. The author opens their own file in Word and sees flags in the margin, where they already expect feedback. python-docx 1.2.0 supports `add_comment()` anchored to a run range; the `docx-comments` package adds threading and resolution if reply-to-flag becomes desirable.

This is hours of work, not weeks, and it serves the primary user in their existing tool with no plugin, no hosting, and no tenant-admin approval. For a demo it also reads as a colleague having reviewed the file rather than as software having judged it, which matches the tone constraint in §1.5.4.

**Secondary — a self-contained annotated HTML report** (with print-to-PDF), one per Aufsichtsarbeit: the full artifact rendered, flags anchored inline, each expandable to its rule quote and source, grouped by severity. This is the artifact for the compliance reader, and the one that can be emailed, printed, and passed around a committee.

Both are consumers of the same flag JSON. Neither is a separate pipeline.

**Mandatory in both: a "checks not run, and why" section.** With the `requires` mechanism (§3.3) this is now a routine occurrence on any draft, not an edge case. A tool that silently omits coverage is worse than one that admits its gaps, and for an author it is actively useful — "nicht prüfbar bis Erwartungshorizont vorliegt" is a to-do list.

### 4.4 The Word side panel: designed for, deliberately not built

A task pane add-in giving live hints while typing is the right eventual surface for the primary user, and the design above is already compatible with it: flags anchor to logical IDs rather than document offsets, and the check runner is a stateless JSON-in/JSON-out service (§9).

The strongest argument for the Word route is one it also fixes: **the parsing problem in §2.2.** Ship a template whose content-control tags *are* the schema field names, and structure becomes explicit at authoring time rather than reverse-engineered afterwards. Parsing becomes trivial and reliable, and the template nudges toward well-formed items. Two modes follow: structured template gets the full catalogue, free-form gets the degraded subset with the disclosure above.

It stays out of these five weeks for three reasons:

1. **Cost against budget.** Manifest, HTTPS hosting, Office.js, sideloading, and cross-version testing is realistically 1.5–2 weeks of a 5-week project, spent on plumbing.
2. **Zero evaluation value.** The PoC's question is whether the flags are correct, which is measured on JSON. The surface is genuinely deferrable without weakening the result.
3. **Rollout dependency.** Organisation-wide deployment runs through the Microsoft 365 admin centre and needs tenant admin at the target institution, which is not available during a PoC. Requirement-set availability also needs checking, since public-sector schools plausibly run older perpetual Office versions.

**No compliance relief either way.** An add-in is a web app; the item text still leaves the machine and reaches the service. The Bavarian KI-Leitfaden constraint and the DPIA requirement are identical for the add-in, the report pipeline, and the docx path.

What this PoC does for it, at near-zero cost: the template content-control tag spec is written in week 1 alongside the item schema (§8), the service boundary is explicit (§9), and week 5 produces a short add-in feasibility and rollout appendix instead of a build.

---

## 5. Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  rules/*.yaml            corpus/                                  │
│  ~18 rules, per family   PflAPrV, Anlage 2, Rahmenpläne          │
│  + mutation defs         (public legal/curricular text only)      │
└───────────┬──────────────────────┬───────────────────────────────┘
            │                      │ chunk + embed (local, free)
            │                      ▼
            │            ┌─────────────────────┐
            │            │ Vector store        │
            │            │ (Chroma, local)     │
            │            └──────────┬──────────┘
            │                       │
   ┌────────▼───────────────────────▼──────────────────────────────┐
   │  Check runner                                                  │
   │                                                                │
   │  input: parsed Aufgabe (JSON, may be incomplete)               │
   │                                                                │
   │  0. precondition gate: for each rule, are `requires` met?      │
   │       unmet → "nicht prüfbar" entry, no model call             │
   │  1. deterministic checks   → flags        (no model, no cost)   │
   │  2. llm checks: for each rule,                                 │
   │       slice artifact per rule.input_slice                      │
   │       + rule_text + retrieved passage                          │
   │       → ONE prompt per rule                                    │
   │       → structured flag or null                                │
   │  3. aggregate checks       → flags                             │
   └────────┬──────────────────────────────┬───────────────────────┘
            │                              │
            │                    ┌─────────▼──────────┐
            │                    │ Model gateway       │
            │                    │ one interface,      │
            │                    │ N backends,         │
            │                    │ retry + backoff     │
            │                    └─────────┬──────────┘
            │                              │
            │                    ┌─────────▼──────────┐
            │                    │ Response cache      │
            │                    │ key: rule_id +      │
            │                    │ item_version +      │
            │                    │ model + prompt_hash │
            │                    └────────────────────┘
            ▼
   ┌────────────────────────────────────────┐    ┌──────────────────┐
   │ Report renderer → annotated HTML/PDF    │    │ Run log (SQLite) │
   └────────────────────────────────────────┘    │ every flag, every │
                                                  │ model, every run  │
                                                  └──────────────────┘
```

### 5.1 One prompt per rule

Each model call sees exactly one rule and only the artifact fragment that rule needs. Not one large prompt carrying the whole catalogue.

Reasons, in order of importance:

1. It makes "no flag without evidence" structural rather than aspirational. One rule in scope means the model cannot attribute a finding to the wrong rule.
2. Small prompts are where small models are reliable. A 20B model asked to apply eighteen rules to a 2,500-word artifact in one pass will produce plausible mush.
3. Failures are isolated and debuggable. A bad rule prompt is fixed without regressing seventeen others.
4. It is what makes the free-tier token budget work (§6.3).

Cost: more calls. Mitigated by the cache and by the fact that deterministic checks make no calls at all.

### 5.2 Model gateway and cache

Both are requirements, not conveniences.

The **gateway** is one interface over multiple backends. Free tiers are volatile: provider catalogues change without notice, models get retired, published rate limits shift within weeks. Model names are configuration, never hardcoded. Backends are tried in a configured order with retry and backoff.

The **cache** keys on `(rule_id, item_version, model, prompt_hash)`. It makes scored evaluation runs reproducible, keeps repeated development iterations inside daily quotas, and means a mid-run rate-limit stall resumes rather than restarts.

### 5.3 Stack

All free and open: Python, Pydantic (schemas), PyYAML (catalogue), Chroma (vectors), Jinja2 (report), SQLite (run log), pytest (deterministic checks and golden-file report tests). No orchestration framework. At this scale a framework is more surface area than help.

---

## 6. Model strategy

### 6.1 One model, chosen for the question the PoC actually asks

Zero budget and no GPU rules out a frontier API. The choice is between free open-weight models, and the PoC uses **one**: `gpt-oss-120b` via a free hosted tier (Groq publishes 131K context and 30 RPM for it).

The reasoning for picking the larger of the two realistic candidates rather than the smaller: the question this PoC exists to answer is whether the rule catalogue and retrieval setup produce useful, correctly-cited flags *at all*. That's best answered with the more capable model, so a weak result can be attributed to the approach rather than to the model being too small to execute it. The separate question of what the smallest deployable model would need to be — real for a production pilot, since a Land will ask what it can self-host — is deferred to the gap list (§11) rather than measured in these five weeks. A single-model PoC cannot answer both questions at once, and answering the first one well matters more than answering the second one badly.

Open-weight is still the right choice of model family, independent of size: it keeps the production narrative intact, since a proprietary ceiling would have made the strongest result unusable in a pitch, given that Bavaria's KI-Leitfaden bars internal documents from freely public AI systems.

Note what this design does *not* require: it never demonstrates local self-hosting. It does not need to. Whether a 20B at Q4 fits available hardware is a hardware-procurement fact (~16 GB VRAM), not something a PoC must prove. Running a 20B through a free API and measuring its quality answers the decision-relevant question at zero cost.

### 6.2 Provider posture

Free-tier constraints as verified September 2026, with the caveat that these numbers move monthly:

- **Groq** — no card, publishes its limits (30 RPM; ~1,000 RPD and ~100K TPD on the larger models). Predictable, plannable. Primary.
- **Cerebras** — no card, roughly 30 RPM / 14,400 RPD / ~1M tokens per day. Highest daily token headroom, but a volatile model catalogue that has collapsed to a handful of models before. Secondary, never hardcoded.
- **Google AI Studio** — free Flash models, no card, but limits are not published publicly and the models are proprietary. Not used, on the open-weight grounds above.
- **OpenRouter** — useful as a fallback layer, but ~50 free-model requests per day is too low for a scored run.

**Two things to write into the demo, not bury:** free tiers generally permit training on submitted prompts, and these providers are non-EU. Both are acceptable here only because every input is synthetic. Both are disqualifying for real exam content. State this at the top of any demo so the PoC is not mistaken for a deployable pilot.

### 6.3 Token budget arithmetic

Worked out rather than assumed. Token-per-day caps bind well before request-per-day caps.

Per scored run:

| | Calls | Avg tokens/call | Total |
|---|---|---|---|
| Clean items × llm rules | 12 × 9 = 108 | ~1,600 (sliced) | ~173K |
| Mutated variants × targeted rules | ~144 | ~1,600 | ~230K |
| **Total** | **~250** | | **~400K** |

Comfortably within a single free provider's daily token ceiling (§6.2), with no need to split runs across providers or days to stay under a cap. The `input_slice` per-rule mechanism (§3.3.1) is still worth keeping regardless, since sending the whole 2,500-word artifact to every check would roughly triple these figures and erode the margin, and it remains the reason correctness doesn't degrade as the catalogue grows past ~20 rules.

### 6.4 Kaggle free GPU versus free hosted APIs

Both are viable at zero budget. The tradeoff is worth recording because the answer is not obvious and because it is the main compute decision in the project.

| | Kaggle notebook, self-served model | Free hosted API |
|---|---|---|
| Time to first useful call | 1–2 days (notebook setup, ~9–13 GB model download, vLLM or Ollama install, caching the weights in a Kaggle Dataset so each session doesn't re-download) | Minutes |
| Binding limit | GPU-hours (~30/week) | Tokens per day (§6.3) |
| Throughput | Slow. A quantized 14–20B on a T4 or P100 runs at roughly 15–30 output tokens/sec, so a ~250-call scored run is hours of wall time and eats a meaningful share of the weekly quota on every re-run | Fast enough that iteration speed is not the constraint |
| Interruption | 12-hour session cap, idle disconnects, everything needs checkpointing | Rate-limit stalls, resumable via the cache |
| Reproducibility | Better in principle: seeds, temperature, and logprobs are all under your control | No seeds or logprobs; mitigated by the response cache, which makes a scored run reproducible from cached responses even if the provider is not |
| Development ergonomics | Poor. A notebook is a bad home for a multi-module Python service, and Kaggle is not a server, so either the whole pipeline runs inside the notebook or you tunnel to it | Normal local Python service, normal tests, normal debugging |
| Model size reachable | Capped by 16 GB (single P100/T4) or 32 GB with dual-T4 tensor parallelism and extra setup | 120B-class available |
| Third-party data exposure | None | Prompts may be used for training; providers are non-EU |
| Volatility | None. A downloaded model file does not get retired mid-project | Real. Catalogues and published limits change monthly |

**Decision: free hosted APIs as the primary path.** The deciding factor is model size: `gpt-oss-120b`, the model chosen in §6.1, is not reachable on a single Kaggle GPU. Running the PoC's actual model requires a hosted API regardless of any other tradeoff in the table.

The second factor is iteration speed. In five weeks, the scarcest resource is the number of prompt-and-rule revisions you can get through. Kaggle's setup cost, session interruptions, and generation speed all tax exactly that, independent of which model is chosen.

**Not planned as part of this PoC:** a local Kaggle run. With a single model chosen for capability rather than for deployability, there is no local-hosting claim this PoC is trying to support, so the half-day self-hosting confirmation that a two-model design would have justified isn't scoped here. If a production pilot later needs to know what a self-hostable model's quality looks like, that is exactly the kind of question a second, smaller model run would answer well — see the gap list note in §11.

### 6.5 German-language quality is an assumption to test, not to hold

Both candidate models considered in scoping were multilingual but not German-first, and the domain is fachsprachlich and legally precise. **Week 2 includes an explicit German-quality spot check** on the chosen model before committing further: a handful of hand-graded outputs on real Fachsprache. If German quality is inadequate, the fallback is a Gemma-4-class model at ~12B. This check is cheap and finding out in week 2 rather than week 5 is worth a day.

---

## 7. Test corpus and evaluation

### 7.1 Synthetic base items

All test items are written for this project. No school items, no published Prüfungsfragen collections, no scraped practice questions. This eliminates the confidentiality and copyright exposure flagged in the August research doc, and it is the reason the free-tier providers in §6.2 are usable at all.

Target: **12 base Aufsichtsarbeiten**, deliberately spread across Versorgungsbereiche, Altersgruppen, and grades of Pflegebedürftigkeit, and deliberately including some that are *good* and some with organically weak construction. Ideally reviewed once by a nursing-education SME for face validity, though the evaluation does not depend on that.

### 7.2 Blind mutation harness

Detection is measured by injecting known defects into clean items, one at a time, and checking whether the corresponding rule fires.

Because every rule in the catalogue carries its own `mutation` definition (§3.3), the harness is **generated from the catalogue**. Adding a rule automatically adds its test case. There is no separate test corpus to maintain and drift.

Design requirements:

- **Blind.** A script selects and applies the mutation and records ground truth separately. Whoever inspects outputs does not know which variant they are looking at. Without this the evaluation measures the evaluator's expectations.
- **Held-out defect classes.** The mutation set includes several defect types no rule was written for, to distinguish generalisation from memorisation. These are expected to be missed; the point is knowing the shape of the blind spot.
- **Clean items always run too.** The false-flag rate on unmutated originals is the headline number. For a review tool, a false flag costs expert trust and time, while a missed flag is merely the status quo. Precision matters more than recall here, and the evaluation must be able to say so with a number.

### 7.3 Metrics

| Metric | Reported per | Why |
|---|---|---|
| Detection rate | rule | Which checks actually work |
| False-flag rate on clean items | rule | The credibility number |
| Evidence validity | sampled, hand-graded | Does the cited rule/passage actually support the flag? A correct flag with fabricated evidence is a failure. |
| Anchor accuracy | sampled | Does the flag point at the right span? |

### 7.4 The honest limitation

The evaluation measures detection of defects the team injected into items the team wrote. That is circular, and the mitigations in §7.2 reduce but do not remove it. **External validity is untested.**

This must be stated plainly in the write-up, with "run the harness against 20 real Aufgabenvorschläge from one school or one Regierung" as the first entry on the post-PoC gap list. A PoC that names its own limitation is more credible to a public-sector reviewer than one that overclaims.

---

## 8. Five-week plan

| Week | Focus | Deliverable |
|---|---|---|
| **1** | Rule catalogue, taxonomy extraction, schemas | Anlage 2 competency codes and CE/Situationsmerkmale structure extracted from the Lehrplan into `rules/kompetenzen.yaml` (§3.2.1); operator list to `rules/operators.yaml`; ~20 rules in YAML with sources, `input_slice`, `requires`, and mutation definitions; item schema; Word template content-control tag spec (§4.4); 12 synthetic base Aufsichtsarbeiten. No code beyond schema validation and the one-shot extraction scripts. |
| **2** | Deterministic spine | Permissive parser into the item schema; all 8–9 deterministic checks with unit tests; model gateway + cache; German-quality spot check on the chosen model (§6.5); end-to-end run on a 3-item smoke set |
| **3** | LLM checks, families A and B | One prompt per rule, structured output, span anchoring, evidence capture; iterate against the smoke set |
| **4** | Retrieval, family C, evaluation | Corpus chunked and embedded; 2–3 family C rules; mutation harness generated from the catalogue; scored run on the full catalogue |
| **5** | Outputs, write-up | Docx comment writer (primary output) and annotated HTML/PDF report (secondary), both with golden-file tests; results, limitations, gap list, add-in feasibility appendix |

Week 5 has more room than a two-model design would have left. Two ways that room can be used, in order of priority: first, harden the outputs (docx writer, report renderer, golden-file tests) beyond what a tighter schedule would have allowed; second, if time remains, widen family C past the single Mobilität-Expertenstandard slice, or run the German-quality spot check as a fuller comparison rather than a handful of examples. Neither is committed — see the cuts below.

There is no slack. Pre-decided cuts, in order:

1. Family C narrows from three rules to one, demonstrated on a hand-selected slice.
2. The HTML report degrades to a plain flag table. The docx comment output does not get cut — it is the primary user's surface.
3. The scored run in week 4 drops to a subset of rules rather than the full catalogue.

**Not cuttable:** the rule catalogue (week 1), the `requires` precondition gate, evidence on every flag, and the false-flag measurement. Losing any of those means the PoC cannot answer the question it exists to answer, or cannot be used by the person it is for.

### 8.1 Why no interactive application

A standalone web app is one more place for the author to go, whereas Word comments arrive in the file they are already working in.

A Prüfungsausschuss member evaluating this will judge it on whether the flags are right and whether the reasoning is citable. Comments in their own document show that directly, with no hosting and no new tool to learn. The eventual real surface is the Word task pane (§4.4), so a web prototype would be throwaway work in a direction nobody intends to go.

---

## 9. Working agreement for implementation (Claude Code)

Implementation is by Claude Code. A few constraints are worth fixing up front because they are cheap now and expensive to retrofit.

**Repository layout**

```
rules/          *.yaml — the catalogue. Data, not code. Editable by a non-programmer.
schemas/        JSON Schema / Pydantic models for Aufgabe, Flag, RuleSet
corpus/         public legal + curricular text, chunked
items/          synthetic base items (12), as JSON
mutations/      generated variants + ground truth (gitignored, reproducible from seed)
checks/
  deterministic/  one module per rule, one test file per rule
  llm/            prompt templates, one per rule
gateway/        model interface, backends, cache
service/        stateless JSON-in/JSON-out entry point over the check runner
docio/          .docx read (python-docx) + comment writeback; Word template spec
report/         Jinja2 templates, golden-file tests
eval/           harness, metrics, result tables
docs/           this document, results write-up
```

**Non-negotiables for the implementation**

- Rules live in YAML, never in Python. A rule change must not require a code change.
- **The check runner is reachable as a stateless service with a documented JSON contract** (`Aufgabe` in, `Flag[]` + `NotChecked[]` out). The docx writer, the HTML report, and a future Word add-in are all consumers of that one contract. No consumer reaches into the runner's internals. This is the single change that keeps §4.4 a drop-in later rather than a rewrite.
- Checks never run without their `requires` satisfied, and every unmet precondition produces an explicit `NotChecked` entry. Silent skipping is a bug.
- The docx writer never modifies the input file. It always emits a copy.
- Every deterministic check has a unit test, written before or with the check.
- The report renderer has golden-file tests. Report regressions are otherwise invisible.
- The model gateway never hardcodes a model name. Free-tier catalogues change without notice.
- No real exam content, ever, in any prompt, test fixture, or commit. The synthetic-only rule is a compliance boundary, not a convenience.
- Mutations are reproducible from a seed and gitignored, so ground truth cannot drift from the variants.

**Sequencing note.** Weeks 1 and 2 are largely rule curation and deterministic logic, which is the part with the most durable value and the least AI in it. Resist the pull to start with the interesting model work. If week 1 slips, everything after it is built on sand.

---

## 10. Risks

| Risk | Assessment | Mitigation |
|---|---|---|
| **Rule catalogue is thinner than expected** | Materially reduced. Between the Lehrplan's coded competencies, the StMUK operator list, and the 27-item PflegePlus checklist, the sources are now known to be rich enough for ~20 rules. The residual risk is operationalisability, not availability. | Work the checklist and the Leitfaden through in the first three days and fix the rule count then, not in week 4. |
| **Free-tier volatility** | High likelihood, low impact. Model catalogues and limits change monthly. | Gateway with multiple backends; models as config; cache so a stall resumes. |
| **Token-per-day caps bind mid-evaluation** | Moderate. §6.3 shows the budget is tight, not comfortable. | Input slicing, targeted mutation evaluation, split across providers and days. |
| **German-language quality of the chosen model** | Unknown until tested. Would undermine the whole result, since there is no second model to fall back on for comparison. | Explicit week-2 spot check; Gemma-4-class fallback identified. |
| **Evaluation circularity** | Certain, not a risk but a known limitation. | Blind mutation, held-out defect classes, false-flag measurement, and stating it plainly (§7.4). |
| **Family C underdelivers** | Likely. Automated source-grounding is unsolved everywhere; the research doc found no shipped example at any vendor. | Scoped as a demonstration on 2–3 rules over public text only. Pre-decided cut to one rule. |
| **Author rejection on professional grounds** | The most likely non-technical failure. Qualified Lehrende may experience the tool as software auditing their pedagogical judgement. | Tone constraints in §1.5.4; advisory-only output; suggestions offering alternatives rather than a single fix; test this with a real Fachprüfer before the demo, not after. |
| **False-flag fatigue during drafting** | Higher exposure than the reviewer case, since authors invoke it repeatedly per Aufgabe. | Precision over recall; `requires` gate to prevent spurious flags on incomplete drafts; false-flag rate is the headline evaluation metric (§7.3). |
| **Liability framing of an advisory tool** | Unresolved legal question, not a product defect. If a flagged-clean item is later challenged, the tool's role must be defensible. | No aggregate score, no gate, no auto-apply (§1.2). Raise with a Land Justiziariat alongside the copyright question before any pilot. |
| **PoC mistaken for a deployable pilot** | Real reputational risk with public-sector audiences. | Non-compliance stated at the top of the demo and in the write-up: non-EU providers, prompts may train models, synthetic data only. |

---

## 11. Out of scope, and the production gap list

Explicitly out of scope for these five weeks: any model training, fine-tuning, or feedback-driven learning loop; statistical difficulty and discrimination validation; draft item generation; exam delivery and proctoring; the Word task pane add-in (§4.4) and any other interactive application; DSGVO/BSI-compliant hosting; Fachliteratur ingestion; multi-user committee workflow, comment threading, sign-off, or authoring-time audit trail beyond a plain run log.

The statistical component deserves a note on why it is out rather than merely deferred: it requires candidate response data to calibrate difficulty and discrimination against, and none exists for newly drafted items. That is a data problem, not a time or budget problem.

The write-up in week 5 closes with a concrete gap list for a production version. Expected contents, in priority order:

1. Validate against real Aufgabenvorschläge (20+, one school or one Regierung), with at least one Prüfungsausschuss member using it while drafting rather than only reviewing outputs. Nothing else on this list matters until external validity is established.
2. EU/German-hosted, DPIA-cleared, Art. 28 GDPR-contracted inference. The Bavarian KI-Leitfaden warns explicitly that retrofitting this is usually infeasible, so it is a v1 architecture requirement for any real pilot, not a hardening pass.
3. Authoring-time audit trail: committee sign-off, blueprint alignment record, revision log. The research doc established that no vendor covers this; IQUL's legally-compliant-auditing module is delivery-side only.
4. The Word task pane add-in plus the structured template, which is the primary user's real surface (§4.4). Includes the tenant-admin deployment path and cross-version requirement-set testing.
5. Multi-author committee workflow: several Ausschuss members on one Aufgabe, flag discussion and resolution, internal agreement before external submission.
6. Licensed Fachliteratur corpus for family C, which is what would make source-grounding genuinely useful rather than demonstrative.
7. A second, smaller model run (e.g. `gpt-oss-20b` or similarly sized) to answer the production-sizing question this PoC deliberately does not measure: what quality survives at a size a Land could plausibly self-host (§6.1, §6.4).
8. Statistical validation, once response data exists to calibrate against.
9. Resolution of the AI-generated-content copyright question, and the advisory-tool liability question (§1.2), with a Land Justiziariat before any pilot contract.
10. Jurisdiction profiles beyond BW.

---

## 12. Verification items at kickoff

Things this document assumes that should be re-checked in week 1, since some are volatile and some were not confirmable from public sources:

- **Free-tier limits and model availability** for `gpt-oss-120b`. Verified September 2026; these change monthly.
- **BW Leitfaden content depth.** This document assumes it yields roughly ten operationalisable formal rules plus an Operatorenliste. Confirm by reading it fully before fixing the rule count.
- **Whether Bavaria has unpublished internal guidance** for written Pflege exam construction, obtainable from StMGP or a Regierung. Public sources show none; that is not proof none exists.
- **The Bavarian Regierung-level review workflow** for the generalistische Ausbildung specifically. The 15-January Aufgabenvorschlag process is documented for the Altenpflege Schulversuch; confirm whether an analogous checkpoint exists for the generalistische Prüfung, since §1.4 leans on it.
- **Who in the Prüfungsausschuss actually drafts versus approves.** PflAPrV constitutes the Ausschuss with a Vorsitz from the zuständige Behörde plus Fachprüferinnen and Fachprüfer, but the practical division of labour between drafting Lehrende and approving members determines whether the primary user is one author or a committee, which in turn determines how much of the deferred multi-author workflow (§11) matters. §1.4 and §1.5 depend on this.
- **The Word environment at target institutions**: Microsoft 365 versus older perpetual Office, and whether add-in deployment via the admin centre is available at all. Determines whether §4.4 is a realistic phase 2.
- **Licence terms for the corpus documents.** Two distinct questions. (a) The StMUK / ISB Lehrplan is a state publication, so reuse is likely permissible, but confirm the terms before it ships inside a product corpus. (b) The PflegePlus Handreichungen are third-party copyrighted works (Kamm / Roche, 2025); their checklist and extended operator list need either permission or independently worded rules citing rather than reproducing them.
- **Whether the July 2020 Lehrplan is still the current version.** It was declared binding "zur Erprobung" from school year 2020/21. A revision may have followed. Check with ISB Bayern.
- **The Bay. StMUK Operatorenliste as a primary document**, rather than via its reproduction in the PflegePlus Handreichung.
- **The Anlage 2 code list behind KOMP-06.** Currently derived by counting codes cited under "Anlage 2 PflAPrV" headings in the Lehrplan (§3.2.1) — 79 codes across the document's eleven curriculare Einheiten. That reflects the curriculum's citation choices, not a direct extraction of PflAPrV's Anlage 2 text. Re-derive the authoritative list from Anlage 2 itself before KOMP-06 is treated as more than a demonstration.
- **BayernKI / ALP-KI terms** on input retention and training reuse. Still open from the August research doc.

---

## Sources

**Legal and curricular framework**

- [PflAPrV](https://www.gesetze-im-internet.de/pflaprv/BJNR157200018.html) · [Anlage 2 PflAPrV](https://www.gesetze-im-internet.de/pflaprv/anlage_2.html)
- [Rahmenpläne der Fachkommission § 53 PflBG – BIBB](https://www.bibb.de/dokumente/pdf/a26_rahmenplaene-pflegeausbildung.pdf)

**Item-writing and curricular guidance**

- **Lehrpläne und Ausbildungspläne für die Berufsfachschule für Pflege**, Bayerisches Staatsministerium für Unterricht und Kultus / Staatsinstitut für Schulqualität und Bildungsforschung (ISB), July 2020. Binding by Verfügung 21.07.2020, Az. VI.5-BS9600.1-3-7a.67273. www.isb.bayern.de
- **Handreichung 01: Umgang mit Operatoren in der Pflegeausbildung** and **Handreichung 02: Sprachsensibel Prüfen in der Pflegeausbildung**, Kamm / Roche, PflegePlus (ILS GmbH), 2025. www.pflegeplus-sprache.de
- **Expertenstandard "Erhaltung und Förderung der Mobilität in der Pflege"**, Aktualisierung 2020, DNQP im Auftrag der Geschäftsstelle Qualitätsausschuss Pflege e.V. — the sole DNQP Expertenstandard published free and full-text (all others require purchase). gs-qsa-pflege.de
- [Leitfaden zur Erstellung von Prüfungsaufgaben (Baden-Württemberg) – Sozialministerium BW](https://sozialministerium.baden-wuerttemberg.de/fileadmin/redaktion/m-sm/intern/downloads/Downloads_Gesundheits-_Pflegeberufe/Leitfaden_schriftliche-Abschlusspruefung-Berufsfachschulen-Pflege.pdf) — cross-check; also mirrored on [HubbS](https://hubbs.schule/mediathek/leitfaden-zur-erstellung-von-pruefungsaufgaben-fuer-die-zentrale-schriftliche), where the metadata confirms ZSL / Baden-Württemberg authorship
- [Handreichung praktische Abschlussprüfung – StMGP Bayern (2024)](https://vdpb-praxisanleitung.de/wp-content/uploads/2025/01/240916_StMGP-Handreichung-praktische-Abschlusspruefung.pdf) — Bavarian, but practical exam only
- [Berufsfachschule – ISB Bayern](https://www.isb.bayern.de/schularten/berufliche-schulen/berufsfachschule/) — Pflege Handreichungen, none on written item construction
- [Anlage 9, Konzept zur Durchführung der staatlichen Prüfung im Schulversuch – gesetze-bayern.de](https://www.gesetze-bayern.de/Content/Resource?path=resources%2FBayVwV259525_BayVV2230-1-3-UK-632-KF-1-A009.PDF) — the 15-January Aufgabenvorschlag → Regierung review workflow

**Model and infrastructure**

- [Free LLM APIs compared – OpenRouter](https://openrouter.ai/blog/tutorials/free-llm-apis-compared/) · [Best LLM API with a free tier – CostBench](https://costbench.com/best/best-llm-api-with-free-tier/) · [Free LLM API tiers – TokenMix](https://tokenmix.ai/blog/free-llm-api) · [Free LLM API tiers 2026 – Paterson](https://ianlpaterson.com/blog/free-llm-api-2026/)
- [Best Ollama models 2026 – Morph](https://www.morphllm.com/best-ollama-models) · [Open-source LLM comparison – ComputingForGeeks](https://computingforgeeks.com/open-source-llm-comparison/)

**Word integration**

- [python-docx `add_comment()` – Document objects](https://python-docx.readthedocs.io/en/latest/api/document.html) · [comment support added in 1.2.0](https://github.com/python-openxml/python-docx/pull/624) · [docx-comments (threading, resolution, Word Online compatibility)](https://pypi.org/project/docx-comments/)

**Prior project documents**

- *Competitive & Market Landscape Brief*, August 14, 2026
- *Research Documentation: Validation Layer for a Pflegeausbildung Exam-Authoring Tool*, August 19, 2026

---

*As of September 2, 2026. The regulatory layer (PflBG, PflAPrV, Rahmenpläne) is stable. Free-tier inference limits and open-weight model availability change monthly and are re-verification items at kickoff (§12).*
