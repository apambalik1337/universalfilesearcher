"""
parsers package

Central registry mapping file extensions to parser instances. Adding a new
file type means: write a new *_parser.py implementing BaseParser, register
it in ALL_PARSERS below, and add its extension(s) to CATEGORY_MAP (and
ICON_MAP if you want a distinct icon) so it shows up correctly in the
search filter UI and result badges. Nothing else in the application needs
to change.
"""

from .xlsx_parser import XlsxParser
from .xls_parser import XlsParser
from .pdf_parser import PdfParser
from .csv_parser import CsvParser
from .docx_parser import DocxParser
from .doc_parser import DocParser
from .txt_parser import TxtParser
from .pptx_parser import PptxParser
from .ppt_parser import PptParser
from .ods_parser import OdsParser
from .odt_parser import OdtParser
from .rtf_parser import RtfParser
from .json_parser import JsonParser
from .xml_parser import XmlParser
from .html_parser_local import HtmlParser
from .eml_parser import EmlParser
from .yaml_parser import YamlParser

ALL_PARSERS = [
    XlsxParser(),
    XlsParser(),
    PdfParser(),
    CsvParser(),
    DocxParser(),
    DocParser(),
    TxtParser(),
    PptxParser(),
    PptParser(),
    OdsParser(),
    OdtParser(),
    RtfParser(),
    JsonParser(),
    XmlParser(),
    HtmlParser(),
    EmlParser(),
    YamlParser(),
]

# Build a fast extension -> parser lookup table.
_EXT_MAP = {}
for _parser in ALL_PARSERS:
    for _ext in _parser.extensions:
        _EXT_MAP[_ext] = _parser

SUPPORTED_EXTENSIONS = sorted(_EXT_MAP.keys())

# Grouping used for the "Search in" file-type filter and for result badges.
# Every supported extension must appear here exactly once.
CATEGORY_MAP = {
    ".pdf": "PDF",
    ".xlsx": "Excel", ".xlsm": "Excel", ".xls": "Excel",
    ".docx": "Word", ".doc": "Word",
    ".pptx": "PowerPoint", ".ppt": "PowerPoint",
    ".csv": "CSV", ".tsv": "CSV",
    ".txt": "Text", ".log": "Text",
    ".ods": "OpenDocument", ".odt": "OpenDocument",
    ".rtf": "RTF",
    ".json": "Data", ".xml": "Data", ".yaml": "Data", ".yml": "Data",
    ".html": "Web", ".htm": "Web",
    ".eml": "Email",
}

CATEGORIES = ["PDF", "Excel", "Word", "PowerPoint", "CSV", "Text",
              "OpenDocument", "RTF", "Data", "Web", "Email"]

ICON_MAP = {
    ".pdf": "📄",
    ".xlsx": "📊", ".xlsm": "📊", ".xls": "📊", ".ods": "📊",
    ".docx": "📝", ".doc": "📝", ".odt": "📝", ".rtf": "📃",
    ".pptx": "📽️", ".ppt": "📽️",
    ".csv": "📋", ".tsv": "📋",
    ".txt": "🗒️", ".log": "🗒️",
    ".json": "🧩", ".xml": "🧩", ".yaml": "🧩", ".yml": "🧩",
    ".html": "🌐", ".htm": "🌐",
    ".eml": "✉️",
}


def get_parser_for(file_path: str):
    """Return the parser instance responsible for this file's extension, or None."""
    import os
    ext = os.path.splitext(file_path)[1].lower()
    return _EXT_MAP.get(ext)


def is_supported(file_path: str) -> bool:
    return get_parser_for(file_path) is not None


def category_for(extension: str) -> str:
    return CATEGORY_MAP.get(extension.lower(), "Other")


def icon_for(extension: str) -> str:
    return ICON_MAP.get(extension.lower(), "📁")
