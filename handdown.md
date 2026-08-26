# Handoff — AI-Assisted German Nursing Exam Creation Tool

## Purpose

We are building a self-hosted AI-assisted exam authoring tool for the German nursing professional field.

The user writes:
- a case/scenario
- subquestions
- expected answers / marking scheme

The AI sidebar should review the material against:
- German nursing/examination legislation
- examination requirements/guidelines
- internal Handreichungen/checklists/rubrics

and provide:
- potential compliance issues
- question-quality issues
- competency alignment issues
- source-backed explanations
- suggested wording changes

## Constraints

- Confidential/protected material: no public LLM APIs in production
- Use open-weight, self-hosted models
- Production target: ~20 concurrent users
- Phase 1 prototype: one active user
- Phase 1 includes RAG + deterministic rules
- Start with a 14B model, not 8B

---

# Current Phase: RAG-first prototype

Do not integrate the 14B model yet.

Current target:

```text
Authoritative documents
        |
        v
Document-type-specific ingestion
        |
        v
Structured chunks + common metadata
        |
        +------------------+
        |                  |
        v                  v
   BGE-M3 embeddings     BM25
        |                  |
        v                  v
      FAISS        lexical retrieval
        |                  |
        +--------+---------+
                 |
                 v
          Hybrid retrieval
                 |
                 v
          later: reranker
                 |
                 v
             Qwen3-14B
                 |
                 v
       findings + citations
       + suggested changes
```

---

# Architecture decision: extensible document types

We expect 3+ document types as the system grows.

Do NOT hard-code the RAG system around only "legal" and "Handreichung".

Prefer a registry pattern:

```python
chunkers = {
    "legal": LegalChunker(),
    "handreichung": HandreichungChunker(),
    # future:
    # "checklist": ChecklistChunker(),
    # "guideline": GuidelineChunker(),
    # "standard": StandardChunker(),
}
```

The RAG core stays generic.

## Common metadata

Every chunk should have common fields such as:

```text
chunk_id
document_id
document_type
title
source_file
text
source_locator
chunk_index
authority
effective_from
effective_to
```

Then allow type-specific metadata under `structure` and/or semantic-content fields.

Example legal:

```json
{
  "document_type": "legal",
  "source_locator": "§ 15",
  "structure": {
    "section": "§ 15",
    "paragraph": "2",
    "sentence": null,
    "number": null
  }
}
```

Example Handreichung/operator:

```json
{
  "document_type": "handreichung",
  "content_type": "operator",
  "operator": "analysieren",
  "anforderungsbereich": "II",
  "structure": {
    "chapter": "3.2",
    "section": "Erweiterte Operatorenliste"
  }
}
```

Example checklist:

```json
{
  "document_type": "handreichung",
  "content_type": "checklist_item",
  "checklist_name": "Sprachsensible Leistungserhebung",
  "category": "Fallsituation",
  "structure": {
    "chapter": "Anhang 1"
  }
}
```

Principle:

> Common metadata for retrieval/filtering + type-specific metadata for citation/interpretation.

Do not force every document type to have legal fields such as `§` or `Absatz`.

---

# Uploaded source documents

Two real Handreichungen were uploaded and inspected.

## 1. Umgang mit Operatoren in der Pflegeausbildung

Filename:

```text
01 Handreichung Operatoren_PflegePlus.pdf
```

Observed structure:

```text
Handreichung
├── 1 Einleitung
├── 2 Operatoren in der Pflegeausbildung
└── 3 Operatorenlisten
    ├── 3.1 Liste der Operatoren des Bay. StMUK
    └── 3.2 Erweiterte Operatorenliste
          ├── Anforderungsbereich
          ├── Operator
          ├── Aufgabenstellung
          ├── Erklärung
          ├── Redemittel
          ├── Beispiel-Aufgabenstellung
          └── Beispiel-Antwort
└── Literatur
```

The document states that operator use helps structure/formulate exam questions, align tasks with competence requirements, and support differentiated assessment.

