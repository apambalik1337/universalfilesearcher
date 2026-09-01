"""
ppt_parser.py

Parses legacy binary PowerPoint files (.ppt) by converting to .pptx with
LibreOffice headless (preserves slide structure) and reusing PptxParser.
Reports a clear, actionable error if LibreOffice isn't available rather
than pretending .ppt is supported.
"""

import os
import shutil
import subprocess
import tempfile

from .base_parser import BaseParser, ParseResult
from .pptx_parser import PptxParser


def _find_soffice():
    for name in ("soffice", "libreoffice"):
        path = shutil.which(name)
        if path:
            return path
    for candidate in (
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ):
        if os.path.exists(candidate):
            return candidate
    return None


class PptParser(BaseParser):
    extensions = (".ppt",)
    display_name = "PowerPoint 97-2003 (.ppt)"

    def parse(self, file_path: str) -> ParseResult:
        soffice = _find_soffice()
        if not soffice:
            return ParseResult(
                success=False,
                error=(
                    "No .ppt extractor available. Install LibreOffice "
                    "(https://www.libreoffice.org/download/) to enable .ppt support, then re-index."
                ),
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                result = subprocess.run(
                    [soffice, "--headless", "--norestore", "--convert-to", "pptx", "--outdir", tmpdir, file_path],
                    capture_output=True, timeout=90,
                )
            except subprocess.TimeoutExpired:
                return ParseResult(success=False, error="LibreOffice conversion timed out")
            except Exception as e:
                return ParseResult(success=False, error=f"LibreOffice conversion failed: {e}")

            if result.returncode != 0:
                stderr = result.stderr.decode(errors="replace") if result.stderr else ""
                return ParseResult(success=False, error=f"LibreOffice could not convert file: {stderr[:300]}")

            base = os.path.splitext(os.path.basename(file_path))[0]
            pptx_path = os.path.join(tmpdir, base + ".pptx")
            if not os.path.exists(pptx_path):
                return ParseResult(success=False, error="LibreOffice conversion produced no output")

            return PptxParser().parse(pptx_path)

    def is_dependency_available(self) -> bool:
        return _find_soffice() is not None

    def dependency_message(self) -> str:
        return "Install LibreOffice (https://www.libreoffice.org/download/) to enable .ppt support."
