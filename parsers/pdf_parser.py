"""
pdf_parser.py

Parses PDF files using PyMuPDF (fitz).

Requirements from spec (Priority 2 - MUST WORK):
  - read every page, preserve page number in results
  - handle Malay and English text
  - handle many-page PDFs without failing
  - a PDF extraction failure must not stop the entire indexing process
    (handled at this parser level by catching exceptions per-page, and at
    the indexer level by catching exceptions per-file)
  - detect PDFs with little/no extractable text (likely scanned/image-based)
    and report that clearly instead of silently returning nothing (spec
    section 4) -- OCR itself is explicitly out of scope for V1.
"""

import warnings
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    import pymupdf as fitz  # PyMuPDF (import path renamed upstream; fitz alias kept for clarity)

from .base_parser import BaseParser, ParseResult, Record

# If total extracted characters across the whole document fall below this,
# treat the PDF as "likely scanned / image-based" per spec section 4.
MIN_TEXT_CHARS_THRESHOLD = 20


class PdfParser(BaseParser):
    extensions = (".pdf",)
    display_name = "PDF"

    def parse(self, file_path: str) -> ParseResult:
        try:
            doc = fitz.open(file_path)
        except Exception as e:
            return ParseResult(success=False, error=f"Failed to open PDF: {e}")

        records = []
        total_chars = 0
        page_errors = 0

        try:
            page_count = doc.page_count
            for page_num in range(page_count):
                try:
                    page = doc.load_page(page_num)
                    text = page.get_text("text") or ""
                except Exception:
                    page_errors += 1
                    continue

                stripped = text.strip()
                total_chars += len(stripped)
                if not stripped:
                    continue

                # Store per-line/paragraph rather than the whole page as one
                # giant blob, so context snippets stay tight and useful.
                for chunk in _split_into_chunks(stripped):
                    records.append(Record(content=chunk, page=page_num + 1))
        finally:
            doc.close()

        if total_chars < MIN_TEXT_CHARS_THRESHOLD:
            return ParseResult(
                success=True,
                records=records,
                warning="No searchable text detected. This PDF may be scanned/image-based.",
            )

        if page_errors and not records:
            return ParseResult(
                success=False,
                error=f"Could not extract text from any of {page_errors} page(s).",
            )

        return ParseResult(success=True, records=records)

    def is_dependency_available(self) -> bool:
        try:
            import pymupdf  # noqa
            return True
        except ImportError:
            return False

    def dependency_message(self) -> str:
        return "Install with: pip install pymupdf"


def _split_into_chunks(text: str, max_len: int = 500):
    """
    Split page text into reasonably sized chunks (by blank-line / newline
    boundaries) so search results have tight, relevant context instead of
    an entire page dumped at once. Falls back to fixed-size slicing for
    pages that are one giant unbroken block of text.
    """
    parts = [p.strip() for p in text.split("\n") if p.strip()]
    chunks = []
    buffer = ""
    for part in parts:
        candidate = (buffer + " " + part).strip() if buffer else part
        if len(candidate) > max_len and buffer:
            chunks.append(buffer)
            buffer = part
        else:
            buffer = candidate
    if buffer:
        chunks.append(buffer)
    return chunks if chunks else [text[:max_len]]
