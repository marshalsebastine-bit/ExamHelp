"""Structure-aware, extensible source chunking.

The RAG core consumes the common chunk fields produced here.  Document-specific
chunkers add their own fields without forcing legal-document structure on other
source types.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class SourceDocument:
    document_id: str
    path: Path
    title: str
    text: str
    document_type: str


def _compact(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _paragraph_chunks(text: str, max_chars: int = 1800) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            # Keep an unusually long paragraph retrievable instead of discarding it.
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
    def chunk(self, document: SourceDocument) -> list[dict]: ...

    def _base(self, document: SourceDocument, text: str, locator: str, **metadata: object) -> dict:
        return {
            "document_id": document.document_id,
            "document_type": document.document_type,
            "title": document.title,
            "source_file": document.path.name,
            "text": text.strip(),
            "source_locator": locator,
            "authority": "internal_guidance" if document.document_type.startswith("handreichung") else "official_source",
            "effective_from": None,
            "effective_to": None,
            **metadata,
        }


class GenericChunker(DocumentChunker):
    """Safe fallback for future types until a specialised parser is introduced."""

    def chunk(self, document: SourceDocument) -> list[dict]:
        return [
            self._base(document, text, f"Abschnitt {i + 1}", structure={"section": None})
            for i, text in enumerate(_paragraph_chunks(document.text))
        ]


class LegalChunker(GenericChunker):
    """Interim PDF/text chunker; official HTML parsing will replace this later."""

    SECTION = re.compile(r"(?m)^§\s*(\d+[a-z]?)\b[^\n]*")

    def chunk(self, document: SourceDocument) -> list[dict]:
        matches = list(self.SECTION.finditer(document.text))
        if not matches:
            return super().chunk(document)
        chunks: list[dict] = []
        for match, following in zip(matches, matches[1:] + [None]):
            section_text = document.text[match.start(): following.start() if following else len(document.text)].strip()
            section = f"§ {match.group(1)}"
            for text in _paragraph_chunks(section_text):
                paragraph = re.search(r"\((\d+)\)", text)
                chunks.append(self._base(
                    document, text, section if not paragraph else f"{section} Abs. {paragraph.group(1)}",
                    structure={"section": section, "paragraph": paragraph.group(1) if paragraph else None},
                ))
        return chunks


class OperatorHandreichungChunker(DocumentChunker):
    OPERATOR = re.compile(r"(?m)^Operator\s+(.+?)\s*$")

    @staticmethod
    def _field(text: str, start: str, ends: Iterable[str]) -> str | None:
        end_pattern = "|".join(re.escape(end) for end in ends)
        match = re.search(rf"(?ms)^{re.escape(start)}\s*(.*?)(?=^{end_pattern}\s*(?:\n|$)|\Z)", text)
        return _compact(match.group(1)) if match else None

    def chunk(self, document: SourceDocument) -> list[dict]:
        # The first occurrence is the table of contents; records begin after section 3.2.
        start = document.text.find("3.2 Erweiterte Operatorenliste", 1500)
        body = document.text[start:] if start >= 0 else document.text
        records = list(self.OPERATOR.finditer(body))
        chunks: list[dict] = []
        area = None
        for match, following in zip(records, records[1:] + [None]):
            record = body[match.start(): following.start() if following else len(body)].strip()
            before = body[max(0, match.start() - 180):match.start()]
            area_match = re.search(r"Anforderungsbereich\s+([I]{1,3})\s*:", before)
            if area_match:
                area = area_match.group(1)
            operator = _compact(match.group(1))
            def capture(pattern: str) -> str | None:
                found = re.search(pattern, record, re.M | re.S)
                return _compact(found.group(1)) if found else None

            # These labels are an intentional schema in this Handreichung.  Treat the
            # parenthesised example labels separately from the primary task formulation.
            fields = {
                "task_formulation": capture(r"^Aufgabenstellung\s+(.+?)(?=^Erklärung\s)"),
                "explanation": capture(r"^Erklärung\s+(.+?)(?=^Redemittel\s)"),
                "redemittel": capture(r"^Redemittel\s+(.+?)(?=^Aufgabenstellung\s*\n\s*\(Beispiel\))"),
                "example_question": capture(r"^Aufgabenstellung\s*\n\s*\(Beispiel\)\s*(.*?)(?=^Antwort\s*\n\s*\(Beispiel\))"),
                "example_answer": capture(r"^Antwort\s*\n\s*\(Beispiel\)\s*(.*?)\Z"),
            }
            chunks.append(self._base(
                document, record, f"3.2 Erweiterte Operatorenliste: {operator}",
                content_type="operator", operator=operator.lower(), anforderungsbereich=area,
                structure={"chapter": "3.2", "section": "Erweiterte Operatorenliste"}, **fields,
            ))
        return chunks


class SprachsensibelHandreichungChunker(DocumentChunker):
    HEADINGS = [
        ("1", "Einleitung", re.compile(r"(?m)^1\.?(?:\s+)Einleitung\s*$")),
        ("2", "Sprachsensible Leistungserhebung", re.compile(r"(?m)^2\.?(?:\s+)Sprachsensible Leistungserhebung\s*$")),
        ("3", "Strategien für die sprachliche Gestaltung", re.compile(r"(?m)^3\.?(?:\s+)Strategien für die sprachliche Gestaltung\s*$")),
        ("3.1", "Fallsituationen", re.compile(r"(?m)^3\.1\s+Fallsituationen\s*$")),
        ("3.2", "Aufgabenstellungen", re.compile(r"(?m)^3\.2\s+Aufgabenstellungen\s*$")),
        ("4", "Strategien für Auszubildende", re.compile(r"(?m)^4\.?(?:\s+)Strategien für Auszubildende\s*$")),
        ("5", "Fazit", re.compile(r"(?m)^5\.?(?:\s+)Fazit\s*$")),
        ("Anhang 1", "Checkliste", re.compile(r"(?m)^6\.\s+Anhang 1: Checkliste\s*$")),
    ]

    def _sections(self, text: str) -> list[tuple[str, str, str]]:
        found: list[tuple[int, str, str, int]] = []
        for number, name, pattern in self.HEADINGS:
            matches = list(pattern.finditer(text))
            if matches:
                # Contents appears at the beginning; body headings are the final matches.
                match = matches[-1]
                found.append((match.start(), number, name, match.end()))
        found.sort()
        return [(number, name, text[end:found[i + 1][0] if i + 1 < len(found) else len(text)].strip()) for i, (_, number, name, end) in enumerate(found)]

    def chunk(self, document: SourceDocument) -> list[dict]:
        chunks: list[dict] = []
        pair_number = 0
        for chapter, section, text in self._sections(document.text):
            if chapter == "Anhang 1":
                for category, items in re.findall(r"(?ms)(\d+\.\s+(?:Fallsituation|Aufgabenstellung))\s*(.*?)(?=^\d+\.\s+(?:Fallsituation|Aufgabenstellung)|\Z)", text):
                    for item in re.findall(r"□\s*(.*?)(?=\s*□|\Z)", items, re.S):
                        chunks.append(self._base(document, _compact(item), f"Anhang 1: {category}", content_type="checklist_item", checklist_name="Sprachsensible Leistungserhebung", category=category.split(" ", 1)[1], structure={"chapter": "Anhang 1", "section": "Checkliste"}))
                continue
            # Create linked, whole example pairs and omit them from generic chunks to prevent duplicates.
            pairs = list(re.finditer(r"(?ms)^Schwer verständlich:\s*(.*?)(?=^Leicht verständlich:)^Leicht verständlich:\s*(.*?)(?=^Schwer verständlich:|\Z)", text))
            residual = text
            for pair in pairs:
                pair_number += 1
                chunks.append(self._base(document, _compact(pair.group(0)), f"{chapter} {section}: Beispiel {pair_number}", content_type="example_pair", example_pair_id=f"{document.document_id}_example_{pair_number:02d}", difficult_example=_compact(pair.group(1)), easy_example=_compact(pair.group(2)), structure={"chapter": chapter, "section": section}))
                residual = residual.replace(pair.group(0), "")
            for paragraph in _paragraph_chunks(residual):
                chunks.append(self._base(document, paragraph, f"{chapter} {section}", content_type="guidance", structure={"chapter": chapter, "section": section}))
        return chunks


CHUNKER_REGISTRY: dict[str, DocumentChunker] = {
    "legal": LegalChunker(),
    "handreichung_operatoren": OperatorHandreichungChunker(),
    "handreichung_sprachsensibel": SprachsensibelHandreichungChunker(),
    "handreichung": GenericChunker(),
    "generic": GenericChunker(),
}


def classify_source(path: Path) -> str:
    name = path.name.lower()
    if "operatoren" in name and "pflegeplus" in name:
        return "handreichung_operatoren"
    if "sprachsensibel" in name and "pflegeplus" in name:
        return "handreichung_sprachsensibel"
    if name.startswith(("pflbg", "pflaprv")):
        return "legal"
    return "generic"


def chunk_document(document: SourceDocument) -> list[dict]:
    chunks = CHUNKER_REGISTRY[document.document_type].chunk(document)
    for index, chunk in enumerate(chunks):
        chunk["chunk_index"] = index
        chunk["chunk_id"] = f"{document.document_id}_{index:05d}"
        # Retain old field name for compatibility with existing stored artefacts.
        chunk["source_id"] = document.document_id
    return chunks
