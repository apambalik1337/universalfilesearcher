"""
base_parser.py

Defines the common interface every file-type parser must implement, and the
normalized record structure that all extracted content is converted into.

Design goal (see project spec section 7 & 8):
    File -> Detect extension -> Select parser -> Extract content
          -> Normalize content -> Store in search index

Every parser subclasses BaseParser and implements parse(file_path), which
must return a list of Record objects (can be empty, never raises for
"expected" failures -- those are reported via ParseResult.error instead).
"""

from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class Record:
    """
    A single normalized, searchable unit of content extracted from a file.

    Not every field is populated for every file type -- see section 8 of the
    spec for per-format examples. `content` is the only field that is always
    required, since it's what actually gets indexed/searched.
    """
    content: str
    sheet: Optional[str] = None
    cell: Optional[str] = None
    row: Optional[int] = None
    column: Optional[str] = None
    page: Optional[int] = None
    slide: Optional[int] = None
    location: Optional[str] = None  # generic location label, e.g. "Table 2", "Paragraph 12"

    def location_summary(self) -> str:
        """Human-readable one-line description of where this record came from."""
        parts = []
        if self.sheet:
            parts.append(f"Sheet: {self.sheet}")
        if self.cell:
            parts.append(f"Cell: {self.cell}")
        if self.row is not None:
            parts.append(f"Row: {self.row}")
        if self.column:
            parts.append(f"Column: {self.column}")
        if self.page is not None:
            parts.append(f"Page: {self.page}")
        if self.slide is not None:
            parts.append(f"Slide: {self.slide}")
        if self.location:
            parts.append(self.location)
        return " | ".join(parts) if parts else ""


@dataclass
class ParseResult:
    """
    Wraps the outcome of parsing a single file. Even on failure this is
    returned (not raised) so the indexer can continue with other files
    (spec section 15: one bad file must never halt indexing).
    """
    success: bool
    records: List[Record] = field(default_factory=list)
    error: Optional[str] = None
    warning: Optional[str] = None  # e.g. "scanned PDF, no extractable text"


class BaseParser:
    """
    Subclass this for each supported file type.

    Contract:
      - `extensions` is a tuple of lowercase extensions this parser handles,
         e.g. (".xlsx",).
      - parse(file_path) must catch its own exceptions and return a
        ParseResult(success=False, error=...) rather than raising, so the
        indexer's per-file try/except is just a safety net, not the primary
        mechanism.
    """
    extensions: tuple = ()
    display_name: str = "Unknown"

    def parse(self, file_path: str) -> ParseResult:
        raise NotImplementedError

    def is_dependency_available(self) -> bool:
        """Override if this parser needs an optional external dependency."""
        return True

    def dependency_message(self) -> str:
        """Human readable message describing how to install a missing dependency."""
        return ""
