"""Parse the PflAPrV Anlage competency tables into coded, citable records.

Anlage 1 (Zwischenprüfung) and Anlage 2 (staatliche Prüfung) are laid out as a
three-level hierarchy in the official HTML:

    I.                          Kompetenzbereich       (roman numeral)
    1.                          Kompetenzschwerpunkt   (arabic)
    Die Absolventinnen und Absolventen
    a)                          Einzelkompetenz        (letter)

which composes into the code form the Bavarian Lehrplan cites — ``I.1.h``,
``V.2.c``.  Parsing it here rather than trusting the Lehrplan's citations is
what makes KOMP-06 a real set-membership test against binding federal law
instead of a test against a curriculum author's reading of it
(tech doc 3.2.1 caveat, 12).

Each record carries the Anlage it came from, so a Family B flag can cite the
competency it actually mapped to.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict

from corpus.ingest.legal import Provision

# Level markers appear on their own line in the extracted text.
BEREICH = re.compile(r"^([IVX]{1,3})\.$")
SCHWERPUNKT = re.compile(r"^(\d{1,2})\.$")
EINZELKOMPETENZ = re.compile(r"^([a-z])\)$")

# Boilerplate that introduces every Einzelkompetenz list; not content.
ABSOLVENTEN = "Die Absolventinnen und Absolventen"


@dataclass(frozen=True)
class Kompetenz:
    code: str  # "I.1.h"
    anlage: str  # "1" | "2"
    anlage_locator: str  # "Anlage 2 (zu § 9 Absatz 1 Satz 2)"
    kompetenzbereich: str  # "I"
    kompetenzbereich_titel: str
    schwerpunkt: str  # "1"
    schwerpunkt_titel: str
    einzelkompetenz: str  # "h"
    text: str
    fundstelle: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def _is_marker(line: str) -> bool:
    return bool(BEREICH.match(line) or SCHWERPUNKT.match(line) or EINZELKOMPETENZ.match(line))


def parse_anlage_kompetenzen(provision: Provision) -> list[Kompetenz]:
    """Extract coded Einzelkompetenzen from one Anlage provision.

    Returns an empty list for Anlagen that are not competency tables (the
    certificate templates in Anlagen 8-14, for instance), so callers can pass
    every Anlage in without pre-filtering.
    """
    if not provision.is_anlage or provision.unit_number is None:
        return []

    lines = [line.strip() for line in provision.text.split("\n")]
    records: list[Kompetenz] = []

    bereich = bereich_titel = schwerpunkt = schwerpunkt_titel = None

    index = 0
    while index < len(lines):
        line = lines[index]
        if not line:
            index += 1
            continue

        # A marker line is followed by its title/content on subsequent lines,
        # up to the next marker.  Collecting until the next marker keeps
        # competencies that wrap across several extracted lines intact.
        def collect(start: int) -> tuple[str, int]:
            parts: list[str] = []
            cursor = start
            while cursor < len(lines):
                candidate = lines[cursor]
                if candidate and _is_marker(candidate):
                    break
                if candidate and candidate != ABSOLVENTEN:
                    parts.append(candidate)
                cursor += 1
            return re.sub(r"\s+", " ", " ".join(parts)).strip(), cursor

        if BEREICH.match(line):
            bereich = BEREICH.match(line).group(1)
            bereich_titel, index = collect(index + 1)
            # A new Kompetenzbereich invalidates the current Schwerpunkt.
            schwerpunkt = schwerpunkt_titel = None
            continue

        if SCHWERPUNKT.match(line) and bereich is not None:
            schwerpunkt = SCHWERPUNKT.match(line).group(1)
            schwerpunkt_titel, index = collect(index + 1)
            continue

        if EINZELKOMPETENZ.match(line) and bereich is not None and schwerpunkt is not None:
            letter = EINZELKOMPETENZ.match(line).group(1)
            text, index = collect(index + 1)
            if text:
                records.append(
                    Kompetenz(
                        code=f"{bereich}.{schwerpunkt}.{letter}",
                        anlage=provision.unit_number,
                        anlage_locator=provision.locator,
                        kompetenzbereich=bereich,
                        kompetenzbereich_titel=bereich_titel or "",
                        schwerpunkt=schwerpunkt,
                        schwerpunkt_titel=schwerpunkt_titel or "",
                        einzelkompetenz=letter,
                        text=text,
                        fundstelle=provision.fundstelle,
                    )
                )
            continue

        index += 1

    return records
