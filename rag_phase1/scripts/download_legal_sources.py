"""Download the authoritative PflBG and PflAPrV HTML documents for ingestion."""
from __future__ import annotations

from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"

SOURCES = {
    "PflBG.html": "https://www.gesetze-im-internet.de/pflbg/BJNR258110017.html",
    "PflAPrV.html": "https://www.gesetze-im-internet.de/pflaprv/BJNR157200018.html",
}


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for filename, url in SOURCES.items():
        request = Request(url, headers={"User-Agent": "ExamHelp-RAG/0.1"})
        with urlopen(request, timeout=30) as response:
            content = response.read()
        temporary = RAW_DIR / f"{filename}.tmp"
        temporary.write_bytes(content)
        temporary.replace(RAW_DIR / filename)
        print(f"Downloaded {filename}")


if __name__ == "__main__":
    main()
