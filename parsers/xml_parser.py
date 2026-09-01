"""
xml_parser.py

Parses .xml files using the stdlib ElementTree. Each element's text content
and attribute values are indexed as separate records, with the location
shown as an XPath-like tag path (e.g. "root/members/member[2]/@name" for
an attribute, or "root/members/member[2]" for text content) so a match
can be traced back to exactly where it came from.
"""

import xml.etree.ElementTree as ET

from .base_parser import BaseParser, ParseResult, Record

MAX_RECORDS = 20000


class XmlParser(BaseParser):
    extensions = (".xml",)
    display_name = "XML"

    def parse(self, file_path: str) -> ParseResult:
        try:
            tree = ET.parse(file_path)
        except ET.ParseError as e:
            return ParseResult(success=False, error=f"Malformed XML: {e}")
        except Exception as e:
            return ParseResult(success=False, error=f"Failed to open XML file: {e}")

        records = []
        root = tree.getroot()
        _walk(root, _local_name(root.tag), records)

        if not records:
            return ParseResult(success=True, records=[], warning="No content found in XML file")

        return ParseResult(success=True, records=records[:MAX_RECORDS])

    def is_dependency_available(self) -> bool:
        return True


def _local_name(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _walk(element, path, records):
    if len(records) >= MAX_RECORDS:
        return

    for attr_name, attr_val in element.attrib.items():
        text = (attr_val or "").strip()
        if text:
            records.append(Record(content=text, location=f"{path}/@{attr_name}"))

    text = (element.text or "").strip()
    if text:
        records.append(Record(content=text, location=path))

    counts = {}
    for child in element:
        tag = _local_name(child.tag)
        counts[tag] = counts.get(tag, 0) + 1
        idx = counts[tag]
        child_path = f"{path}/{tag}[{idx}]" if _will_repeat(element, tag) else f"{path}/{tag}"
        _walk(child, child_path, records)


def _will_repeat(parent, tag) -> bool:
    return sum(1 for c in parent if _local_name(c.tag) == tag) > 1
