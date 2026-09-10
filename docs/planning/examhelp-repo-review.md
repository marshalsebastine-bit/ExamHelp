# Repo Review: `marshalsebastine-bit/ExamHelp`

**Reviewed:** September 2, 2026
**Against:** *Technical Documentation: PoC — KI-gestütztes Flagging von Prüfungsaufgaben*
**Scope of review:** all committed code, data, and handoff notes. The committed FAISS metadata was loaded and inspected, so the findings below are about what the parsers *actually produced*, not only what the code appears to do.

---

## Summary

~790 lines of Python across 12 modules, plus a 443-chunk built index and four source documents. Roughly **60% is directly reusable**, 25% needs repurposing rather than rewriting, and 15% should be dropped as superseded or as premature scale.

The two most valuable things in the repo are not the RAG plumbing. They are the **official legal HTML parser** and the **structured extraction of the two Handreichungen**, which produced 26 clean operator records and 27 categorised checklist items. That output maps almost directly onto Family A of the rule catalogue, which means part of the planning doc's Week 1 is already done.

There is also **one blocking defect**: the entire Anlage 2 competency table is indexed under the citation `§ 62`. Details in §4.1. Family B cannot be built until that is fixed, and under the "no flag without evidence" rule it currently produces fabricated citations.

| Verdict | Items |
|---|---|
| **Keep** | Source documents + manifest, `read_legal_html()`, operator extraction output, Handreichung checklist/example-pair output, `lexical.py`, `matches_filters()`, chunker registry pattern, evaluation README's labelling discipline, common-metadata principle |
| **Rework** | Operator + checklist records → rule data rather than vector chunks; `LegalChunker` (Anlagen); `authority` field semantics; expand `queries.jsonl` |
| **Remove** | `chunk_text()` dead path, config-constant duplication, FAISS, reranker plan, Qwen3-14B commitment, Gradio/FastAPI UI direction, `rules/example_rules.yaml`, `source_id` compatibility alias, the 11-capability product list, the 20-concurrent-user target |

---

## 1. Keep

### 1.1 `data/raw/` and `data/source_manifest.json`

PflBG and PflAPrV official HTML, both Handreichungen, with a manifest recording URL, type, and authority per source. Provenance metadata for legal sources was something the planning doc listed as work; it exists. Keep as-is.

### 1.2 `read_legal_html()` in `app/ingest.py` — the best code in the repo

Selects `div.jnnorm[title="Einzelnorm"]` from gesetze-im-internet HTML, pulls the heading from `.jnheader h3` and the body from `.jnhtml`, skips the Inhaltsübersicht, and raises if no provisions are found. It also reads `iso-8859-1` correctly, which is a real trap on that site.

This is exactly the structure-aware legal ingestion the handoff notes described as still outstanding. It also handles the metadata page: `legal_source_metadata()` extracts the official title and the `table.standangaben` status line. Keep verbatim.

### 1.3 The operator extraction output — 26 clean records

`OperatorHandreichungChunker` produced 26 operator records with `anforderungsbereich`, `task_formulation`, `explanation`, `redemittel`, `example_question`, and `example_answer`. Verified: **zero nulls** in `anforderungsbereich` and `task_formulation` across all 26.

This is the data FORM-03 (valid operator from the list) and FORM-04 (operator matches declared Anforderungsniveau) need, already extracted and already carrying the Anforderungsbereich I/II/III mapping. See §2.1 for how it should be consumed.

### 1.4 The Sprachsensibel extraction output — 27 checklist items, 15 example pairs

Also verified in the built index:

- **27 `checklist_item` records**, each categorised as `Fallsituation` or `Aufgabenstellung`. These are near-1:1 candidate Family A rules. Several map onto rules the planning doc had already invented independently — the checklist's items on irrelevant information and on nested sentence structures correspond to FORM-09 and FORM-05.
- **15 `example_pair` records**, each linking a hard-to-read and an easy-to-read formulation with `difficult_example` / `easy_example` fields.
- **23 `guidance` records** split by chapter and section.

The example pairs are unexpectedly valuable: they are ready-made few-shot material for the LLM checks in Family A, and they are also a source of *mutations* — the "schwer verständlich" side of each pair is a real-world defect instance, authored by domain experts rather than invented by the team. That partially addresses the evaluation-circularity limitation in §7.4 of the planning doc.

### 1.5 `app/lexical.py`

Sixteen lines, does one thing correctly: German BM25 tokenisation that keeps umlauts and ß while dropping punctuation, shared between indexing and querying so `begründen?` and `begründen` match. Two tests cover it. Keep.

### 1.6 `matches_filters()` and `metadata_value()` in `app/retrieval.py`

