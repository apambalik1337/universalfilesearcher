"""
txt_parser.py

Parses plain .txt and .log files with encoding detection for common
Windows encodings in addition to UTF-8.
"""

import chardet

from .base_parser import BaseParser, ParseResult, Record

CANDIDATE_ENCODINGS = ["utf-8-sig", "utf-8", "cp1252", "latin-1"]


class TxtParser(BaseParser):
    extensions = (".txt", ".log")
    display_name = "Text (.txt, .log)"

    def parse(self, file_path: str) -> ParseResult:
        try:
            with open(file_path, "rb") as f:
                raw = f.read()
        except Exception as e:
            return ParseResult(success=False, error=f"Could not read file: {e}")

        text = None
        for enc in CANDIDATE_ENCODINGS:
            try:
                text = raw.decode(enc)
                break
            except (UnicodeDecodeError, LookupError):
                continue

        if text is None:
            try:
                guess = chardet.detect(raw)
                enc = guess.get("encoding")
                if enc:
                    text = raw.decode(enc, errors="replace")
            except Exception:
                pass

        if text is None:
            return ParseResult(success=False, error="Could not detect a valid text encoding")

        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
        if not paragraphs:
            return ParseResult(success=True, records=[], warning="Empty file")

        records = [
            Record(content=p, location=f"Line {i}")
            for i, p in enumerate(paragraphs, start=1)
        ]
        return ParseResult(success=True, records=records)

    def is_dependency_available(self) -> bool:
        return True
