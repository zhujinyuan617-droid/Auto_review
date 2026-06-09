from __future__ import annotations

import re

from .records import CitationRecord

_TAG = re.compile(r"^([A-Z0-9]{2})  - ?(.*)$")


def parse_ris_text(text: str) -> list[CitationRecord]:
    """Parse RIS text into CitationRecords. Hand-rolled tag state machine.

    TY starts a record, ER ends it; lines not matching a tag continue the last
    tag's value; AU may repeat (collected as authors).
    """
    records: list[CitationRecord] = []
    current: dict[str, list[str]] | None = None
    last_tag: str | None = None

    for line in text.splitlines():
        match = _TAG.match(line)
        if match:
            tag, value = match.group(1), match.group(2).strip()
            if tag == "TY":
                current = {}
                last_tag = None
                continue
            if tag == "ER":
                if current is not None:
                    records.append(_to_record(current))
                current = None
                last_tag = None
                continue
            if current is not None:
                current.setdefault(tag, []).append(value)
                last_tag = tag
        elif current is not None and last_tag is not None and line.strip():
            current[last_tag][-1] = (current[last_tag][-1] + " " + line.strip()).strip()

    return records


def _to_record(tags: dict[str, list[str]]) -> CitationRecord:
    def first(tag: str, *fallbacks: str) -> str:
        for key in (tag, *fallbacks):
            if tags.get(key):
                return tags[key][0].strip()
        return ""

    return CitationRecord(
        title=first("TI", "T1"),
        doi=first("DO"),
        year=first("PY", "Y1"),
        journal=first("T2", "JO", "JF"),
        authors=tuple(a.strip() for a in tags.get("AU", []) if a.strip()),
    )
