"""
odt_parser.py

Parses OpenDocument Text files (.odt) using odfpy.
Searches paragraphs, headings, and tables.
"""

from odf.opendocument import load
from odf.text import P, H
from odf.table import Table, TableRow, TableCell
from odf import teletype

from .base_parser import BaseParser, ParseResult, Record


class OdtParser(BaseParser):
    extensions = (".odt",)
    display_name = "OpenDocument Text (.odt)"

    def parse(self, file_path: str) -> ParseResult:
        try:
            doc = load(file_path)
        except Exception as e:
            return ParseResult(success=False, error=f"Failed to open document: {e}")

        records = []
        try:
            for i, h in enumerate(doc.getElementsByType(H), start=1):
                text = _element_text(h)
                if text:
                    records.append(Record(content=text, location=f"Heading {i}"))

            for i, p in enumerate(doc.getElementsByType(P), start=1):
                text = _element_text(p)
                if text:
                    records.append(Record(content=text, location=f"Paragraph {i}"))

            for t_idx, table in enumerate(doc.getElementsByType(Table), start=1):
                for r_idx, row in enumerate(table.getElementsByType(TableRow), start=1):
                    for c_idx, cell in enumerate(row.getElementsByType(TableCell), start=1):
                        text_parts = [_element_text(p) for p in cell.getElementsByType(P)]
                        text = " ".join(t for t in text_parts if t).strip()
                        if text:
                            records.append(
                                Record(content=text, location=f"Table {t_idx}", row=r_idx, column=f"Column {c_idx}")
                            )
        except Exception as e:
            return ParseResult(success=False, error=f"Error while reading document contents: {e}", records=records)

        if not records:
            return ParseResult(success=True, records=[], warning="No content found in document")

        return ParseResult(success=True, records=records)

    def is_dependency_available(self) -> bool:
        try:
            import odf  # noqa
            return True
        except ImportError:
            return False

    def dependency_message(self) -> str:
        return "Install with: pip install odfpy"


def _element_text(element) -> str:
    try:
        return teletype.extractText(element).strip()
    except Exception:
        return ""
