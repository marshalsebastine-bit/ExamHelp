from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Iterable

from bs4 import BeautifulSoup
from pypdf import PdfReader

from app.chunking import SourceDocument, chunk_document, classify_source


def clean_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def read_html(path: Path) -> str:
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return clean_text(soup.get_text("\n"))


def read_legal_html(path: Path) -> str:
    """Extract only individual provisions from gesetze-im-internet HTML.

    The official pages place each provision in ``div.jnnorm[title=Einzelnorm]``.
    Selecting those nodes avoids table-of-contents entries, navigation, print headers,
    and URLs that make PDF extraction noisy and dilute retrieval.
    """
    soup = BeautifulSoup(path.read_text(encoding="iso-8859-1"), "lxml")
    provisions: list[str] = []
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
        if text:
            provisions.append(f"{heading}\n\n{text}")
    if not provisions:
        raise ValueError(f"No individual provisions found in official legal HTML: {path}")
    return "\n\n".join(provisions)


def read_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    return clean_text("\n\n".join((page.extract_text() or "") for page in reader.pages))


def read_text(path: Path) -> str:
    return clean_text(path.read_text(encoding="utf-8"))


def read_source(path: Path, document_type: str | None = None) -> str:
    suffix = path.suffix.lower()
    if suffix in {".html", ".htm"}:
        if document_type == "legal":
            return read_legal_html(path)
        return read_html(path)
    if suffix == ".pdf":
        return read_pdf(path)
    if suffix in {".txt", ".md"}:
        return read_text(path)
    raise ValueError(f"Unsupported file type: {path}")


def source_id(path: Path) -> str:
    return hashlib.sha1(path.name.encode("utf-8")).hexdigest()[:12]

# TODO:- for real legal RAG system,eventually move to token-aware and structure-aware chunking.
def chunk_text(text: str, max_chars: int = 2600, overlap_chars: int = 250) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        candidate = f"{current}\n\n{para}".strip() if current else para
        if len(candidate) <= max_chars:
            current = candidate
            continue

        if current:
            chunks.append(current)
        tail = current[-overlap_chars:] if overlap_chars else ""
        current = f"{tail}\n\n{para}".strip()

        if len(current) > max_chars:
            start = 0
            while start < len(current):
                end = min(start + max_chars, len(current))
                piece = current[start:end].strip()
                if piece:
                    chunks.append(piece)
                if end == len(current):
                    break
                start = max(0, end - overlap_chars)
            current = ""

    if current:
        chunks.append(current)
    return chunks


def build_chunks(paths: Iterable[Path]) -> list[dict]:
    """Read sources and delegate parsing to the document-type registry."""
    all_chunks: list[dict] = []
    for path in paths:
        document_type = classify_source(path)
        document = SourceDocument(
            document_id=source_id(path), path=path, title=path.stem,
            text=read_source(path, document_type=document_type), document_type=document_type,
        )
        all_chunks.extend(chunk_document(document))
    return all_chunks
