"""The input artifact: one Aufsichtsarbeit.

**One Aufsichtsarbeit contains exactly two Aufgabe blocks** ("Aufgabe 1" /
"Aufgabe 2" in the Prüfungsausschuss's own vocabulary), each independently
themed: its own Fallsituation, its own Teilaufgaben.  Both blocks share one
Bearbeitungszeit, one Punktzahl budget, and one Prüfungsbereich correspondence,
all declared at the Aufsichtsarbeit level (PflAPrV § 14 (1)-(3)).

This was not in the original schema — week 1 modelled one Fallsituation per
Aufsichtsarbeit, which is wrong: a candidate's 120-minute paper for one
Prüfungsbereich is composed of two independently-themed cases (e.g. one
stationäre Langzeitpflege, one stationäre psychiatrische Pflege), not one.  The
correction is structural, not cosmetic, so every rule that used to pair "the
Fallsituation" with "the Teilaufgaben" of a whole Aufsichtsarbeit has to be
re-scoped to one Aufgabe block, and the anchor grammar gained a level
(``ag.1.ta.2`` instead of ``ta.2``).

**Schema change, 2026-09-11:** the curriculare-Einheit claim (``ce_bezug``) and
the Situationsmerkmale that get checked against it moved down from the Aufgabe
block to the individual Teilaufgabe (``Teilaufgabe.situationsmerkmale``, which
now also carries ``curriculare_einheit``, ``wissensgrundlagen`` and
``quellenangabe``), since different Teilaufgaben within one Fallsituation can
target different CEs. ``Teilaufgabe.kompetenzzuordnung`` (the claimed Anlage-2
codes) was removed with no replacement, which retires KOMP-01/02/03/03B/06
(``blocked_on`` in rules/kompetenz.yaml) until competency evidence has a new
home in this schema. A new ``Teilaufgabe.kompetenzanforderung`` field
(Wissen / Analyse-Synthese / Reflexion-Beurteilung) was added.
``Fallsituation.titel`` (then typed ``Versorgungsbereich | None``) and
``.pflegebeduerftigkeit``, and ``Situationsmerkmale.akteure``, were added in the
same change and then removed again shortly after (still 2026-09-11): none were
read by any check, and ``titel`` duplicated ``versorgungsbereich`` with no
distinct purpose. ``titel`` was reintroduced immediately after as free text
(``str | None``) -- a short author-chosen label for the case, independent of
the Prüfungsbereich/Versorgungsbereich vocabulary, so the two fields now serve
different purposes and both stay.

**Schema change, 2026-09-11 (later same day):** ``Teilaufgabe.kompetenzzuordnung_abgeleitet``
gives KOMP-01/03/03B/06 evidence to run against again -- an LLM-derived list of
Anlage-2 Einzelkompetenzen (e.g. ``["I.1.h"]``), populated at check time by
KOMP-01 rather than declared by the author. Deliberately not named
``kompetenzzuordnung``: that name meant an author claim, and conflating the two
is exactly what KOMP-02 existed to prevent. KOMP-02 itself has no "claimed" side
left to compare a derived value against and is retired, not redesigned. See
rules/kompetenz.yaml's Family B meta block for the full migration note.

Three design rules drive everything here.

**Every field is optional** (tech doc 1.5.1, 2.2).  The primary user is the
author, who runs the tool on a draft with three of five Teilaufgaben written and
no Erwartungshorizont yet — and, now, possibly with only Aufgabe 1 written and
Aufgabe 2 not yet started.  A schema that rejects incomplete input locks out the
person the tool is for.  Completeness is therefore *computed* and drives which
checks can run, rather than being enforced at parse time.  This is also why
``aufgaben`` is not pinned to length 2 at the pydantic level even though the
domain rule is "always exactly two": rejecting a draft with only one Aufgabe
written would violate the same principle the whole schema is built on.
``completeness()`` reports the gap instead.

**IDs identify a structural position, not text.**  ``ag.1.ta.2`` means "the
second Teilaufgabe of the first Aufgabe block", whatever it currently says.
The author rewrites the text, the ID still points at the same element, so two
runs can be compared to see whether a flag was resolved or persisted. Character
offsets or text hashes would be invalidated by any edit and cannot do that.

Known limitation, accepted for this PoC: ordinal IDs shift if the author
reorders or inserts a Teilaufgabe (or an Aufgabe block), since the old ``ag.1``
becomes ``ag.2``.  Each run is one-shot against a submitted draft, so this does
not bite here.  In the Word add-in the fix is natural — a content control
carries its own tag through edits, so the tag becomes the opaque identifier and
the number is display only (tech doc 2.2, 4.4).
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


class Kompetenzanforderung(str, Enum):
    """The cognitive level a Teilaufgabe addresses, in the Prüfungsausschuss's
    own three-way vocabulary rather than the operator list's Anforderungsbereiche
    (schema change 2026-09-11). Distinct field from ``Anforderungsniveau``: both
    are kept, since the restructuring request introduced this one alongside the
    existing one rather than in place of it."""

    wissen = "Wissen"
    analyse_synthese = "Analyse/Synthese"
    reflexion_beurteilung = "Reflexion/Beurteilung"


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
    """The Lehrplan's own vocabulary for describing a case, now recorded per
    Teilaufgabe rather than once per Fallsituation (schema change 2026-09-11):
    a single Aufgabe block's Fallsituation can motivate several Teilaufgaben
    that each target a different curriculare Einheit, so the CE claim and its
    Situationsmerkmale moved down to the granularity where that claim is
    actually made.

    Structuring this by Situationsmerkmale rather than by invented setting and
    Altersgruppe fields means the schema mirrors a binding document, and the
    fields are ones a Prüfungsausschuss member already thinks in (tech doc 2.1).
    Only the three fields below are structured per-CE tables in the Lehrplan
    (see rules/situationsmerkmale.yaml); an ``akteure`` field used to be kept
    here too even though the Lehrplan has no per-CE Akteure list to check it
    against, but it was removed (2026-09-11) for carrying no checkable evidence.

    ``curriculare_einheit`` replaces the old ``Aufgabe.ce_bezug``: the CE claim
    now sits next to the Situationsmerkmale it is checked against instead of
    one level up on the whole Aufgabe block. ``wissensgrundlagen`` and
    ``quellenangabe`` are new: the Lehrplan lists Wissensgrundlagen per CE
    alongside its Situationsmerkmale (see rules/situationsmerkmale.yaml), and
    an author-supplied Quellenangabe lets a claim here be traced back to where
    it came from.
    """

    curriculare_einheit: list[str] = Field(
        default_factory=list, description="Curriculare Einheit (CE) this Teilaufgabe draws on, e.g. ['CE 09']"
    )
    handlungsanlaesse: list[str] = Field(default_factory=list)
    kontextbedingungen: list[str] = Field(default_factory=list)
    handlungsmuster: list[str] = Field(default_factory=list)
    wissensgrundlagen: list[str] = Field(default_factory=list, description="Wissensgrundlagen (WG)")
    quellenangabe: str | None = Field(default=None, description="where this Situationsmerkmale claim is sourced from")


class Fallsituation(Base):
    text: str | None = None
    titel: str | None = Field(
        default=None, description="a short free-text label summarising the case, e.g. 'Frau Ostermann - Mobilität und soziale Teilhabe'"
    )
    versorgungsbereich: Versorgungsbereich | None = None
    altersgruppe: Altersgruppe | None = None

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
    kompetenzanforderung: Kompetenzanforderung | None = Field(
        default=None, description="Wissen / Analyse-Synthese / Reflexion-Beurteilung, as declared by the author"
    )
    punkte: float | None = None
    situationsmerkmale: Situationsmerkmale = Field(default_factory=Situationsmerkmale)
    kompetenzzuordnung_abgeleitet: list[str] = Field(
        default_factory=list,
        description="Anlage 2 Einzelkompetenzen an LLM derived from this Teilaufgabe's text, e.g. ['I.1.h']",
    )
    erwartungshorizont: Erwartungshorizont | None = None


class Aufgabe(Base):
    """One of the two independently-themed case blocks within an
    Aufsichtsarbeit — "Aufgabe 1" / "Aufgabe 2" in the Prüfungsausschuss's own
    vocabulary.  Position in ``Aufsichtsarbeit.aufgaben`` gives the number
    (index 0 = Aufgabe 1), the same convention already used for Teilaufgaben:
    the number is derived from structural position, never stored redundantly.

    Each Aufgabe carries its own Fallsituation and its own Teilaufgaben.
    Bearbeitungszeit, the overall Punktzahl, and the Prüfungsbereich
    correspondence stay at the Aufsichtsarbeit level: those are properties of
    the whole 120-minute paper (PflAPrV § 14 (1)-(3)), not of one block within
    it. The curriculare-Einheit claim that used to live here as ``ce_bezug``
    moved down to ``Teilaufgabe.situationsmerkmale.curriculare_einheit``
    (schema change 2026-09-11): a block's two-plus Teilaufgaben can target
    different CEs even while sharing one Fallsituation.
    """

    fallsituation: Fallsituation | None = None
    teilaufgaben: list[Teilaufgabe] = Field(default_factory=list)


class Aufsichtsarbeit(Base):
    """One written exam item: one 120-minute paper for one Prüfungsbereich,
    composed of exactly two Aufgabe blocks. Every field optional; see the
    module docstring."""

    aufgabe_id: str | None = None
    metadaten: Metadaten = Field(default_factory=Metadaten)
    aufgaben: list[Aufgabe] = Field(
        default_factory=list,
        description="always exactly 2 when complete (Aufgabe 1, Aufgabe 2); "
        "may hold fewer on an in-progress draft",
    )

    # Some rules apply across the set of three Aufsichtsarbeiten rather than
    # within one: PflAPrV expects the three Fallsituationen to vary overall
    # (KOMP-05).  Cross-item context is therefore a first-class field.
    geschwister_aufgaben: list[str] = Field(
        default_factory=list, description="aufgabe_ids of sibling Aufsichtsarbeiten in the same exam"
    )

    # ---- flattening helpers, for rules that operate on the whole paper --------

    def alle_teilaufgaben(self) -> list[Teilaufgabe]:
        """Every Teilaufgabe across both Aufgabe blocks, in document order.

        Used by whole-paper rules (FORM-02's Bearbeitungsumfang, KOMP-04's
        Anforderungsniveau distribution, QUELL-03's Vorbehaltsaufgaben check):
        the Prüfungsbereich correspondence and the 120-minute Bearbeitungszeit
        apply to the whole paper, not to one block, so these rules must see
        across the block boundary rather than stopping at the first Aufgabe.
        KOMP-03/03B used to pool this too, before the schema change of
        2026-09-11 removed the field (``teilaufgabe.kompetenzzuordnung``) their
        coverage check read; both are ``blocked_on`` in rules/kompetenz.yaml
        pending a redesign against the new Kompetenzanforderung/CE model.
        """
        return [t for aufgabe in self.aufgaben for t in aufgabe.teilaufgaben]

    @property
    def punkte_summe(self) -> float | None:
        werte = [t.punkte for t in self.alle_teilaufgaben() if t.punkte is not None]
        return sum(werte) if werte else None

    # ---- stable structural IDs -------------------------------------------------

    def aufgabe_block_id(self, index: int) -> str:
        """1-based, matching "Aufgabe 1" / "Aufgabe 2"."""
        return f"ag.{index + 1}"

    def teilaufgabe_id(self, aufgabe_index: int, teilaufgabe_index: int) -> str:
        """1-based within its Aufgabe block, matching how a Prüfungsausschuss
        member numbers them ("Aufgabe 1, Teilaufgabe 2")."""
        return f"{self.aufgabe_block_id(aufgabe_index)}.ta.{teilaufgabe_index + 1}"

    def erwartungspunkt_id(self, aufgabe_index: int, teilaufgabe_index: int, punkt_index: int) -> str:
        return f"{self.teilaufgabe_id(aufgabe_index, teilaufgabe_index)}.eh.{punkt_index + 1}"

    def anchors(self) -> list[str]:
        """Every addressable position in this artifact, in document order."""
        anchors: list[str] = ["aufgabe"]
        for ai, aufgabe in enumerate(self.aufgaben):
            block_id = self.aufgabe_block_id(ai)
            anchors.append(block_id)
            if aufgabe.fallsituation:
                anchors.append(f"{block_id}.fs")
                anchors.extend(
                    f"{block_id}.{satz_id}" for satz_id in aufgabe.fallsituation.satz_ids()
                )
            for ti, teilaufgabe in enumerate(aufgabe.teilaufgaben):
                anchors.append(self.teilaufgabe_id(ai, ti))
                if teilaufgabe.erwartungshorizont:
                    anchors.extend(
                        self.erwartungspunkt_id(ai, ti, pi)
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
        parts = anchor.split(".")
        if parts[0] != "ag" or len(parts) < 2 or not parts[1].isdigit():
            return None
        aufgabe_index = int(parts[1]) - 1
        if not 0 <= aufgabe_index < len(self.aufgaben):
            return None
        aufgabe = self.aufgaben[aufgabe_index]

        if len(parts) == 2:
            return aufgabe
        if parts[2] == "fs":
            if len(parts) == 3:
                return aufgabe.fallsituation
            if len(parts) == 5 and parts[3] == "satz":
                return aufgabe.fallsituation
            return None
        if parts[2] != "ta" or len(parts) < 4 or not parts[3].isdigit():
            return None
        teilaufgabe_index = int(parts[3]) - 1
        if not 0 <= teilaufgabe_index < len(aufgabe.teilaufgaben):
            return None
        teilaufgabe = aufgabe.teilaufgaben[teilaufgabe_index]
        if len(parts) == 4:
            return teilaufgabe
        if len(parts) == 6 and parts[4] == "eh" and parts[5].isdigit():
            horizont = teilaufgabe.erwartungshorizont
            if horizont is None:
                return None
            punkt_index = int(parts[5]) - 1
            if 0 <= punkt_index < len(horizont.erwartungspunkte):
                return horizont.erwartungspunkte[punkt_index]
        return None

    # ---- completeness ----------------------------------------------------------

    def completeness(self) -> dict[str, bool]:
        """What is present, so the precondition gate can decide what may run.

        Computed rather than required: this is the mechanism that lets the tool
        be useful on a draft instead of refusing it (tech doc 1.5.1). Reported
        per Aufgabe block (``aufgabe_1.*`` / ``aufgabe_2.*``) since that is now
        the granularity most rules run at, plus one whole-paper fact
        (``aufgaben.vollstaendig``) for the domain rule that there must be
        exactly two.
        """
        result: dict[str, bool] = {
            "aufgaben.vollstaendig": len(self.aufgaben) == 2,
            "metadaten.bearbeitungszeit_minuten": self.metadaten.bearbeitungszeit_minuten
            is not None,
            "geschwister_aufgaben": bool(self.geschwister_aufgaben),
        }
        for ai in range(2):
            prefix = f"aufgabe_{ai + 1}"
            aufgabe = self.aufgaben[ai] if ai < len(self.aufgaben) else None
            teilaufgaben = aufgabe.teilaufgaben if aufgabe else []
            result.update(
                {
                    f"{prefix}.fallsituation.text": bool(
                        aufgabe and aufgabe.fallsituation and aufgabe.fallsituation.text
                    ),
                    f"{prefix}.fallsituation.titel": bool(
                        aufgabe and aufgabe.fallsituation and aufgabe.fallsituation.titel
                    ),
                    f"{prefix}.teilaufgaben": bool(teilaufgaben),
                    f"{prefix}.teilaufgabe.text": any(t.text for t in teilaufgaben),
                    f"{prefix}.teilaufgabe.anforderungsniveau": any(
                        t.anforderungsniveau for t in teilaufgaben
                    ),
                    f"{prefix}.teilaufgabe.kompetenzanforderung": any(
                        t.kompetenzanforderung for t in teilaufgaben
                    ),
                    f"{prefix}.teilaufgabe.punkte": any(t.punkte is not None for t in teilaufgaben),
                    f"{prefix}.teilaufgabe.curriculare_einheit": any(
                        t.situationsmerkmale.curriculare_einheit for t in teilaufgaben
                    ),
                    f"{prefix}.teilaufgabe.situationsmerkmale": any(
                        any(
                            getattr(t.situationsmerkmale, dimension)
                            for dimension in ("handlungsanlaesse", "kontextbedingungen", "handlungsmuster")
                        )
                        for t in teilaufgaben
                    ),
                    f"{prefix}.teilaufgabe.kompetenzzuordnung_abgeleitet": any(
                        t.kompetenzzuordnung_abgeleitet for t in teilaufgaben
                    ),
                    f"{prefix}.teilaufgabe.erwartungshorizont": any(
                        t.erwartungshorizont and t.erwartungshorizont.erwartungspunkte
                        for t in teilaufgaben
                    ),
                }
            )
        return result
