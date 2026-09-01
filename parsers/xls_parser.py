"""
xls_parser.py

Parses legacy binary Excel files (.xls) using xlrd.

Note: xlrd >= 2.0 dropped .xlsx support but still supports the old binary
.xls format, which is exactly what we need here since .xlsx is already
handled by xlsx_parser.py.
"""

import xlrd

from .base_parser import BaseParser, ParseResult, Record


class XlsParser(BaseParser):
    extensions = (".xls",)
    display_name = "Excel 97-2003 (.xls)"

    def parse(self, file_path: str) -> ParseResult:
        try:
            book = xlrd.open_workbook(file_path)
        except Exception as e:
            return ParseResult(
                success=False,
                error=f"Unable to read legacy Excel format: {e}",
            )

        records = []
        try:
            for sheet in book.sheets():
                for row_idx in range(sheet.nrows):
                    for col_idx in range(sheet.ncols):
                        try:
                            cell = sheet.cell(row_idx, col_idx)
                        except Exception:
                            continue
                        value = cell.value
                        if value is None or value == "":
                            continue
                        text = str(value).strip()
                        if not text:
                            continue
                        col_letter = _col_letter(col_idx)
                        records.append(
                            Record(
                                content=text,
                                sheet=sheet.name,
                                cell=f"{col_letter}{row_idx + 1}",
                            )
                        )
        except Exception as e:
            return ParseResult(
                success=False,
                error=f"Error while reading sheet contents: {e}",
                records=records,
            )

        if not records:
            return ParseResult(success=True, records=[], warning="No content found in workbook")

        return ParseResult(success=True, records=records)

    def is_dependency_available(self) -> bool:
        try:
            import xlrd  # noqa
            return True
        except ImportError:
            return False

    def dependency_message(self) -> str:
        return "Install with: pip install xlrd"


def _col_letter(idx: int) -> str:
    """Convert a 0-based column index to an Excel-style column letter (0 -> A, 1 -> B, ...)."""
    letters = ""
    idx += 1
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        letters = chr(65 + rem) + letters
    return letters
