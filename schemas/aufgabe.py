"""The input artifact: one Aufsichtsarbeit.

Two design rules from the plan drive everything here.

**Every field is optional** (tech doc 1.5.1, 2.2).  The primary user is the
author, who runs the tool on a draft with three of five Teilaufgaben written and
no Erwartungshorizont yet.  A schema that rejects incomplete input locks out the
person the tool is for.  Completeness is therefore *computed* and drives which
checks can run, rather than being enforced at parse time.

**IDs identify a structural position, not text.**  ``ta.2`` means "the second
Teilaufgabe", whatever it currently says.  The author rewrites the text, the ID
still points at the same element, so two runs can be compared to see whether a
flag was resolved or persisted.  Character offsets or text hashes would be
invalidated by any edit and cannot do that.

Known limitation, accepted for this PoC: ordinal IDs shift if the author
reorders or inserts a Teilaufgabe, since the old ``ta.2`` becomes ``ta.3``.  Each
run is one-shot against a submitted draft, so this does not bite here.  In the
Word add-in the fix is natural — a content control carries its own tag through
edits, so the tag becomes the opaque identifier and the number is display only
(tech doc 2.2, 4.4).
"""
from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

# Abbreviations that end in a period without ending a sentence.  German nursing
# case prose is dense with these, and every one of them would otherwise create a
# spurious sentence anchor -- which shows up directly in the anchor-accuracy
# metric (tech doc 7.3).
ABKUERZUNGEN = {
    "z", "b", "ca", "bzw", "ggf", "evtl", "inkl", "usw", "etc", "d", "h", "u", "a",
    "vgl", "abs", "nr", "ff", "dr", "med", "sog", "max", "min", "mind", "bspw",
    "jhd", "geb", "verst", "pflegefachfr", "ggü", "o", "s",
}

# A sentence ends at ., ! or ? followed by whitespace and a capital letter.
SATZENDE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ])")


class Anforderungsniveau(str, Enum):
    """Anforderungsbereiche of the operator list: I reproduction, II transfer,
    III judgement.  Stored as *declared by the author*; the tool derives its own
    and flags divergence (tech doc 2.2)."""

    I = "I"
    II = "II"
    III = "III"


class Versorgungsbereich(str, Enum):
    stationaer_akut = "stationaer_akut"
    stationaer_langzeit = "stationaer_langzeit"
    ambulant = "ambulant"
    paediatrisch = "paediatrisch"
    psychiatrisch = "psychiatrisch"
    rehabilitativ = "rehabilitativ"


class Altersgruppe(str, Enum):
    kind = "kind"
    jugendlicher = "jugendlicher"
    erwachsener = "erwachsener"
    alter_mensch = "alter_mensch"


class Base(BaseModel):
    # Unknown keys are kept rather than rejected: a permissive parser (week 2)
    # will produce fields this schema has not caught up with, and losing them
    # silently is worse than carrying them.
    model_config = ConfigDict(extra="allow", use_enum_values=True)


class Metadaten(Base):
    pruefungsbereich: str | None = None
    ausbildungsabschluss: str | None = Field(
        default=None, description="e.g. Pflegefachfrau/Pflegefachmann"
    )
    bearbeitungszeit_minuten: int | None = Field(
        default=None, description="PflAPrV § 14 expects 120 minutes per Aufsichtsarbeit"
    )
    autor: str | None = None
    version: str | None = None
    datum: str | None = None


class Situationsmerkmale(Base):
    """The Fallsituation described in the Lehrplan's own vocabulary.

    Structuring this by Situationsmerkmale rather than by invented setting and
    Altersgruppe fields means the schema mirrors a binding document, and the
    fields are ones a Prüfungsausschuss member already thinks in (tech doc 2.1).

    ``akteure`` is kept because authors do describe who appears in a case, but
    note the Lehrplan supplies no per-CE Akteure list to compare against, so
    KOMP-07 compares only the three structured dimensions
    (see rules/situationsmerkmale.yaml).
    """

    handlungsanlaesse: list[str] = Field(default_factory=list)
    kontextbedingungen: list[str] = Field(default_factory=list)
    handlungsmuster: list[str] = Field(default_factory=list)
    akteure: list[str] = Field(default_factory=list)


