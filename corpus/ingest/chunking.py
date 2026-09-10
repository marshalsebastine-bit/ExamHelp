"""Structure-aware chunking of corpus documents.

Chunk boundaries follow document structure — provision, Anlage, Kompetenz — never
character counts, so that every retrieved passage carries a citation a flag can
quote (tech doc 4.1, "no flag without evidence").

The phase-1 chunker registry pattern is kept; the legal chunker is rewritten to
consume structured provisions instead of regexing a flattened text blob.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from corpus.ingest.kompetenzen import parse_anlage_kompetenzen
from corpus.ingest.legal import Provision

# How binding a source is, which is what the severity model needs.  The phase-1
# `authority` field derived this from `document_type`, conflating *where a
# document came from* with *how binding it is* (repo review 2.3).
AUTHORITY = {
    "binding_federal",  # PflBG, PflAPrV, Anlage 1/2
    "official_state",  # Bay. StMUK Operatorenliste, ISB Lehrplan
    "third_party_advisory",  # PflegePlus Handreichungen, BW Leitfaden
    "professional_normative",  # DNQP Expertenstandard
}

# Anlagen 1-4 are competency tables; 5+ are stundenverteilung tables and
# certificate templates, which have no competency structure to extract.
KOMPETENZ_ANLAGEN = {"1", "2", "3", "4"}


@dataclass(frozen=True)
class SourceDocument:
    document_id: str
    path: Path
    title: str
    document_type: str
    text: str = ""
    provisions: list[Provision] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)


def _paragraph_chunks(text: str, max_chars: int) -> list[str]:
    """Group paragraphs up to a size limit, splitting only over-long paragraphs."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = paragraph
        while len(current) > max_chars:
            split_at = current.rfind(" ", 0, max_chars)
            split_at = split_at if split_at > max_chars // 2 else max_chars
            chunks.append(current[:split_at].strip())
            current = current[split_at:].strip()
    if current:
        chunks.append(current)
    return chunks


class DocumentChunker(ABC):
    @abstractmethod
    def chunk(self, document: SourceDocument, max_chars: int) -> list[dict]: ...

    def _base(self, document: SourceDocument, text: str, locator: str, **extra: object) -> dict:
        chunk = {
            "document_id": document.document_id,
            "document_type": document.document_type,
            "title": document.title,
            "source_file": document.path.name,
            "source_url": None,
            "retrieved_at": None,
            "legal_status": None,
            "authority": None,
            "text": text.strip(),
            "source_locator": locator,
            **document.metadata,
            **extra,
        }
        if chunk["authority"] not in AUTHORITY:
            raise ValueError(
                f"chunk {locator!r} has authority {chunk['authority']!r}, "
                f"which is not one of {sorted(AUTHORITY)}"
            )
        return chunk


class GenericChunker(DocumentChunker):
    """Fallback for document types without a specialised parser."""

    def chunk(self, document: SourceDocument, max_chars: int) -> list[dict]:
        return [
            self._base(document, text, f"Abschnitt {i + 1}", structure={"section": None})
            for i, text in enumerate(_paragraph_chunks(document.text, max_chars))
        ]


class LegalChunker(DocumentChunker):
    """Chunk official legal HTML by provision, keeping each provision's locator.

    Anlagen that are competency tables are additionally emitted one chunk per
    Einzelkompetenz, because that is the granularity Family B tags at: a flag
    saying "this Teilaufgabe maps to I.1.h" has to be able to quote I.1.h and
    nothing else (repo review 4.1).
    """

    def chunk(self, document: SourceDocument, max_chars: int) -> list[dict]:
        chunks: list[dict] = []
        for provision in document.provisions:
            if provision.is_anlage and provision.unit_number in KOMPETENZ_ANLAGEN:
                chunks.extend(self._kompetenz_chunks(document, provision))
                continue
            chunks.extend(self._provision_chunks(document, provision, max_chars))
        return chunks

    def _kompetenz_chunks(self, document: SourceDocument, provision: Provision) -> list[dict]:
        records = parse_anlage_kompetenzen(provision)
        if not records:
            # Structure unexpectedly absent: fall back rather than silently
            # dropping an Anlage from the corpus.
            return self._provision_chunks(document, provision, max_chars=1800)
        return [
            self._base(
                document,
                record.text,
                f"{provision.locator}, Kompetenz {record.code}",
                content_type="kompetenz",
                kompetenz_code=record.code,
                anlage=record.anlage,
                kompetenzbereich=record.kompetenzbereich,
                kompetenzbereich_titel=record.kompetenzbereich_titel,
                schwerpunkt=record.schwerpunkt,
                schwerpunkt_titel=record.schwerpunkt_titel,
                fundstelle=record.fundstelle,
                structure={
                    "unit_type": "anlage",
                    "unit": provision.unit_number,
                    "section": provision.locator,
                    "kompetenz_code": record.code,
                },
            )
            for record in records
        ]

    def _provision_chunks(
        self, document: SourceDocument, provision: Provision, max_chars: int
    ) -> list[dict]:
        chunks: list[dict] = []
        for text in _paragraph_chunks(provision.text, max_chars):
            absatz = re.search(r"\((\d+)\)", text)
            locator = provision.locator
            if provision.unit_type == "paragraph" and absatz:
                locator = f"{locator} Abs. {absatz.group(1)}"
            chunks.append(
                self._base(
                    document,
                    text,
                    locator,
                    content_type="norm" if provision.unit_type == "paragraph" else "anlage_text",
                    fundstelle=provision.fundstelle,
                    structure={
                        "unit_type": provision.unit_type,
                        "unit": provision.unit_number,
                        "section": provision.locator,
                        "paragraph": absatz.group(1) if absatz and provision.unit_type == "paragraph" else None,
                    },
                )
            )
        return chunks


CHUNKER_REGISTRY: dict[str, DocumentChunker] = {
    "legal": LegalChunker(),
    "generic": GenericChunker(),
}


def classify_source(path: Path) -> str:
    if path.name.lower().startswith(("pflbg", "pflaprv")):
        return "legal"
    return "generic"


def chunk_document(document: SourceDocument, max_chars: int = 1800) -> list[dict]:
    chunks = CHUNKER_REGISTRY[document.document_type].chunk(document, max_chars)
    for index, chunk in enumerate(chunks):
        chunk["chunk_index"] = index
        chunk["chunk_id"] = f"{document.document_id}_{index:05d}"
    return chunks
