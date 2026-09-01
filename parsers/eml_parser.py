"""
eml_parser.py

Parses .eml (saved email) files using Python's stdlib `email` package.
No external dependency needed. Indexes the key headers (Subject, From,
To, Cc, Date) as separate labeled records plus the message body (plain
text preferred; falls back to stripping tags from an HTML-only body),
so a search can find a name whether it appears in the sender, subject,
or the body text.
"""

import email
from email import policy
from email.parser import BytesParser

from .base_parser import BaseParser, ParseResult, Record

HEADER_FIELDS = ["Subject", "From", "To", "Cc", "Bcc", "Date"]


class EmlParser(BaseParser):
    extensions = (".eml",)
    display_name = "Email (.eml)"

    def parse(self, file_path: str) -> ParseResult:
        try:
            with open(file_path, "rb") as f:
                msg = BytesParser(policy=policy.default).parse(f)
        except Exception as e:
            return ParseResult(success=False, error=f"Failed to parse email: {e}")

        records = []
        for field in HEADER_FIELDS:
            value = msg.get(field)
            if value:
                records.append(Record(content=str(value).strip(), location=f"Header: {field}"))

        body_text = _extract_body(msg)
        if body_text:
            paragraphs = [p.strip() for p in body_text.split("\n") if p.strip()]
            for i, p in enumerate(paragraphs, start=1):
                records.append(Record(content=p, location=f"Body, line {i}"))

        if not records:
            return ParseResult(success=True, records=[], warning="No content found in email")

        return ParseResult(success=True, records=records)

    def is_dependency_available(self) -> bool:
        return True


def _extract_body(msg) -> str:
    try:
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain" and not part.is_attachment():
                    return part.get_content()
            for part in msg.walk():
                if part.get_content_type() == "text/html" and not part.is_attachment():
                    return _strip_html(part.get_content())
            return ""
        else:
            content_type = msg.get_content_type()
            content = msg.get_content()
            if content_type == "text/html":
                return _strip_html(content)
            return content or ""
    except Exception:
        return ""


def _strip_html(html_text: str) -> str:
    from html.parser import HTMLParser

    class _Stripper(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts = []

        def handle_data(self, data):
            self.parts.append(data)

    try:
        stripper = _Stripper()
        stripper.feed(html_text or "")
        return " ".join(stripper.parts)
    except Exception:
        return html_text or ""