class Fallsituation(Base):
    text: str | None = None
    situationsmerkmale: Situationsmerkmale = Field(default_factory=Situationsmerkmale)
    versorgungsbereich: Versorgungsbereich | None = None
    altersgruppe: Altersgruppe | None = None
    pflegebeduerftigkeit: str | None = None

    def saetze(self) -> list[str]:
        """Split the Fallsituation into sentences for anchoring.

        Splitting has to be *stable and reproducible* rather than linguistically
        perfect, but it does have to survive the two constructions that saturate
        this domain: abbreviated surnames ("Frau K. ist 82 Jahre alt") and
        "z. B.".  A plain split on ". " puts a false sentence boundary inside
        both, and every false boundary shifts the anchors after it.
        """
        if not self.text:
            return []
        text = re.sub(r"\s+", " ", self.text.replace("\n", " ")).strip()
        sentences: list[str] = []
        current = ""
        for fragment in SATZENDE.split(text):
            candidate = f"{current} {fragment}".strip() if current else fragment
            # Look at the token that carried the period: a lone capital is an
            # initial ("K."), and a known abbreviation is not a sentence end.
            tail = re.search(r"([A-Za-zÄÖÜäöü]+)\.$", current or fragment)
            token = tail.group(1).casefold() if tail else ""
            ends_sentence = not (
                (len(token) == 1 and (current or fragment)[-2:-1].isupper())
                or token in ABKUERZUNGEN
            )
            if current and ends_sentence:
                sentences.append(current)
                current = fragment
            else:
                current = candidate
        if current:
            sentences.append(current)
        return [s for s in sentences if s.strip()]

    def satz_ids(self) -> list[str]:
        """Sentence-level anchors, so a flag can point at one sentence."""
        return [f"fs.satz.{i + 1}" for i in range(len(self.saetze()))]


class Erwartungspunkt(Base):
    text: str | None = None
    punkte: float | None = None


class Erwartungshorizont(Base):
    erwartungspunkte: list[Erwartungspunkt] = Field(default_factory=list)
    freitext: str | None = None

    @property
    def punkte_summe(self) -> float | None:
        werte = [p.punkte for p in self.erwartungspunkte if p.punkte is not None]
        return sum(werte) if werte else None


class Teilaufgabe(Base):
    text: str | None = Field(default=None, description="contains the Operator")
    anforderungsniveau: Anforderungsniveau | None = Field(
        default=None, description="as declared by the author, not as derived"
    )
    punkte: float | None = None
    kompetenzzuordnung: list[str] = Field(
        default_factory=list, description="Anlage 2 codes as claimed by the author, e.g. I.1.h"
    )
    erwartungshorizont: Erwartungshorizont | None = None


