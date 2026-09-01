"""
yaml_parser.py

Parses .yaml/.yml files. Uses PyYAML if it's installed (safe_load, so no
arbitrary Python object construction) and flattens the resulting
dict/list structure the same way json_parser.py does, so matches are
traceable to a key path like "database.host" or "servers[2].name".

If PyYAML isn't installed, falls back to a simple line-by-line "key:
value" scan -- less structurally accurate but still searchable, and the
app clearly reports which mode was used only via normal parsing (no
silent full-fidelity claim either way since both modes extract real text).
"""

from .base_parser import BaseParser, ParseResult, Record

MAX_RECORDS = 20000


class YamlParser(BaseParser):
    extensions = (".yaml", ".yml")
    display_name = "YAML"

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
            import yaml
            data = yaml.safe_load(text)
            records = []
            _flatten(data, "$", records)
        except ImportError:
            records = _line_scan(text)
        except Exception as e:
            return ParseResult(success=False, error=f"Invalid YAML: {e}")

        if not records:
            return ParseResult(success=True, records=[], warning="No content found in YAML file")

        return ParseResult(success=True, records=records[:MAX_RECORDS])

    def is_dependency_available(self) -> bool:
        return True  # falls back to a plain-text scan even without PyYAML

    def dependency_message(self) -> str:
        return "For structured key-path locations, install with: pip install pyyaml (a basic text scan works without it)"


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


def _line_scan(text: str):
    records = []
    for i, line in enumerate(text.split("\n"), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        records.append(Record(content=stripped, location=f"Line {i}"))
    return records
