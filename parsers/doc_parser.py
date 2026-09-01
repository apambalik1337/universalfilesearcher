"""
doc_parser.py

Parses legacy binary Word documents (.doc).

python-docx cannot open .doc (it's a completely different binary OLE
format, not a zip of XML like .docx), so there is no native pure-Python
way to reliably read it. Per spec Priority 5 ("SHOULD SUPPORT"), we
implement a real fallback rather than pretending support exists:

  1. Try LibreOffice headless conversion to .txt (best fidelity, works on
     Windows/Mac/Linux if LibreOffice is installed).
  2. If LibreOffice isn't available, try `antiword` if present.
  3. If neither is available, report a clear, actionable error telling the
     user exactly what to install -- we do NOT silently claim success.
"""

import os
import shutil
import subprocess
import tempfile

from .base_parser import BaseParser, ParseResult, Record


def _find_soffice():
    for name in ("soffice", "libreoffice"):
        path = shutil.which(name)
        if path:
            return path
    # Common Windows install locations, in case it's not on PATH.
    windows_candidates = [
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ]
    for candidate in windows_candidates:
        if os.path.exists(candidate):
            return candidate
    return None


class DocParser(BaseParser):
    extensions = (".doc",)
    display_name = "Word 97-2003 (.doc)"

    def parse(self, file_path: str) -> ParseResult:
        soffice = _find_soffice()
        antiword = shutil.which("antiword")

        if soffice:
            return self._parse_with_libreoffice(file_path, soffice)
        elif antiword:
            return self._parse_with_antiword(file_path, antiword)
        else:
            return ParseResult(
                success=False,
                error=(
                    "No .doc extractor available. Install LibreOffice "
                    "(https://www.libreoffice.org/download/) or antiword to "
                    "enable .doc support, then re-index."
                ),
            )

    def _parse_with_libreoffice(self, file_path: str, soffice_path: str) -> ParseResult:
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                result = subprocess.run(
                    [
                        soffice_path,
                        "--headless",
                        "--norestore",
                        "--convert-to", "txt:Text",
                        "--outdir", tmpdir,
                        file_path,
                    ],
                    capture_output=True,
                    timeout=90,
                )
            except subprocess.TimeoutExpired:
                return ParseResult(success=False, error="LibreOffice conversion timed out")
            except Exception as e:
                return ParseResult(success=False, error=f"LibreOffice conversion failed: {e}")

            if result.returncode != 0:
                stderr = result.stderr.decode(errors="replace") if result.stderr else ""
                return ParseResult(
                    success=False,
                    error=f"LibreOffice could not convert file: {stderr[:300]}",
                )

            base = os.path.splitext(os.path.basename(file_path))[0]
            txt_path = os.path.join(tmpdir, base + ".txt")
            if not os.path.exists(txt_path):
                return ParseResult(success=False, error="LibreOffice conversion produced no output")

            try:
                with open(txt_path, "r", encoding="utf-8", errors="replace") as f:
                    text = f.read()
            except Exception as e:
                return ParseResult(success=False, error=f"Could not read converted text: {e}")

        return self._records_from_text(text)

    def _parse_with_antiword(self, file_path: str, antiword_path: str) -> ParseResult:
        try:
            result = subprocess.run(
                [antiword_path, file_path],
                capture_output=True,
                timeout=60,
            )
        except Exception as e:
            return ParseResult(success=False, error=f"antiword failed: {e}")

        if result.returncode != 0:
            return ParseResult(
                success=False,
                error=f"antiword could not read file: {result.stderr.decode(errors='replace')[:300]}",
            )

        text = result.stdout.decode(errors="replace")
        return self._records_from_text(text)

    def _records_from_text(self, text: str) -> ParseResult:
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
        if not paragraphs:
            return ParseResult(success=True, records=[], warning="No content found in document")
        records = [
            Record(content=p, location=f"Paragraph {i}")
            for i, p in enumerate(paragraphs, start=1)
        ]
        return ParseResult(success=True, records=records)

    def is_dependency_available(self) -> bool:
        return _find_soffice() is not None or shutil.which("antiword") is not None

    def dependency_message(self) -> str:
        return (
            "Install LibreOffice (https://www.libreoffice.org/download/) "
            "or antiword to enable .doc support."
        )
