"""Week 2's closing deliverable (tech doc plan, handdown02.md 5): run the
full check catalogue, sequenced by checks/runner.py, against a 3-item smoke
set spanning the corpus's risk tiers -- not just the happy path:

- A-01: a clean item. Exercises the "mostly passes" path.
- C-03: a deliberate-defect item (items/manifest.json's known_weaknesses).
  Exercises real Flags across both Family A and Family B.
- D-01: a deliberately incomplete draft (one Aufgabe block, no
  Erwartungshorizont). Exercises NotChecked paths that a from-scratch item
  actually hits, not just a manufactured edge case.

Uses gateway.model_gateway.classify_kompetenz for KOMP-01 when a model
provider is actually reachable; falls back to classify=None (same
"skip cleanly without one" posture as tests/test_gateway_integration.py)
if the gateway call fails, so this script runs even fully offline.

Usage: .venv/bin/python scripts/smoke_run.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from checks.catalogue import load_anlage_2_text
from checks.runner import run_checks
from gateway.model_gateway import classify_kompetenz, get_backend
from schemas.aufgabe import Aufsichtsarbeit
from schemas.flag import CheckResult

ITEMS_DIR = ROOT / "items"
LOGS_DIR = ROOT / "logs"
SMOKE_SET = ["A-01", "C-03", "D-01"]


def load(name: str) -> Aufsichtsarbeit:
    return Aufsichtsarbeit.model_validate(json.loads((ITEMS_DIR / f"{name}.json").read_text(encoding="utf-8")))


def resolve_classifier():
    """A real classify + its model label if the gateway is actually
    reachable right now, else (None, None) -- probed once with a cheap call
    rather than assumed from whether an API key is merely set, since a set
    key does not guarantee the provider actually answers (this project's
    own recent history: an active Mistral key that 429'd on one model)."""
    try:
        kompetenz_text = load_anlage_2_text()
        classify_kompetenz("Testaufruf.", ["I.1.a"], kompetenz_text=kompetenz_text)
        backend = get_backend()
        return classify_kompetenz, backend.model
    except Exception as exc:
        print(f"Model gateway not reachable ({type(exc).__name__}: {exc}); running KOMP-01 as classify=None.")
        return None, None


def render(result: CheckResult) -> list[str]:
    lines = [f"=== {result.aufgabe_id} ===", f"model: {result.model}", f"coverage: {result.coverage}", ""]
    if result.flags:
        lines.append(f"Flags ({len(result.flags)}):")
        for flag in sorted(result.flags, key=lambda f: (f.anchor, f.rule_id)):
            lines.append(f"  [{flag.severity}/{flag.mechanism}] {flag.rule_id} @ {flag.anchor}: {flag.finding}")
    else:
        lines.append("Flags: none")
    lines.append("")
    lines.append(f"NotChecked ({len(result.not_checked)}):")
    for nc in sorted(result.not_checked, key=lambda n: (n.rule_id, n.anchor or "")):
        anchor = f" @ {nc.anchor}" if nc.anchor else ""
        lines.append(f"  {nc.rule_id}{anchor}: {nc.reason}")
    lines.append("")
    return lines


def run() -> None:
    classify, model = resolve_classifier()

    all_lines: list[str] = [f"Smoke run over {SMOKE_SET}, model={model!r}", ""]
    for name in SMOKE_SET:
        result = run_checks(load(name), classify=classify, model=model)
        block = render(result)
        all_lines.extend(block)
        print("\n".join(block))

    LOGS_DIR.mkdir(exist_ok=True)
    log_path = LOGS_DIR / f"smoke_run_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.txt"
    log_path.write_text("\n".join(all_lines), encoding="utf-8")
    print(f"Wrote {log_path.relative_to(ROOT)}")


if __name__ == "__main__":
    run()
