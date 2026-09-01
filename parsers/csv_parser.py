"""
csv_parser.py

Parses CSV files, handling headers, quoted values, and encoding detection
(important for Malaysian/Windows-originated files that are often
cp1252 / latin-1 / utf-8-sig rather than plain utf-8).
"""

import csv
import chardet

from .base_parser import BaseParser, ParseResult, Record

# Encodings to try in order before falling back to chardet's best guess.
CANDIDATE_ENCODINGS = ["utf-8-sig", "utf-8", "cp1252", "latin-1"]


class CsvParser(BaseParser):
    extensions = (".csv", ".tsv")
    display_name = "CSV / TSV"

    def parse(self, file_path: str) -> ParseResult:
        raw = None
        try:
            with open(file_path, "rb") as f:
                raw = f.read()
        except Exception as e:
            return ParseResult(success=False, error=f"Could not read file: {e}")

        text, encoding_used = _decode(raw)
        if text is None:
            return ParseResult(success=False, error="Could not detect a valid text encoding")

        # Sniff the dialect (delimiter) but fall back to a sensible default
        # if sniffing fails -- tab for .tsv files, comma otherwise.
        import os
        sample = text[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except Exception:
            dialect = csv.excel_tab if file_path.lower().endswith(".tsv") else csv.excel

        records = []
        try:
            reader = csv.reader(text.splitlines(), dialect)
            rows = list(reader)
        except Exception as e:
            return ParseResult(success=False, error=f"Failed to parse CSV structure: {e}")

        if not rows:
            return ParseResult(success=True, records=[], warning="Empty CSV file")

        header = rows[0]
        data_rows = rows[1:]

        for row_idx, row in enumerate(data_rows, start=2):  # row 1 is header
            for col_idx, value in enumerate(row):
                value = (value or "").strip()
                if not value:
                    continue
                column_name = header[col_idx] if col_idx < len(header) else f"Column {col_idx + 1}"
                records.append(
                    Record(
                        content=value,
                        row=row_idx,
                        column=column_name,
                    )
                )

        if not records:
            return ParseResult(success=True, records=[], warning="No content found in CSV")

        return ParseResult(success=True, records=records)

    def is_dependency_available(self) -> bool:
        return True  # stdlib csv module, always available


def _decode(raw: bytes):
    for enc in CANDIDATE_ENCODINGS:
        try:
            return raw.decode(enc), enc
        except (UnicodeDecodeError, LookupError):
            continue
    # Last resort: let chardet guess.
    try:
        guess = chardet.detect(raw)
        enc = guess.get("encoding")
        if enc:
            return raw.decode(enc, errors="replace"), enc
    except Exception:
        pass
    return None, None
