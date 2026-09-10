"""Structure-aware ingestion of official German legal HTML.

The parsing of ``div.jnnorm[title="Einzelnorm"]`` is carried over unchanged from
phase 1, where it was correct.  What changed is the *interface*: provisions are
returned as structured records rather than concatenated into one text blob.

That is the fix for the blocking defect in the phase-1 index (repo review 4.1),
where every Anlage 1 and Anlage 2 competency chunk was cited as "§ 62".  The
cause was not the section regex by itself but the flattening: once the
Einzelnorm headings are folded into a single string, the only way back to a
locator is to guess at it, and ``^§\\s*(\\d+)`` cannot recognise an Anlage
heading.  Anlagen therefore inherited the last § that happened to precede them.

Keeping each provision's own heading attached removes the guess entirely.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from bs4 import BeautifulSoup

# The official pages are latin-1, not UTF-8.  Reading them as UTF-8 fails on
# every umlaut in the corpus.
LEGAL_ENCODING = "iso-8859-1"

LEGAL_SOURCE_URLS = {
    "pflbg": "https://www.gesetze-im-internet.de/pflbg/BJNR258110017.html",
    "pflaprv": "https://www.gesetze-im-internet.de/pflaprv/BJNR157200018.html",
}

# "§ 9", "§ 49d", "§ 45a"
SECTION_HEADING = re.compile(r"^§\s*(\d+[a-z]?)\b")
# "Anlage 2 (zu § 9 Absatz 1 Satz 2) Kompetenzen für ..." and "Anlage 12a (zu § 49d)"
ANLAGE_HEADING = re.compile(r"^Anlage\s+(\d+[a-z]?)\b")
# "(Fundstelle: BGBl. I 2018, 1596 - 1600; ...)" — the official page reference
# that distinguishes one Anlage from another in the printed Bundesgesetzblatt.
FUNDSTELLE = re.compile(r"Fundstelle:\s*([^;)]+)")


def clean_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


@dataclass(frozen=True)
class Provision:
    """One ``Einzelnorm`` — a § or an Anlage — with its own heading preserved.

    ``unit_type`` is what Family B needs: it makes "this text is part of Anlage 2"
    a fact carried by the data rather than something a downstream regex has to
    re-infer from flattened text.
    """

    heading: str
    text: str
    unit_type: str  # "paragraph" | "anlage" | "other"
    unit_number: str | None  # "9", "49d", "2", "12a"
    locator: str  # citable: "§ 9" or "Anlage 2 (zu § 9 Absatz 1 Satz 2)"
    fundstelle: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def is_anlage(self) -> bool:
        return self.unit_type == "anlage"


def _classify_heading(heading: str) -> tuple[str, str | None, str]:
    """Derive ``(unit_type, unit_number, locator)`` from an Einzelnorm heading.

    The locator is what ends up in a flag's evidence, so for an Anlage it keeps
    the "(zu § 9 Absatz 1 Satz 2)" qualifier: that is how the Anlage is cited in
    practice, and it is what distinguishes Anlage 2 (staatliche Prüfung) from
    Anlage 1 (Zwischenprüfung) to a reader.
    """
    anlage = ANLAGE_HEADING.match(heading)
    if anlage:
        # Keep "Anlage 2 (zu § 9 Absatz 1 Satz 2)" but drop the long descriptive
        # tail that follows it, which is a title rather than part of the citation.
        qualified = re.match(r"^(Anlage\s+\d+[a-z]?(?:\s*\([^)]*\))?)", heading)
        locator = qualified.group(1).strip() if qualified else f"Anlage {anlage.group(1)}"
        return "anlage", anlage.group(1), locator

    section = SECTION_HEADING.match(heading)
    if section:
        return "paragraph", section.group(1), f"§ {section.group(1)}"

    return "other", None, heading[:80]


def read_legal_html(path: Path) -> list[Provision]:
    """Extract individual provisions from gesetze-im-internet HTML.

    Selecting ``div.jnnorm[title="Einzelnorm"]`` avoids table-of-contents
    entries, navigation, print headers, and the bare URLs that make PDF
    extraction of these documents noisy.
    """
    soup = BeautifulSoup(path.read_text(encoding=LEGAL_ENCODING), "lxml")
    provisions: list[Provision] = []
    for norm in soup.select('div.jnnorm[title="Einzelnorm"]'):
        header = norm.select_one(".jnheader h3")
        if header is None:
            continue
        heading = clean_text(header.get_text(" "))
        if not heading or heading.casefold().startswith("inhaltsübersicht"):
            continue
        body = norm.select_one(".jnhtml")
        if body is None:
            continue
        text = clean_text(body.get_text("\n"))
        if not text:
            continue
        unit_type, unit_number, locator = _classify_heading(heading)
        fundstelle = FUNDSTELLE.search(text)
        provisions.append(
            Provision(
                heading=heading,
                text=text,
                unit_type=unit_type,
                unit_number=unit_number,
                locator=locator,
                fundstelle=clean_text(fundstelle.group(1)) if fundstelle else None,
            )
        )
    if not provisions:
        raise ValueError(f"No individual provisions found in official legal HTML: {path}")
    return provisions


def legal_source_metadata(path: Path) -> dict[str, object]:
    """Read provenance that applies to the whole consolidated document."""
    source_key = path.stem.casefold()
    metadata: dict[str, object] = {
        "authority": "binding_federal",
        "source_url": LEGAL_SOURCE_URLS.get(source_key),
        "retrieved_at": datetime.fromtimestamp(path.stat().st_mtime, UTC).date().isoformat(),
        "legal_status": None,
    }
    if path.suffix.lower() not in {".html", ".htm"}:
        return metadata

    soup = BeautifulSoup(path.read_text(encoding=LEGAL_ENCODING), "lxml")
    title = soup.select_one('div.jnnorm[title="Rahmen"] .jnheader h1')
    if title:
        metadata["official_title"] = clean_text(title.get_text(" "))
    status = soup.select_one("table.standangaben")
    if status:
        # "Stand: ..." carries the consolidation date, which is the closest thing
        # the official page gives to a version for this document.
        metadata["legal_status"] = clean_text(status.get_text(" "))
    return metadata


def find_provision(provisions: list[Provision], locator_prefix: str) -> Provision | None:
    """Look up one provision by the start of its locator, e.g. "Anlage 2"."""
    for provision in provisions:
        if provision.locator.startswith(locator_prefix):
            return provision
    return None
