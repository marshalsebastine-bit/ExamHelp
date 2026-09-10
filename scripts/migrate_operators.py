"""One-shot migration: PflegePlus Handreichung 01 -> rules/operators.yaml.

This is a *migration tool*, not a runtime component.  Nothing in the check
runner parses a PDF: the operator table is frozen to reviewed, version-
controlled YAML and the deterministic checks read that (repo review 4.3).
Re-run this only to regenerate the table from a new document revision.

Two things this deliberately records rather than papers over:

1.  Section 3.1, the official *Liste der Operatoren des Bay. StMUK*, is embedded
    as scanned images and carries no extractable text (1 character across its
    three pages).  Phase 1 skipped it via a magic character offset, and repo
    review 4.2 attributes the omission to that offset -- but fixing the offset
    recovers nothing.  The official list needs OCR or, better, first-hand
    acquisition from StMUK (repo review 5, action 1).
2.  What is extractable is section 3.2, the authors' *Erweiterte
    Operatorenliste*.  Its own preamble states it reproduces the binding
    operators "im Originaltext" and extends them, so it is a superset of the
    official list -- but it does not mark which entries are the binding ones.
    Every record is therefore tagged `authority: third_party_advisory` and
    `binding_status: unverified` until the StMUK list is in hand.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml
from pypdf import PdfReader

from corpus.config import RAW_DIR, ROOT

SOURCE_PDF = RAW_DIR / "01 Handreichung Operatoren_PflegePlus.pdf"
TARGET = ROOT / "rules" / "operators.yaml"

SECTION_32 = "3.2   Erweiterte Operatorenliste"
ANFORDERUNGSBEREICH = re.compile(r"(?m)^\s*Anforderungsbereich\s+(I{1,3})\s*:\s*(.+?)\s*$")
OPERATOR = re.compile(r"(?m)^\s*Operator\s+(\S.*?)\s*$")
# Bare page numbers sit between records in the extracted text.
PAGE_NUMBER = re.compile(r"(?m)^\s*\d{1,3}\s*$")


def compact(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def read_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages).replace("\xa0", " ")


def field(record: str, pattern: str) -> str | None:
    found = re.search(pattern, record, re.M | re.S)
    return compact(found.group(1)) if found else None


# Separable-verb particles: the Handreichung lists "ableiten" as the operator but
# formulates it as "Leiten Sie ... ab.", so the fragment cannot be matched on the
# operator's own prefix.
SEPARABLE_PARTICLES = ("ab", "an", "auf", "aus", "ein", "gegenüber", "mit", "nach", "vor", "zu")


def split_formulations(task_formulation: str | None) -> list[str]:
    """Split a grouped row's Aufgabenstellung into one fragment per operator."""
    if not task_formulation:
        return []
    # Fragments are separated by the ellipsis that ends each pattern.
    parts = re.split(r"(?<=…)\s*(?=[A-ZÄÖÜ])|(?<=\bab\.)\s*(?=[A-ZÄÖÜ])", task_formulation)
    return [compact(part) for part in parts if compact(part)]


def formulation_for(operator: str, fragments: list[str]) -> str | None:
    """Pick the Aufgabenstellung fragment belonging to one operator of a group."""
    if not fragments:
        return None
    if len(fragments) == 1:
        return fragments[0]
    stem = operator[:5].casefold()
    for fragment in fragments:
        if fragment[:6].casefold().startswith(stem[:4]):
            return fragment
    # Separable verb: "ableiten" -> root "leiten" plus trailing particle "ab".
    for particle in SEPARABLE_PARTICLES:
        if operator.casefold().startswith(particle):
            root = operator[len(particle):]
            for fragment in fragments:
                if fragment.casefold().startswith(root[:4].casefold()):
                    return fragment
    return None


