"""
ods_parser.py

Parses OpenDocument Spreadsheet files (.ods) using odfpy.
Searches every sheet and every populated cell, preserving sheet name and
cell coordinate.
"""

from odf.opendocument import load
from odf.table import Table, TableRow, TableCell
from odf.text import P
from odf import teletype

from .base_parser import BaseParser, ParseResult, Record


class OdsParser(BaseParser):
    extensions = (".ods",)
    display_name = "OpenDocument Spreadsheet (.ods)"

    def parse(self, file_path: str) -> ParseResult:
        try:
            doc = load(file_path)
        except Exception as e:
            return ParseResult(success=False, error=f"Failed to open spreadsheet: {e}")

        records = []
        try:
            tables = doc.spreadsheet.getElementsByType(Table)
            for table in tables:
                sheet_name = table.getAttribute("name") or "Sheet"
                row_idx = 0
                for row in table.getElementsByType(TableRow):
                    row_idx += 1
                    col_idx = 0
                    for cell in row.getElementsByType(TableCell):
                        col_idx += 1
                        text_parts = [teletype.extractText(p) for p in cell.getElementsByType(P)]
                        text = " ".join(t.strip() for t in text_parts if t.strip()).strip()
                        if not text:
                            continue
                        col_letter = _col_letter(col_idx - 1)
                        records.append(
                            Record(content=text, sheet=str(sheet_name), cell=f"{col_letter}{row_idx}")
                        )
        except Exception as e:
            return ParseResult(success=False, error=f"Error while reading sheet contents: {e}", records=records)

        if not records:
            return ParseResult(success=True, records=[], warning="No content found in spreadsheet")

        return ParseResult(success=True, records=records)

    def is_dependency_available(self) -> bool:
        try:
            import odf  # noqa
            return True
        except ImportError:
            return False

    def dependency_message(self) -> str:
        return "Install with: pip install odfpy"


def _col_letter(idx: int) -> str:
    letters = ""
    idx += 1
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        letters = chr(65 + rem) + letters
    return letters
