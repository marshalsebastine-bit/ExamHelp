"""Week 2 German-quality spot check (tech doc 6.5): a handful of real
Fachsprache Teilaufgaben run through the KOMP-01 classifier -- the one LLM
task currently wired up -- with the result written out for hand-grading.

KOMP-01's output is a constrained code list, not free German prose (see
gateway/model_gateway.py::PROMPT_TEMPLATE), so there is nothing to grade for
fluency. What tech doc 6.5's question reduces to here is comprehension: does
the model, reading real German Pflege-Fachsprache, pick the Anlage-2 codes a
human grader would also pick? That is what this script surfaces, one
Teilaufgabe at a time, for a human to actually grade -- it does not grade
itself.

Selection is deterministic, not random: one qualifying Teilaufgabe per item
(round-robin across items/*.json in filename order, so the sample spans
items and curriculare Einheiten instead of clustering inside one item) with
a non-empty candidate set. A Teilaufgabe with candidates == [] short-circuits
to an empty result with no model call at all (candidate_kompetenzen's
CE-maps-to-nothing case), so it has nothing to spot-check. As of 2026-09,
every Teilaufgabe in the 12-item corpus has a real (12-28 code) candidate
set -- neither the CE-maps-to-nothing empty case nor the CE-not-declared
85-code fallback appears in the corpus, so this sample cannot exercise
either; that is a corpus-coverage fact, not a bug in this script.

Also writes every raw LLM response (the literal completion text, before this
project's own json.loads/candidate-filtering) to logs/, one line per call --
useful for spotting a malformed or non-JSON response that classify_kompetenz's
parsing would otherwise silently turn into an empty result. Calls the backend
directly rather than through classify_kompetenz for this reason: the cached,
filtered path is exactly what this spot check needs to see underneath.

Usage: MISTRAL_API_KEY=... .venv/bin/python scripts/spot_check_german_quality.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from checks.catalogue import load_anlage_2_text
from checks.llm.kompetenz_candidates import candidate_kompetenzen
from gateway.model_gateway import _build_prompt, get_backend
from schemas.aufgabe import Aufsichtsarbeit

ITEMS_DIR = ROOT / "items"
SAMPLE_SIZE = 8
OUTPUT = ROOT / "docs" / "week2-german-quality-spot-check.md"
LOGS_DIR = ROOT / "logs"


def load_items() -> list[Aufsichtsarbeit]:
    paths = sorted(p for p in ITEMS_DIR.glob("*.json") if p.name != "manifest.json")
    return [Aufsichtsarbeit.model_validate(json.loads(p.read_text(encoding="utf-8"))) for p in paths]


def first_qualifying_teilaufgabe(aufgabe: Aufsichtsarbeit) -> dict | None:
    for ai, block in enumerate(aufgabe.aufgaben):
        for ti, teilaufgabe in enumerate(block.teilaufgaben):
            if not teilaufgabe.text:
                continue
            ce = teilaufgabe.situationsmerkmale.curriculare_einheit
            candidates = candidate_kompetenzen(ce)
            if not candidates:
                continue
            return {
                "aufgabe_id": aufgabe.aufgabe_id,
                "anchor": aufgabe.teilaufgabe_id(ai, ti),
                "ce": ce,
                "text": teilaufgabe.text,
                "candidates": candidates,
            }
    return None


def collect_sample() -> list[dict]:
    sample = [entry for aufgabe in load_items() if (entry := first_qualifying_teilaufgabe(aufgabe))]
    return sample[:SAMPLE_SIZE]


def run() -> None:
    kompetenz_text = load_anlage_2_text()
    sample = collect_sample()
    if not sample:
        print("No Teilaufgabe with a non-empty candidate set found -- nothing to spot-check.")
        return

    LOGS_DIR.mkdir(exist_ok=True)
    backend = get_backend()
    log_path = LOGS_DIR / f"spot_check_llm_responses_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.txt"
    log_lines = [f"Model: {backend.model} (provider resolved via MODEL_PROVIDER, see gateway/model_gateway.py)", ""]

    lines = [
        "# Week 2 German-quality spot check (tech doc 6.5)",
        "",
        f"Model: {backend.model}",
        "",
        "Grade each row: does the model's chosen code set match what a human grader",
        "reading the Teilaufgabe and the candidate Anlage-2 texts would pick? Note any",
        "case where German Fachsprache seems to have been misread, not just any",
        "disagreement on borderline competency scope.",
        "",
    ]

    for entry in sample:
        header = f"{entry['aufgabe_id']} {entry['anchor']}"
        prompt = _build_prompt(entry["text"], entry["candidates"], kompetenz_text)
        raw = backend.complete(prompt, json_mode=True, temperature=0.0)
        try:
            codes = json.loads(raw).get("codes", [])
        except (json.JSONDecodeError, AttributeError):
            codes = []
        result = sorted(set(codes) & set(entry["candidates"]))

        log_lines.append(f"=== {header} ===")
        log_lines.append(f"Teilaufgabe: {entry['text']}")
        log_lines.append(f"Candidates ({len(entry['candidates'])}): {', '.join(entry['candidates'])}")
        log_lines.append("Raw LLM response:")
        log_lines.append(raw)
        log_lines.append(f"Parsed + filtered to candidate set: {result}")
        log_lines.append("")

        lines.append(f"## {header}  (CE: {entry['ce'] or 'none declared'})")
        lines.append("")
        lines.append(f"**Teilaufgabe:** {entry['text']}")
        lines.append("")
        lines.append(f"**Candidate codes ({len(entry['candidates'])}):**")
        for code in entry["candidates"]:
            lines.append(f"- {code}: {kompetenz_text.get(code, '(kein Text verfuegbar)')}")
        lines.append("")
        lines.append(f"**Model chose:** {result or '(none)'}")
        lines.append("")
        lines.append("**Grade (correct / wrong / unsure):** ")
        lines.append("")
        lines.append("---")
        lines.append("")
        print(f"{header}: candidates={entry['candidates']} -> chosen={result}")

    log_path.write_text("\n".join(log_lines), encoding="utf-8")
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {log_path.relative_to(ROOT)} (raw LLM responses)")
    print(f"Wrote {OUTPUT.relative_to(ROOT)} -- fill in the grade column by hand.")


if __name__ == "__main__":
    run()