class Aufsichtsarbeit(Base):
    """One written exam item. Every field optional; see the module docstring."""

    aufgabe_id: str | None = None
    metadaten: Metadaten = Field(default_factory=Metadaten)
    ce_bezug: list[str] = Field(
        default_factory=list, description="curriculare Einheiten drawn on, e.g. ['CE 02', 'CE 07']"
    )
    fallsituation: Fallsituation | None = None
    teilaufgaben: list[Teilaufgabe] = Field(default_factory=list)

    # Some rules apply across the set of three Aufsichtsarbeiten rather than
    # within one: PflAPrV expects the three Fallsituationen to vary overall
    # (KOMP-05).  Cross-item context is therefore a first-class field.
    geschwister_aufgaben: list[str] = Field(
        default_factory=list, description="aufgabe_ids of sibling Aufsichtsarbeiten in the same exam"
    )

    # ---- stable structural IDs -------------------------------------------------

    def teilaufgabe_id(self, index: int) -> str:
        """1-based, matching how a Prüfungsausschuss member numbers them."""
        return f"ta.{index + 1}"

    def erwartungspunkt_id(self, teilaufgabe_index: int, punkt_index: int) -> str:
        return f"ta.{teilaufgabe_index + 1}.eh.{punkt_index + 1}"

    def anchors(self) -> list[str]:
        """Every addressable position in this artifact, in document order."""
        anchors: list[str] = ["aufgabe"]
        if self.fallsituation:
            anchors.append("fs")
            anchors.extend(self.fallsituation.satz_ids())
        for ti, teilaufgabe in enumerate(self.teilaufgaben):
            anchors.append(self.teilaufgabe_id(ti))
            if teilaufgabe.erwartungshorizont:
                anchors.extend(
                    self.erwartungspunkt_id(ti, pi)
                    for pi in range(len(teilaufgabe.erwartungshorizont.erwartungspunkte))
                )
        return anchors

    def resolve(self, anchor: str) -> object | None:
        """Resolve a structural ID back to the element it names.

        The report renderer and the docx writer both need this to place a flag,
        and neither should re-implement the ID grammar.
        """
        if anchor == "aufgabe":
            return self
        if anchor == "fs":
            return self.fallsituation
        parts = anchor.split(".")
        if parts[0] == "fs" and len(parts) == 3 and parts[1] == "satz":
            return self.fallsituation
        if parts[0] != "ta" or len(parts) < 2 or not parts[1].isdigit():
            return None
        index = int(parts[1]) - 1
        if not 0 <= index < len(self.teilaufgaben):
            return None
        teilaufgabe = self.teilaufgaben[index]
        if len(parts) == 2:
            return teilaufgabe
        if len(parts) == 4 and parts[2] == "eh" and parts[3].isdigit():
            horizont = teilaufgabe.erwartungshorizont
            if horizont is None:
                return None
            punkt_index = int(parts[3]) - 1
            if 0 <= punkt_index < len(horizont.erwartungspunkte):
                return horizont.erwartungspunkte[punkt_index]
        return None

    # ---- completeness ----------------------------------------------------------

    @property
    def punkte_summe(self) -> float | None:
        werte = [t.punkte for t in self.teilaufgaben if t.punkte is not None]
        return sum(werte) if werte else None

    def completeness(self) -> dict[str, bool]:
        """What is present, so the precondition gate can decide what may run.

        Computed rather than required: this is the mechanism that lets the tool
        be useful on a draft instead of refusing it (tech doc 1.5.1).
        """
        return {
            "fallsituation.text": bool(self.fallsituation and self.fallsituation.text),
            "fallsituation.situationsmerkmale": bool(
                self.fallsituation
                and any(
                    getattr(self.fallsituation.situationsmerkmale, dimension)
                    for dimension in ("handlungsanlaesse", "kontextbedingungen", "handlungsmuster")
                )
            ),
            "ce_bezug": bool(self.ce_bezug),
            "teilaufgaben": bool(self.teilaufgaben),
            "teilaufgabe.text": any(t.text for t in self.teilaufgaben),
            "teilaufgabe.anforderungsniveau": any(
                t.anforderungsniveau for t in self.teilaufgaben
            ),
            "teilaufgabe.punkte": any(t.punkte is not None for t in self.teilaufgaben),
            "teilaufgabe.kompetenzzuordnung": any(t.kompetenzzuordnung for t in self.teilaufgaben),
            "teilaufgabe.erwartungshorizont": any(
                t.erwartungshorizont and t.erwartungshorizont.erwartungspunkte
                for t in self.teilaufgaben
            ),
            "metadaten.bearbeitungszeit_minuten": self.metadaten.bearbeitungszeit_minuten
            is not None,
            "geschwister_aufgaben": bool(self.geschwister_aufgaben),
        }