It explicitly identifies these elements for checking a question:
- Operator
- Schlüsselbegriff(e)
- Situationsbezug
- ggf. Anzahl der erforderlichen Nennungen

The document's operator entries are highly structured and should not be treated as arbitrary prose chunks.

Recommended semantic content type:

```text
content_type = operator
```

Possible fields:

```text
operator
anforderungsbereich
task_formulation
explanation
redemittel
example_question
example_answer
```

The document distinguishes:
- Anforderungsbereich I: Reproduktion
- Anforderungsbereich II: Transfer / Anwenden
- Anforderungsbereich III: Problemlösen / Werten

---

## 2. Sprachsensibel Prüfen in der Pflegeausbildung

Filename:

```text
02 Handreichung Sprachsensibel Prüfen_PflegePlus.pdf
```

Observed structure:

```text
1. Einleitung
2. Sprachsensible Leistungserhebung
3. Strategien für die sprachliche Gestaltung
    3.1 Fallsituationen
    3.2 Aufgabenstellungen
4. Strategien für Auszubildende
5. Fazit
Anhang 1: Checkliste
Literatur
```

Important distinctions:
- guidance for Fallsituationen
- guidance for Aufgabenstellungen
- text-, sentence- and word-level considerations
- explicit checklist in Anhang 1

Potential content types:

```text
guidance
recommendation
example
checklist_item
example_pair
```

The document also contains "Schwer verständlich" vs "Leicht verständlich" examples. Preserve them as linked example pairs where possible.

---

# Current code/artifacts

A first RAG starter was created:

```text
rag_phase1_starter.zip
```

Then upgraded to:

```text
rag_phase1_structure_aware.zip
```

The structure-aware project contains approximately:

```text
app/
    chunking.py
    ingest.py
    config.py

scripts/
    build_index.py

data/
    raw/
        legal/
        handreichung/
    processed/
    index/

evaluation/
rules/
requirements.txt
README.md
```

The structure-aware code passed a Python compilation check.

## Current stack

- Embeddings: `BAAI/bge-m3`
- Dense retrieval: FAISS
- Lexical retrieval: BM25
- Later: reranker
- Phase-1 LLM: Qwen3-14B
- Prototype API/UI: FastAPI + simple UI/Gradio
- Initial storage: filesystem + SQLite

---

# Current chunking implementation

## Legal

The current prototype:
- recognizes section-style headers such as `§ 15`
- preferentially splits large sections around `(1)`, `(2)`, etc.
- falls back to numbered items and then conservative character splitting

However:

> The legal parser is still regex-based and is NOT the final legal ingestion solution.

For official PflBG/PflAPrV, eventually parse the official HTML structure directly where possible:

```text
Gesetz
  -> §
      -> Absatz
          -> Satz
              -> Nummer
```

This is needed for reliable source citations.

## Handreichung

The current structure-aware project has a generic heading/block parser.

This is now known to be too simplistic for the two real Handreichungen.

The next implementation should specialize the Handreichung parser for their actual structures.

---

# RAG processing model

Embedding is primarily an offline/indexing task.

Initial:

```text
documents
  -> parse
  -> structure-aware chunk
  -> embed
  -> FAISS/BM25 index
```

Query time:

```text
user question
  -> query embedding
  -> dense + BM25 retrieval
  -> hybrid results
```

Do not re-embed the whole corpus for each query.

When source documents change, re-process affected documents/chunks if practical.

For legal sources, preserve version/effective dates.

---

# Why PyTorch appeared

The RAG code uses Sentence Transformers.

Conceptually:

```text
our code
  -> Sentence Transformers
      -> PyTorch
          -> BGE-M3
              -> embedding vectors
```

PyTorch is the ML runtime used to execute the embedding model; it is not the RAG algorithm itself.

FAISS stores/searches the resulting vectors.

Later, a similar ML runtime can be used for LLM inference.

---