Dotted-path metadata filtering (`structure.section`) with case-insensitive exact matching, tested. Small and useful. Keep.

### 1.7 The chunker registry pattern

`DocumentChunker` ABC, `CHUNKER_REGISTRY`, `classify_source()`, and `_base()` supplying common fields. The shape is right and the handoff's stated principle is sound: common metadata for retrieval and filtering, type-specific metadata for citation and interpretation. Keep the pattern; the specific chunkers change.

### 1.8 `evaluation/README.md`

Better than most internal documentation. The labelling guidance — use questions real authors would ask, add paraphrases rather than copying source terms, record the most specific verifiable metadata, have an SME review expected locators — transfers directly to the mutation harness. Keep the document even where the harness changes.

---

## 2. Rework

### 2.1 Operator and checklist records: rule data, not vector chunks

**This is the most important change in this review.**

Both structured extractions currently end up as chunks in a vector index, retrieved by embedding similarity at query time. For this content that is the wrong consumption model.

An operator-to-Anforderungsbereich mapping is a **lookup table with 26 rows**. Embedding it and retrieving by cosine similarity is strictly worse than a dictionary lookup on three counts:

- **It cannot answer the negative case.** FORM-03 asks whether the Teilaufgabe's operator is in the approved list at all. A vector search always returns its nearest neighbours, so an invented operator retrieves the most similar real one and the check silently passes. A dict lookup returns nothing and the check correctly fires.
- **It is non-deterministic** in a check that should be deterministic. The planning doc's §4.1 "deterministic first, model second" and the credibility line about half the checks needing no model both depend on FORM-03 and FORM-04 being table lookups.
- **It costs an embedding model load and a similarity search** to answer a question a dict answers in microseconds.

The 27 checklist items have the same problem in a different form: each is a *rule*, with a scope, a severity, and a testable defect. Retrieving a checklist item as a passage tells the model what to worry about; encoding it as a rule with `requires`, `input_slice`, and `mutation` makes it a check that can be measured.

**Migration:**

1. Freeze the 26 operator records to a committed `rules/operators.yaml` — operator, Anforderungsbereich, task formulation, and example. Deterministic checks read this file.
2. Convert the 27 checklist items into candidate entries in `rules/form.yaml`, each with independently worded `rule_text` (see §5 on copyright), a `source` locator pointing at the Handreichung, `check_type`, `requires`, `input_slice`, and a `mutation`. Expect roughly 15–20 to survive as implementable rules; some will be too vague to operationalise, and finding that out is exactly what Week 1 is for.
3. Keep the guidance prose and example pairs in the retrieval index. Family C legitimately needs to retrieve surrounding explanation, and the example pairs are useful few-shot context. But **no check may depend on retrieval to know what its own rule says.**

### 2.2 `LegalChunker`

Rework required, not optional. See §4.1. The section regex must be replaced by keying off the Einzelnorm heading that `read_legal_html()` already extracts, so that Anlagen become first-class units with their own locators.

### 2.3 The `authority` field

Currently derived from `document_type`, which labels both Handreichungen `internal_guidance`. That is wrong twice: they are external third-party publications rather than internal material (§5), and the field conflates *where a document came from* with *how binding it is*.

The planning doc's severity model depends on the second distinction. `blocker` is reserved for violations of binding PflAPrV requirements; `pruefen` covers state or advisory guidance. Replace with an explicit enum:

```
binding_federal        PflBG, PflAPrV, Anlage 2
official_state         Bay. StMUK Operatorenliste
third_party_advisory   PflegePlus Handreichungen, BW Leitfaden (state-issued, non-binding)
```

Severity then derives from the rule's source authority rather than being hand-assigned per rule.

### 2.4 `evaluation/queries.jsonl`

Six cases, against the README's own target of 20–30. Keep the format and the harness — `evaluate.py` is clean, reports the rank of the first match, and exits non-zero on failure, which makes it CI-able.

One caution: this measures **retrieval**, which is a supporting metric. It is not product evaluation and must not be allowed to stand in for it. The planning doc's mutation harness (§7.2) measures whether the tool *flags correctly*; retrieval recall measures whether the evidence for a flag was findable. Both should exist, reported separately.

---

## 3. Remove