def parse_operators(text: str) -> list[dict]:
    # Use the LAST occurrence: the first is the table-of-contents entry.
    start = text.rfind(SECTION_32)
    if start < 0:
        raise ValueError(f"Section heading {SECTION_32!r} not found in extracted text")
    body = PAGE_NUMBER.sub("", text[start:])

    # Anforderungsbereich headings partition the list.  Scanning forward and
    # carrying the current area is robust to record length, unlike phase 1's
    # fixed 180-character backward window (repo review 4.4).
    areas = [(m.start(), m.group(1), compact(m.group(2))) for m in ANFORDERUNGSBEREICH.finditer(body)]

    def area_at(position: int) -> tuple[str | None, str | None]:
        current: tuple[str | None, str | None] = (None, None)
        for offset, roman, title in areas:
            if offset < position:
                current = (roman, title)
            else:
                break
        return current

    records: list[dict] = []
    matches = list(OPERATOR.finditer(body))
    for match, following in zip(matches, matches[1:] + [None]):
        end = following.start() if following else len(body)
        record = body[match.start():end]
        row_label = compact(match.group(1))
        roman, area_title = area_at(match.start())

        task_formulation = field(record, r"^Aufgabenstellung\s+(.+?)(?=^\s*Erklärung\s)")
        shared = {
            "explanation": field(record, r"^\s*Erklärung\s+(.+?)(?=^\s*Redemittel\s)"),
            "redemittel": field(record, r"^\s*Redemittel\s+(.+?)(?=^\s*Aufgabenstellung\s*\n\s*\(Beispiel\))"),
            "example_task": field(record, r"^\s*Aufgabenstellung\s*\n\s*\(Beispiel\)\s*(.*?)(?=^\s*Antwort\s*\n\s*\(Beispiel\))"),
            "example_answer": field(record, r"^\s*Antwort\s*\n\s*\(Beispiel\)\s*(.*?)\Z"),
        }

        # One source row can carry several operators that share a description,
        # e.g. "entwickeln, planen, ableiten".  Emitting them as one record would
        # make FORM-03 miss a lookup for "planen" and flag a valid operator as
        # unapproved -- a false flag, which is the metric the PoC cares most about.
        names = [compact(n) for n in row_label.split(",") if compact(n)]
        fragments = split_formulations(task_formulation)
        for name in names:
            records.append(
                {
                    "operator": name.casefold(),
                    "display": name,
                    "anforderungsbereich": roman,
                    "anforderungsbereich_titel": area_title,
                    "task_formulation": formulation_for(name, fragments) or task_formulation,
                    **shared,
                    "source_row": row_label if len(names) > 1 else None,
                }
            )
    return records


def main() -> int:
    if not SOURCE_PDF.exists():
        print(f"Source PDF not present: {SOURCE_PDF}")
        return 1

    text = read_pdf_text(SOURCE_PDF)
    records = parse_operators(text)

    missing = [r["operator"] for r in records if not r["anforderungsbereich"] or not r["task_formulation"]]
    # The same verb can legitimately sit at two Anforderungsbereiche ("ableiten"
    # at II and III), so uniqueness is on the (operator, level) pair, not the name.
    pairs = [(r["operator"], r["anforderungsbereich"]) for r in records]
    duplicates = {p for p in pairs if pairs.count(p) > 1}
    multi_level = sorted({o for o, _ in pairs if sum(1 for x, _ in pairs if x == o) > 1})

    document = {
        "meta": {
            "id": "operators",
            "title": "Operatorentabelle fuer die schriftliche Pflegepruefung (Bayern)",
            "purpose": "Lookup table for FORM-03 (operator is on the list) and FORM-04 (operator matches the declared Anforderungsniveau). A set-membership test, never a similarity search: an invented operator must return nothing rather than its nearest real neighbour (repo review 2.1).",
            "source": {
                "document": "PflegePlus Handreichung 01: Umgang mit Operatoren in der Pflegeausbildung",
                "section": "3.2 Erweiterte Operatorenliste",
                "publisher": "Kamm / Roche, PflegePlus (ILS GmbH), 2025",
                "url": "https://www.pflegeplus-sprache.de",
            },
            "authority": "third_party_advisory",
            "binding_status": "unverified",
            "generated_by": "scripts/migrate_operators.py",
            "open_questions": [
                "The official Liste der Operatoren des Bay. StMUK (section 3.1 of the same document) is scanned images with no extractable text. It must be obtained first-hand from StMUK; it cannot be recovered from this PDF without OCR (repo review 4.2, 5).",
                "Section 3.2's preamble states it reproduces the binding StMUK operators verbatim and extends them, but does not mark which entries are binding. Until the StMUK list is in hand, FORM-03 cannot distinguish 'not an approved operator' from 'approved only in the extended list'.",
                "Licence for the Erweiterte Operatorenliste is unresolved (repo review 5, action 3).",
            ],
            "counts": {
                "entries": len(records),
                "distinct_operators": len({r["operator"] for r in records}),
                "by_anforderungsbereich": {
                    area: sum(1 for r in records if r["anforderungsbereich"] == area)
                    for area in ("I", "II", "III")
                },
            },
        },
        "operators": records,
    }

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    with open(TARGET, "w", encoding="utf-8") as handle:
        yaml.safe_dump(document, handle, allow_unicode=True, sort_keys=False, width=100)

    print(f"Wrote {len(records)} operators to {TARGET.relative_to(ROOT)}")
    print(f"  by Anforderungsbereich: {document['meta']['counts']['by_anforderungsbereich']}")
    print(f"  distinct operators: {len({r['operator'] for r in records})}")
    print(f"  incomplete records: {missing or 'none'}")
    print(f"  duplicate (operator, level) pairs: {sorted(duplicates) or 'none'}")
    print(f"  operators at more than one level: {multi_level or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
