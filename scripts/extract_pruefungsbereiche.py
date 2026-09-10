"""One-shot extraction: PflAPrV § 14 (1) -> rules/pruefungsbereiche.yaml.

§ 14 (1) names, for each of the three written Prüfungsbereiche, the
Kompetenzschwerpunkte it draws on.  That turns KOMP-03 ("the Aufsichtsarbeit
covers its intended Prüfungsbereich") into a deterministic check grounded in
binding federal law rather than a judgement call, and it is the reason KOMP-03
can carry `blocker` severity.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml

from corpus.config import RAW_DIR, ROOT
from corpus.ingest.legal import find_provision, read_legal_html

TARGET = ROOT / "rules" / "pruefungsbereiche.yaml"

# "(Kompetenzschwerpunkte I.1, II.1)", "(Kompetenzschwerpunkt V.1)"
SCHWERPUNKTE = re.compile(r"\(Kompetenzschwerpunkt(?:e)?\s+([IVX0-9.,\s]+?)\)")
# Bereich references appear both parenthesised "(Kompetenzbereich III)" and
# inline "des Kompetenzbereiches IV in die Fallbearbeitung einbezogen".
BEREICH = re.compile(r"Kompetenzbereich(?:es|e|s)?\s+([IVX]{1,3})\b")
CODE = re.compile(r"([IVX]{1,3})\.(\d{1,2})")


def main() -> int:
    provisions = read_legal_html(RAW_DIR / "PflAPrV.html")
    paragraph_14 = find_provision(provisions, "§ 14")
    text = paragraph_14.text
    absatz_1 = text[text.find("(1)"): text.find("(2)")]

    # The three Prüfungsbereiche are the numbered items of Absatz 1.
    items = re.split(r"(?m)^\s*([123])\.\s*$", absatz_1)
    bereiche = []
    for number, body in zip(items[1::2], items[2::2]):
        body = re.sub(r"\s+", " ", body).strip().rstrip(",.")
        schwerpunkte = sorted(
            {f"{r}.{n}" for group in SCHWERPUNKTE.findall(body) for r, n in CODE.findall(group)}
        )
        bereiche.append(
            {
                "nummer": int(number),
                "titel": body.split("(")[0].strip().rstrip(",") or None,
                "kompetenzschwerpunkte": schwerpunkte,
                "einzubeziehende_kompetenzbereiche": sorted(set(BEREICH.findall(body))),
                "quote": body,
            }
        )

    document = {
        "meta": {
            "id": "pruefungsbereiche",
            "title": "Die drei schriftlichen Pruefungsbereiche und ihre Kompetenzschwerpunkte",
            "purpose": "Lookup for KOMP-03. PflAPrV § 14 (1) states which Kompetenzschwerpunkte each written Pruefungsbereich draws on, so coverage is decidable deterministically against binding law.",
            "source": {
                "document": "PflAPrV",
                "locator": "§ 14 Absatz 1",
                "url": "https://www.gesetze-im-internet.de/pflaprv/__14.html",
                "authority": "binding_federal",
            },
            "generated_by": "scripts/extract_pruefungsbereiche.py",
            "counts": {"pruefungsbereiche": len(bereiche)},
        },
        "pruefungsbereiche": bereiche,
    }
    with open(TARGET, "w", encoding="utf-8") as handle:
        yaml.safe_dump(document, handle, allow_unicode=True, sort_keys=False, width=100)

    print(f"Wrote {len(bereiche)} Pruefungsbereiche to {TARGET.relative_to(ROOT)}")
    for bereich in bereiche:
        print(f"  {bereich['nummer']}. Schwerpunkte {bereich['kompetenzschwerpunkte']} "
              f"| zusaetzlich Bereich {bereich['einzubeziehende_kompetenzbereiche'] or '-'}")
        print(f"     {(bereich['titel'] or '')[:88]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