| Item | Why |
|---|---|
| `chunk_text()` in `ingest.py` | Dead path, superseded by `_paragraph_chunks()` in `chunking.py`. Two overlapping character splitters with different constants is a latent bug. Its own `TODO` says it is not the final solution. |
| Config-constant duplication | `config.py` declares `TARGET_CHARS=1800`, `MAX_CHARS=2600`, `OVERLAP_CHARS=250`; `chunk_text` defaults to 2600/250; `_paragraph_chunks` defaults to 1800 and never reads config. The config values are not wired in. Wire them or delete them. |
| **FAISS** | 443 chunks. Brute-force cosine over a numpy array is exact, instant, and removes the `faiss-cpu` dependency. Reintroduce if the corpus passes ~50k chunks. |
| **The reranker plan** | Unjustifiable at this corpus size and a distraction from the rule catalogue, which is where quality actually comes from. |
| **Qwen3-14B commitment** | Superseded. The planning doc's ceiling/floor pair is `gpt-oss-120b` / `gpt-oss-20b`, deliberately same-family so the measured delta is a clean size effect. The handoff's "start with 14B not 8B" and "do not integrate Qwen3-14B yet" are both moot. |
| **Gradio / FastAPI UI direction** | Superseded by Word comment writeback plus an annotated HTML report. The handoff's own "AI sidebar" framing points at the Word task pane, which is the deferred real surface. |
| `rules/example_rules.yaml` | Empty placeholder. Delete rather than grow into; the catalogue schema is defined in the planning doc §3.3. |
| `source_id` compatibility alias | `chunk_document()` retains it "for compatibility with existing stored artefacts." No such legacy exists in a one-week-old repo. |
| The 11-item "Potential AI capabilities" list in `handdown.md` | Scope creep. Superseded by three flag families with defined boundaries. |
| "Production target ~20 concurrent users" | Not a PoC concern; deferring it costs nothing and it currently justifies infrastructure choices the PoC should not be making. |
| `.vscode/extensions.json` | Noise. |

`scripts/download_legal_sources.py` is worth keeping despite the raw HTML being committed — it is how the corpus gets refreshed when the law changes.

---

## 4. Defects

### 4.1 BLOCKING — Anlage 1 and Anlage 2 are both cited as "§ 62"

Verified against the committed index. Every chunk of the Anlage competency tables carries `source_locator: "§ 62"` and `structure: {"section": "§ 62", "paragraph": null}`, including the chunks containing the Kompetenzbereich I text that Family B exists to map against.

Cause: `read_legal_html()` correctly extracts the Anlagen (they are `Einzelnorm` divs like everything else), but `LegalChunker.SECTION` matches only `^§\s*(\d+)`. Anlage headings never open a new section, so their content is absorbed into whatever § preceded them.

Three consequences, in ascending severity:

1. Anlage 1 and Anlage 2 are **indistinguishable** in the index. Only the Fundstelle page range differs (1592–1595 versus 1596–1600), and nothing keys on it.
2. **Family B has no citable target.** Anlage 2 is the entire competency blueprint. A competency-mapping flag cannot cite the competency it mapped to.
3. Under the planning doc's §4.1 "no flag without evidence," a flag citing `§ 62` for an Anlage 2 competency is a **fabricated citation**. That is worse than producing no flag, and it is precisely the failure mode the evidence rule exists to prevent.

Fix: derive the locator from the Einzelnorm heading text, so `Anlage 2 (zu § 7 Absatz 3 …)` becomes its own unit. Then structure Anlage 2 by Kompetenzbereich (I–V) and numbered competency, because that is the granularity Family B tags at.

### 4.2 The official Bay. StMUK operator list is skipped entirely

`OperatorHandreichungChunker.chunk()` starts at `document.text.find("3.2 Erweiterte Operatorenliste", 1500)`. Section 3.1 of that Handreichung is the **Liste der Operatoren des Bay. StMUK** — the official Bavarian ministry list. It is dropped; only the authors' extended list at 3.2 is captured.

This is backwards from an authority standpoint. The StMUK list is the official, citable one that a Bavarian Prüfungsausschuss is actually bound by in spirit; 3.2 is a third-party extension of it. Both should be captured and tagged distinctly, and the StMUK list should be obtained from StMUK directly rather than via a secondary reproduction.

### 4.3 Fragile magic offsets

`find(..., 1500)` skips the table of contents by character position. `body[max(0, match.start() - 180):match.start()]` finds the Anforderungsbereich by looking backwards a fixed 180 characters. Both are tuned to the current pypdf text extraction of the current PDF revision. A pypdf upgrade or a document revision changes results silently.

Mitigation, and it also resolves 4.4: **freeze the extracted records to a committed JSON artifact and treat the parser as a one-time migration tool.** Once `operators.yaml` and the checklist rules exist as reviewed, version-controlled data, nothing at runtime depends on regex-parsing a PDF. This is both more robust and simpler than hardening the parser.

### 4.4 Anforderungsbereich inference is positional luck

It worked — 0 of 26 nulls — but it works by scanning backwards for a heading within a fixed window. Resolved by 4.3.

### 4.5 `minmax` scores are per-query

