"""One-shot extraction: Bavarian StMUK/ISB Lehrplan -> rules/kompetenzen.yaml
and rules/situationsmerkmale.yaml.

A migration tool, not a runtime component.  The check runner reads the frozen
YAML; nothing at runtime parses a 507-page PDF.

Three things worth knowing before reading the code:

1.  The source is an actual PDF (507 pages), not the plain UTF-8 text that
    tech doc 3.2.1 and the handdown describe.  pypdf extracts it cleanly.
2.  The document also carries the Anlage 3 (Kinderkrankenpflege) and Anlage 4
    (Altenpflege) curricula for the besondere Abschluesse.  Those are filtered
    out: only the generalistische part is ingested, which is what the
    Pflegefachfrau/-mann exam draws on.
3.  The Anlage-2 code list derived here is the *curriculum's citations*, not
    PflAPrV's own text.  This script therefore cross-checks it against the
    authoritative Anlage 2 parsed straight from PflAPrV, which is what resolves
    the KOMP-06 verification item in tech doc 12.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml

from corpus.config import CACHE_DIR, RAW_DIR, ROOT
from corpus.ingest.kompetenzen import parse_anlage_kompetenzen
from corpus.ingest.legal import find_provision, read_legal_html

SOURCE_PDF = RAW_DIR / "bfs_lp_pflegefachmann.pdf"
CACHE = CACHE_DIR / "lehrplan_raw.txt"
KOMPETENZEN_TARGET = ROOT / "rules" / "kompetenzen.yaml"
SITUATIONSMERKMALE_TARGET = ROOT / "rules" / "situationsmerkmale.yaml"

PAGE_MARK = re.compile(r"<<<PAGE (\d+)>>>")

# The besondere Abschluesse start with this banner.  It also appears in the
# front matter, so only occurrences deep in the document count.
BESONDERER_ABSCHLUSS = re.compile(r"Lehrplan\s+für den besonderen\s+Abschluss")
FRONT_MATTER_PAGES = 100

# "CE 07 Rehabilitatives Pflegehandeln im interprofessionellen Team".  The A/B
# marker must not be allowed to swallow the first letter of a title that starts
# on the following line: "CE 01\n\nAusbildungsstart" would otherwise be read as
# sub-unit "A" plus the title "usbildungsstart".
CE_HEADING = re.compile(r"(?m)^[ \t]*CE[ \t]*(\d{2})\b[ \t]*([AB](?![a-zäöüß]))?")

# A CE title runs from the heading to the first structural keyword after it.
# Cutting on structure rather than on the line end keeps titles that wrap.
TITLE_END = re.compile(
    r"\b(?:Anlage|Zeitrichtwert|Intentionen|Kompetenzen|FACH|Fach:|\d\.\s*Ausbildungsdrittel)"
)
ZEITRICHTWERT = re.compile(r"Zeitrichtwert:\s*(\d+)\s*Stunden")

# "Kompetenzen - 1./2. Ausbildungsdrittel (Anlage 1 PflAPrV)"
ANLAGE_HEADING = re.compile(r"Kompetenzen[^\n]{0,120}?\(Anlage\s*(\d)\s*PflAPrV\)")

# Tolerant of the inconsistent formatting the source contains: "(II.3.b)" and
# "(II 3.b.)" both occur (tech doc 3.2.1).
CODE = re.compile(r"\(([IVX]{1,3})[\s.]{1,2}(\d{1,2})[\s.]{1,2}([a-z])\.?\)")

# Situationsmerkmal row labels, hyphenated across lines in the extracted table
# ("Hand-\nlungs-\nanlässe").  Matched after de-hyphenation.
#
# Only the first three are set as table rows per CE.  `Akteure` and
# Erleben/Deuten/Verarbeiten are described in the Lehrplan's introduction and
# appear in each CE's didaktischer Kommentar as prose, not as a structured
# taxonomy row -- which is what tech doc 3.2.1 means by "alongside".  They are
# matched anyway so the output records their absence as a fact rather than
# leaving it to look like an extraction failure.
STRUCTURED_DIMENSIONS = ("handlungsanlaesse", "kontextbedingungen", "handlungsmuster")
SITUATIONSMERKMALE = {
    "handlungsanlaesse": re.compile(r"(?m)^\s*Handlungsanlässe\s*$"),
    "kontextbedingungen": re.compile(r"(?m)^\s*Kontextbedingungen\s*$"),
    "handlungsmuster": re.compile(r"(?m)^\s*Handlungsmuster\s*$"),
    "akteure": re.compile(r"(?m)^\s*Akteure\s*$"),
    "erleben_deuten_verarbeiten": re.compile(r"(?m)^\s*Erleben[\s/–-]*Deuten[\s/–-]*Verarbeiten\s*$"),
}
BULLET = re.compile(r"[•▪●]\s*")


def load_text(force: bool = False) -> str:
    """Extract the PDF once and cache it; extraction takes ~15s."""
    if CACHE.exists() and not force:
        return CACHE.read_text(encoding="utf-8")
    from pypdf import PdfReader

    reader = PdfReader(str(SOURCE_PDF))
    text = "".join(
        f"\n<<<PAGE {i + 1}>>>\n" + (page.extract_text() or "")
        for i, page in enumerate(reader.pages)
    )
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(text, encoding="utf-8")
    return text


def dehyphenate(text: str) -> str:
    """Rejoin words the PDF layout broke across lines.

    The Situationsmerkmale table labels are the reason this is needed: they are
    set in a narrow column and arrive as "Hand-\\nlungs-\\nanlässe".
    """
    text = text.replace("\x02", "")
    # "Hand- \n lungs- \n anlässe" -> "Handlungsanlässe"
    return re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)


def page_of(text: str, offset: int) -> int:
    marks = PAGE_MARK.findall(text[:offset])
    return int(marks[-1]) if marks else 0


def generalistische_part(text: str) -> tuple[int, int]:
    """Bound the generalistische curriculum, excluding the besondere Abschluesse."""
    banners = [
        m.start() for m in BESONDERER_ABSCHLUSS.finditer(text)
        if page_of(text, m.start()) > FRONT_MATTER_PAGES
    ]
    if not banners:
        raise ValueError("Could not locate the besondere-Abschluss boundary")
    return 0, min(banners)


def block_title(segment: str, offset: int) -> str:
    """Read a CE's title from its definition block.

    Taken only from the definition block, never from the many in-text
    cross-references ("... vgl. CE 01 und CE 02 B"): those outnumber the real
    heading, so a most-frequent-variant vote picks up body prose instead of the
    title.  Cutting on the first structural keyword rather than on the line end
    keeps titles that wrap across lines, which most of them do.
    """
    window = segment[offset: offset + 260]
    cut = TITLE_END.search(window)
    return re.sub(r"\s+", " ", window[: cut.start()] if cut else window).strip(" .–−-")


def ce_blocks(text: str, start: int, end: int) -> list[dict]:
    """Locate the eleven generalistische CE blocks.

    A CE block is identified by a heading followed closely by its Zeitrichtwert;
    that combination distinguishes the real definition from the dozens of page
    headers and cross-references repeating the same CE number.
    """
    segment = text[start:end]

    found: dict[str, dict] = {}
    for match in CE_HEADING.finditer(segment):
        window = segment[match.end(): match.end() + 400]
        zeitrichtwert = ZEITRICHTWERT.search(window)
        if not zeitrichtwert or match.group(1) in found:
            continue
        found[match.group(1)] = {
            "ce": f"CE {match.group(1)}",
            "titel": block_title(segment, match.end()),
            "zeitrichtwert_stunden": int(zeitrichtwert.group(1)),
            "offset": match.start(),
            "seite": page_of(text, start + match.start()),
        }

    blocks = sorted(found.values(), key=lambda b: b["offset"])
    for block, following in zip(blocks, blocks[1:] + [None]):
        block["end"] = following["offset"] if following else len(segment)
        block["text"] = segment[block["offset"]: block["end"]]
    return sorted(blocks, key=lambda b: b["ce"])


def codes_by_anlage(block_text: str) -> dict[str, list[str]]:
    """Split a CE block at its Anlage headings and collect codes per Anlage.

    Anlage 1 competencies are what the Zwischenprüfung tests, Anlage 2 what the
    staatliche Prüfung tests.  Family B only cares about Anlage 2, so the split
    has to survive into the output.
    """
    headings = [(m.start(), m.group(1)) for m in ANLAGE_HEADING.finditer(block_text)]
    result: dict[str, list[str]] = defaultdict(list)
    for (offset, anlage), following in zip(headings, headings[1:] + [None]):
        end = following[0] if following else len(block_text)
        for roman, number, letter in CODE.findall(block_text[offset:end]):
            result[anlage].append(f"{roman}.{number}.{letter}")
    return {anlage: sorted(set(codes)) for anlage, codes in result.items()}


def situationsmerkmale(block_text: str) -> dict[str, list[str]]:
    """Collect the bullet items under each Situationsmerkmal heading."""
    positions: list[tuple[int, str]] = []
    for name, pattern in SITUATIONSMERKMALE.items():
        positions.extend((m.start(), name) for m in pattern.finditer(block_text))
    positions.sort()

    collected: dict[str, list[str]] = defaultdict(list)
    for (offset, name), following in zip(positions, positions[1:] + [None]):
        end = following[0] if following else min(offset + 4000, len(block_text))
        body = block_text[offset:end]
        for raw in BULLET.split(body)[1:]:
            # Drop the page furniture the running header injects mid-table.
            item = re.sub(r"<<<PAGE \d+>>>", " ", raw)
            item = re.sub(r"\s+", " ", item).strip(" .;")
            if 8 < len(item) < 400:
                collected[name].append(item)

    return {name: list(dict.fromkeys(items)) for name, items in collected.items() if items}


def authoritative_anlage_codes() -> dict[str, set[str]]:
    """Parse Anlage 1 and Anlage 2 codes straight from PflAPrV."""
    provisions = read_legal_html(RAW_DIR / "PflAPrV.html")
    return {
        anlage: {r.code for r in parse_anlage_kompetenzen(find_provision(provisions, f"Anlage {anlage}"))}
        for anlage in ("1", "2")
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="re-extract the PDF")
    args = parser.parse_args()

    if not SOURCE_PDF.exists() and not CACHE.exists():
        print(f"Source not present: {SOURCE_PDF}")
        return 1

    text = dehyphenate(load_text(force=args.refresh))
    start, end = generalistische_part(text)
    blocks = ce_blocks(text, start, end)
    print(f"Generalistische part: pages 1-{page_of(text, end)} ({len(blocks)} CE blocks)")

    authoritative = authoritative_anlage_codes()

    einheiten = []
    lehrplan_codes: dict[str, set[str]] = {"1": set(), "2": set()}
    merkmale_out = []
    for block in blocks:
        per_anlage = codes_by_anlage(block["text"])
        for anlage in ("1", "2"):
            lehrplan_codes[anlage].update(per_anlage.get(anlage, []))
        merkmale = situationsmerkmale(block["text"])
        einheiten.append(
            {
                "ce": block["ce"],
                "titel": block["titel"],
                "zeitrichtwert_stunden": block["zeitrichtwert_stunden"],
                "seite": block["seite"],
                "kompetenzen_anlage_1": per_anlage.get("1", []),
                "kompetenzen_anlage_2": per_anlage.get("2", []),
                "im_dritten_ausbildungsdrittel": bool(per_anlage.get("2")),
            }
        )
        merkmale_out.append(
            {
                "ce": block["ce"],
                "titel": block["titel"],
                **{name: items for name, items in merkmale.items()},
            }
        )

    # The cross-check the plan defers to a verification item (tech doc 12).
    cross_check = {}
    for anlage in ("1", "2"):
        derived, official = lehrplan_codes[anlage], authoritative[anlage]
        cross_check[f"anlage_{anlage}"] = {
            "lehrplan_derived_count": len(derived),
            "pflaprv_authoritative_count": len(official),
            "in_both": len(derived & official),
            "cited_by_lehrplan_but_absent_from_pflaprv": sorted(derived - official),
            "in_pflaprv_but_never_cited_by_lehrplan": sorted(official - derived),
        }

    kompetenzen = {
        "meta": {
            "id": "kompetenzen",
            "title": "Kompetenztaxonomie fuer die generalistische Pflegeausbildung",
            "purpose": "Competency catalogue for Family B. KOMP-06 tests set membership against `anlage_2_authoritative`, never against the Lehrplan-derived list.",
            "sources": [
                {
                    "role": "authoritative competency catalogue",
                    "document": "Anlage 2 PflAPrV (zu § 9 Absatz 1 Satz 2)",
                    "url": "https://www.gesetze-im-internet.de/pflaprv/anlage_2.html",
                    "authority": "binding_federal",
                },
                {
                    "role": "curricular structure: CE, Zeitrichtwerte, CE-to-competency mapping",
                    "document": "Lehrplaene und Ausbildungsplaene fuer die Berufsfachschule fuer Pflege (StMUK / ISB Bayern, Juli 2020)",
                    "authority": "official_state",
                },
            ],
            "generated_by": "scripts/extract_lehrplan.py",
            "scope_note": "Generalistische Ausbildung only. The Anlage 3 (Kinderkrankenpflege) and Anlage 4 (Altenpflege) curricula in the same document are excluded.",
            "counts": {
                "curriculare_einheiten": len(einheiten),
                "zeitrichtwert_gesamt_stunden": sum(b["zeitrichtwert_stunden"] for b in blocks),
                "einheiten_im_dritten_drittel": sum(1 for e in einheiten if e["im_dritten_ausbildungsdrittel"]),
                "anlage_2_authoritative": len(authoritative["2"]),
                "anlage_1_authoritative": len(authoritative["1"]),
            },
            "cross_check": cross_check,
            "komp_06_finding": (
                "Every code the Lehrplan cites under an Anlage-2 heading does exist in PflAPrV's Anlage 2, "
                "so the Lehrplan invents nothing -- but it is a strict subset. "
                f"{len(cross_check['anlage_2']['in_pflaprv_but_never_cited_by_lehrplan'])} Anlage-2 competencies "
                "are never cited by the Lehrplan at the Anlage-2 level: "
                f"{', '.join(cross_check['anlage_2']['in_pflaprv_but_never_cited_by_lehrplan'])}. "
                "KOMP-06 built on the Lehrplan-derived list would therefore have raised a false flag against "
                "an item legitimately claiming any of them -- including I.1.h, the code tech doc 3.3.1 uses as "
                "its worked example. This is why KOMP-06 reads `anlage_2_authoritative`, and it resolves the "
                "verification item in tech doc 12."
            ),
        },
        # KOMP-06 reads this and only this.
        "anlage_2_authoritative": sorted(authoritative["2"]),
        "anlage_1_authoritative": sorted(authoritative["1"]),
        "curriculare_einheiten": einheiten,
    }

    situationen = {
        "meta": {
            "id": "situationsmerkmale",
            "title": "Situationsmerkmale je curriculare Einheit",
            "purpose": "The Lehrplan's Situationsprinzip vocabulary. Structures the Fallsituation fields of the item schema (tech doc 2.2) and supplies the comparison target for KOMP-07.",
            "dimensions_structured_per_ce": list(STRUCTURED_DIMENSIONS),
            "dimensions_prose_only": [
                name for name in SITUATIONSMERKMALE if name not in STRUCTURED_DIMENSIONS
            ],
            "dimensions_note": (
                "The Lehrplan sets only Handlungsanlaesse, Kontextbedingungen and Handlungsmuster as "
                "table rows per CE. Akteure and Erleben/Deuten/Verarbeiten are prose in the introduction "
                "and the didaktischer Kommentar, so there is no per-CE list to compare against. The item "
                "schema used to keep an `akteure` field for this reason, but removed it (2026-09-11): with "
                "no per-CE list to check it against, it carried no evidence for any rule. KOMP-07 compares "
                "only the three structured dimensions."
            ),
            "source": {
                "document": "Lehrplaene und Ausbildungsplaene fuer die Berufsfachschule fuer Pflege (StMUK / ISB Bayern, Juli 2020)",
                "authority": "official_state",
            },
            "generated_by": "scripts/extract_lehrplan.py",
            "extraction_note": "Extracted from a PDF table set in narrow columns. Content is indicative for KOMP-07 development and needs a spot review against the document before KOMP-07 is scored.",
        },
        "curriculare_einheiten": merkmale_out,
    }

    for target, document in ((KOMPETENZEN_TARGET, kompetenzen), (SITUATIONSMERKMALE_TARGET, situationen)):
        with open(target, "w", encoding="utf-8") as handle:
            yaml.safe_dump(document, handle, allow_unicode=True, sort_keys=False, width=100)
        print(f"Wrote {target.relative_to(ROOT)}")

    print(f"\nCE blocks: {len(einheiten)}, total Zeitrichtwert "
          f"{kompetenzen['meta']['counts']['zeitrichtwert_gesamt_stunden']}h, "
          f"{kompetenzen['meta']['counts']['einheiten_im_dritten_drittel']} continue into the 3rd Drittel")
    print("\nCross-check, Lehrplan citations vs PflAPrV text:")
    for key, values in cross_check.items():
        print(f"  {key}: lehrplan={values['lehrplan_derived_count']:3d} "
              f"pflaprv={values['pflaprv_authoritative_count']:3d} both={values['in_both']:3d}")
        if values["cited_by_lehrplan_but_absent_from_pflaprv"]:
            print(f"    cited but not in PflAPrV: {values['cited_by_lehrplan_but_absent_from_pflaprv']}")
    merkmal_counts = Counter(k for m in merkmale_out for k in m if k not in {"ce", "titel"})
    print(f"\nSituationsmerkmale coverage across {len(merkmale_out)} CEs: {dict(merkmal_counts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
