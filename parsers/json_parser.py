"""
json_parser.py

Parses .json files by flattening the (possibly deeply nested) structure
into individual searchable records, one per leaf value (string, number,
boolean). The location shown to the user is the JSON path to that value,
e.g. "members[3].name", so a match is traceable back to exactly where in
the file it came from -- the same principle as cell/page/paragraph for
other formats.
"""

import json

from .base_parser import BaseParser, ParseResult, Record

MAX_RECORDS = 20000  # safety cap for pathological / huge JSON files


class JsonParser(BaseParser):
    extensions = (".json",)
    display_name = "JSON"

    def parse(self, file_path: str) -> ParseResult:
        try:
            with open(file_path, "rb") as f:
                raw = f.read()
        except Exception as e:
            return ParseResult(success=False, error=f"Could not read file: {e}")

        text = None
        for enc in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                text = raw.decode(enc)
                break
            except (UnicodeDecodeError, LookupError):
                continue
        if text is None:
            return ParseResult(success=False, error="Could not detect a valid text encoding")

        try:
            data = json.loads(text)
        except Exception as e:
            return ParseResult(success=False, error=f"Invalid JSON: {e}")

        records = []
        _flatten(data, "$", records)

        if not records:
            return ParseResult(success=True, records=[], warning="No content found in JSON file")

        return ParseResult(success=True, records=records[:MAX_RECORDS])

    def is_dependency_available(self) -> bool:
        return True


def _flatten(value, path, records):
    if len(records) >= MAX_RECORDS:
        return
    if isinstance(value, dict):
        for key, sub in value.items():
            _flatten(sub, f"{path}.{key}", records)
    elif isinstance(value, list):
        for idx, sub in enumerate(value):
            _flatten(sub, f"{path}[{idx}]", records)
    elif value is None:
        return
    else:
        text = str(value).strip()
        if text:
            records.append(Record(content=text, location=path))