# Recommended next step

Do NOT integrate Qwen3-14B yet.

First finish the ingestion layer for the two uploaded Handreichungen.

## Immediate implementation task

Refactor ingestion/chunking into an extensible document-type registry.

Then implement a specialized `HandreichungChunker`.

### Operatoren document

Recognize:

```text
Anforderungsbereich
Operator
Aufgabenstellung
Erklärung
Redemittel
Beispiel-Aufgabenstellung
Beispiel-Antwort
```

Each operator should ideally become a coherent structured record/chunk.

Example:

```json
{
  "document_type": "handreichung",
  "content_type": "operator",
  "operator": "begründen",
  "anforderungsbereich": "II",
  "structure": {
    "chapter": "3.2",
    "section": "Erweiterte Operatorenliste"
  },
  "text": "..."
}
```

### Sprachsensibel document

Recognize:

```text
chapter
subsection
guidance/recommendation
example_pair
checklist_item
```

Preserve "Schwer verständlich" / "Leicht verständlich" examples as linked pairs where possible.

---

# Retrieval evaluation before LLM integration

Create a small manually verifiable evaluation set.

Examples:

```text
Query:
"Welche Anforderungen gelten für die Formulierung einer verständlichen Fallsituation?"

Expected:
Sprachsensibel Handreichung / Fallsituationen / relevant guidance

Query:
"Was verlangt der Operator begründen?"

Expected:
Operatoren-Handreichung / content_type=operator / operator=begründen

Query:
"Prüfe diese Aufgabenstellung auf Anzahl der geforderten Nennungen."

Expected:
Operatoren guidance / requirement about explicit number of requested items
```

Measure:
- expected source appears in top-k
- correct content type retrieved
- correct operator/checklist/section retrieved
- source locator correct

---

# After Handreichung retrieval works

1. Add official PflBG/PflAPrV ingestion.
2. Make legal parsing structure-aware using official HTML.
3. Add source/version/effective-date metadata.
4. Add metadata filters to hybrid retrieval.
5. Add reranker.
6. Integrate Qwen3-14B.
7. Add deterministic rules.
8. Build a larger expert-labelled evaluation set.

---

# Product direction

Potential AI capabilities:
- legal/exam compliance checking
- competency alignment
- question-quality review
- question vs expected-answer consistency
- automatic marking-scheme suggestions
- difficulty/cognitive-level analysis
- exam coverage/balance analysis
- ambiguity / alternative-answer detection
- alternative question generation
- candidate/red-team review
- regulation-change impact analysis

The RAG + rules + LLM architecture should support these without redesigning the retrieval layer.

---

# Privacy

Free public notebook/cloud environments are acceptable for:
- public authoritative sources
- synthetic data
- anonymized examples

Do NOT use confidential real examination material in public/free infrastructure.

Production should use private/self-hosted infrastructure.

---

# Useful artifacts from this conversation

Project:

```text
rag_phase1_structure_aware.zip
```

Uploaded source documents:

```text
01 Handreichung Operatoren_PflegePlus.pdf
02 Handreichung Sprachsensibel Prüfen_PflegePlus.pdf
```

The uploaded PDFs are the basis for the Handreichung parsing decisions above.

---

# Instruction for Codex

Start by inspecting the existing `rag_phase1_structure_aware` project.

Then:

1. Refactor document-type handling into a clean extensible registry/plugin pattern.
2. Implement specialized parsing for the two uploaded Handreichungen.
3. Produce structured JSONL chunks.
4. Inspect sample chunks for correctness.
5. Build FAISS + BM25 indexes from those chunks.
6. Run German retrieval test queries and report the retrieved source/content type.
7. Do not integrate Qwen3-14B yet.

Success criterion:

> Given the two Handreichungen, produce clean structured chunks that correspond to meaningful retrieval units, and demonstrate that hybrid retrieval can reliably return the correct operator/guidance/checklist content for several German test queries.

Keep the RAG core model-independent.
