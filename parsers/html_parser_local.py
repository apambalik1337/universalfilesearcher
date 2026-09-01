"""
html_parser_local.py

Parses .html/.htm files using Python's built-in html.parser (no external
dependency). Script/style content is discarded, block-level tags become
paragraph breaks, and the resulting text blocks are indexed individually
so results show useful context instead of one giant blob for the whole
page.

Named html_parser_local.py (not html_parser.py) to avoid any import
collision with the stdlib html.parser module.
"""

from html.parser import HTMLParser as _HTMLParser

from .base_parser import BaseParser, ParseResult, Record

CANDIDATE_ENCODINGS = ["utf-8-sig", "utf-8", "cp1252", "latin-1"]
BLOCK_TAGS = {
    "p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
    "section", "article", "header", "footer", "blockquote", "td",
}
SKIP_TAGS = {"script", "style", "noscript"}


class _TextExtractor(_HTMLParser):
    def __init__(self):
        super().__init__()
        self.blocks = []
        self._current = []
        self._skip_depth = 0
        self.title = None
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag in BLOCK_TAGS:
            self._flush()

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        if tag == "title":
            self._in_title = False
        if tag in BLOCK_TAGS:
            self._flush()

    def handle_data(self, data):
        if self._skip_depth:
            return
        if self._in_title:
            self.title = (self.title or "") + data
            return
        self._current.append(data)

    def _flush(self):
        text = "".join(self._current).strip()
        if text:
            self.blocks.append(" ".join(text.split()))
        self._current = []

    def close(self):
        self._flush()
        super().close()


class HtmlParser(BaseParser):
    extensions = (".html", ".htm")
    display_name = "HTML"

    def parse(self, file_path: str) -> ParseResult:
        try:
            with open(file_path, "rb") as f:
                raw = f.read()
        except Exception as e:
            return ParseResult(success=False, error=f"Could not read file: {e}")

        text = None
        for enc in CANDIDATE_ENCODINGS:
            try:
                text = raw.decode(enc)
                break
            except (UnicodeDecodeError, LookupError):
                continue
        if text is None:
            return ParseResult(success=False, error="Could not detect a valid text encoding")

        try:
            extractor = _TextExtractor()
            extractor.feed(text)
            extractor.close()
        except Exception as e:
            return ParseResult(success=False, error=f"Failed to parse HTML: {e}")

        records = []
        if extractor.title and extractor.title.strip():
            records.append(Record(content=extractor.title.strip(), location="Title"))
        for i, block in enumerate(extractor.blocks, start=1):
            if block:
                records.append(Record(content=block, location=f"Paragraph {i}"))

        if not records:
            return ParseResult(success=True, records=[], warning="No content found in HTML file")

        return ParseResult(success=True, records=records)

    def is_dependency_available(self) -> bool:
        return True
