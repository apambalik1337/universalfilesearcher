"""
rtf_parser.py

Parses Rich Text Format (.rtf) files using striprtf, a pure-Python RTF
text extractor. No Word/LibreOffice dependency required.
"""

from striprtf.striprtf import rtf_to_text

from .base_parser import BaseParser, ParseResult, Record

CANDIDATE_ENCODINGS = ["utf-8", "cp1252", "latin-1"]


class RtfParser(BaseParser):
    extensions = (".rtf",)
    display_name = "Rich Text Format (.rtf)"

    def parse(self, file_path: str) -> ParseResult:
        try:
            with open(file_path, "rb") as f:
                raw = f.read()
        except Exception as e:
            return ParseResult(success=False, error=f"Could not read file: {e}")

        raw_text = None
        for enc in CANDIDATE_ENCODINGS:
            try:
                raw_text = raw.decode(enc)
                break
            except (UnicodeDecodeError, LookupError):
                continue
        if raw_text is None:
            raw_text = raw.decode("utf-8", errors="replace")

        try:
            text = rtf_to_text(raw_text)
        except Exception as e:
            return ParseResult(success=False, error=f"Failed to parse RTF: {e}")

        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
        if not paragraphs:
            return ParseResult(success=True, records=[], warning="No content found in document")

        records = [Record(content=p, location=f"Paragraph {i}") for i, p in enumerate(paragraphs, start=1)]
        return ParseResult(success=True, records=records)

    def is_dependency_available(self) -> bool:
        try:
            import striprtf  # noqa
            return True
        except ImportError:
            return False

    def dependency_message(self) -> str:
        return "Install with: pip install striprtf"