Hybrid scores are normalised across the candidate set of each individual query, so they are comparable *within* a query and meaningless *across* queries. Fine for ranking. Never threshold on them, and do not display them as confidence.

### 4.6 Provenance fields declared but never populated

`effective_from`, `effective_to`, and `legal_status` are in the common chunk schema; `legal_status` is populated for legal HTML, the two date fields never are. Empty provenance fields are worse than absent ones because they imply versioning exists. Either populate them from the `standangaben` table or drop them until they are implemented.

### 4.7 Full scan on filtered search

`dense_limit = index.ntotal if filters else TOP_K_DENSE` scans the whole index whenever a filter is set. The comment correctly explains why (avoiding silent exclusion of a valid chunk with low global rank). Fine at 443 chunks; noted so it is not forgotten if the corpus grows.

---

## 5. Provenance and copyright — needs resolving before the corpus ships

Both Handreichungen are **third-party copyrighted works, not public-sector documents**:

> Herausgeber: Anna Kamm (Diakoneo Berufsfachschulen für Pflege), Prof. Dr. Jörg Roche (Ludwig-Maximilians-Universität München). November 2025. PflegePlus, ILS GmbH, Karben. www.pflegeplus-sprache.de

This matters because the planning doc's §6.2 and §7.1 both rest on the corpus being public legal and curricular text only, which is what makes the non-EU free-tier providers acceptable. These PDFs are not that.

Three actions:

1. **Get the Bay. StMUK Operatorenliste from StMUK directly.** It is official, it is the citable authority for FORM-03 and FORM-04, and sourcing it first-hand removes the dependency on a secondary reproduction.
2. **Word the checklist-derived rules independently.** Using the checklist's *substance* as rule ideas is defensible; reproducing its *formulation* as `rule_text` is not. The `source` field cites the Handreichung; the rule text is the team's own wording. This is also better practice for a rule catalogue that has to be maintainable.
3. **Ask the authors about the Erweiterte Operatorenliste** before treating it as project data. Contact details are in the PDF.

That third point is worth doing early for a reason beyond licensing. Anna Kamm is at Diakoneo Berufsfachschulen für Pflege — a Bavarian multi-site nursing training provider, which is the buyer profile the planning doc identifies, and Roth is a Bavarian site. One conversation potentially resolves the licence question, supplies the nursing-education subject-matter expert the plan needs for seed-item face validity, and opens a pilot channel. These are not obstacles to route around; they are the most plausible allies in the whole project.

---

## 6. Two corrections this repo forces in the planning doc

### 6.1 §3.2 is partly wrong — Bavaria-relevant guidance does exist

The planning doc states that Bavaria has no published written-exam item-writing guidance. That stands for a *comprehensive Leitfaden* comparable to Baden-Württemberg's. But this repo contains:

- an official **Bay. StMUK Operatorenliste** (reproduced at §3.1 of the Operatoren Handreichung), and
- two **Bavarian-authored 2025 Handreichungen** covering operator use and sprachsensible Leistungserhebung, the second with a concrete 27-item checklist for Fallsituationen and Aufgabenstellungen.

For a Bavarian pilot these are *better* rule sources than BW's Leitfaden: closer to the target jurisdiction, more recent, and more directly operationalisable. §3.1 and §3.2 of the planning doc should be revised, and BW's Leitfaden should be demoted from primary rule source to cross-check.

### 6.2 Family A can be larger and better grounded than estimated

The planning doc targets roughly 10 Family A rules with a note that the count should be fixed only after reading the Leitfaden. Between the 27 checklist items and the 26-operator table, Family A can plausibly reach 15–20 rules with genuine source backing, and part of Week 1's curation is already complete.

Also update §5.3 (Chroma) to numpy plus BM25, per §3 above.

---

## 7. Migration checklist

1. Fix `LegalChunker` for Anlagen; re-index; verify Anlage 2 chunks carry an Anlage locator and a Kompetenzbereich. **Blocks Family B.**
2. Capture Handreichung §3.1 (StMUK list) separately from §3.2, tagged by authority.
3. Freeze operator records to `rules/operators.yaml`; retire the PDF parser to a one-shot migration script.
4. Convert the 27 checklist items to candidate rules with independently worded `rule_text`, `requires`, `input_slice`, and `mutation`.
5. Replace the `authority` field with the three-value enum; derive severity from it.
6. Mine the 15 example pairs for both few-shot context and real-world mutation instances.
7. Delete `chunk_text()`, `example_rules.yaml`, the `source_id` alias, and the config duplication.
8. Drop FAISS for numpy brute-force; remove `faiss-cpu`.
9. Expand `queries.jsonl` toward 20–30 cases; keep it clearly separate from the mutation harness.
10. Resolve the PflegePlus licence question and request the StMUK list.
