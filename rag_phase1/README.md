# Phase 1 RAG Prototype — German Nursing Exam Assistant

This is a small, model-independent RAG foundation for the AI-assisted German nursing exam authoring project.

## Goal

Build and evaluate:

- authoritative-source ingestion
- structure-aware chunking
- BGE-M3 embeddings
- FAISS dense retrieval
- BM25 lexical retrieval
- simple hybrid ranking
- source/paragraph metadata
- retrieval evaluation

The 14B generation model is deliberately separate. Qwen3-14B can be plugged in after retrieval quality is validated.

## Initial authoritative corpus

Start with official German federal sources:

- Pflegeberufegesetz (PflBG)
- Pflegeberufe-Ausbildungs- und -Prüfungsverordnung (PflAPrV)

Official source pages:

- https://www.gesetze-im-internet.de/pflbg/
- https://www.gesetze-im-internet.de/pflaprv/

The current prototype also contains two Handreichungen. Their parsers are deliberately
specialised: operator entries become structured records, while the language-sensitive
guide yields guidance, linked difficult/easy example pairs, and checklist items. The parser
registry in `app/chunking.py` keeps future document types isolated from the RAG core.

Add school/internal exam guidelines later under `data/raw/`.

## Install

Python 3.11+ is recommended.

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
```

## Build the first index

Put source files (`.html`, `.txt`, or `.pdf`) into `data/raw/`.

Then:

```bash
python scripts/build_index.py
```

This creates:

- `data/processed/chunks.jsonl`
- `data/index/faiss.index`
- `data/index/metadata.json`
- `data/index/bm25.pkl`

### Official legal sources

The included PDFs remain a fallback. For clean provision-level legal chunks, download
the official HTML before rebuilding; the build automatically prefers HTML over a same-named PDF:

```bash
python3 scripts/download_legal_sources.py
HF_HUB_OFFLINE=1 python3 scripts/build_index.py
```

## Test retrieval

```bash
python scripts/query.py "Welche Kompetenzen werden im mündlichen Teil der staatlichen Prüfung geprüft?"
```

## Evaluate retrieval

Run the manually labelled checks and require the expected result within the top three:

```bash
HF_HUB_OFFLINE=1 python3 scripts/evaluate.py
```

Use `--top-k 5` to inspect a more permissive threshold while improving retrieval.

## Important

Do not use confidential examination material in public/free notebook environments. Use public legal sources and synthetic/anonymized examples during Phase 1.

## Next milestone

1. validate retrieval with an expert-labelled test set;
2. add a reranker;
3. add Qwen3-14B;
4. make the LLM reason only over retrieved evidence;
5. add deterministic examination rules.
