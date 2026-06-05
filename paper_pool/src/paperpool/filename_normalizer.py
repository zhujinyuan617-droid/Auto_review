"""Filename normalization helpers for formal pool PDFs."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


FORBIDDEN_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
SPACE_RE = re.compile(r"\s+")
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def sanitize_filename(value: str, max_chars: int = 180) -> str:
    value = FORBIDDEN_FILENAME_CHARS.sub("_", value or "")
    value = SPACE_RE.sub(" ", value).strip(" ._")
    if len(value) > max_chars:
        value = value[:max_chars].rstrip(" ._")
    return value or "untitled"


def shorten_filename_part(value: str, max_chars: int) -> str:
    return sanitize_filename(value, max_chars=max_chars) or "untitled"


def extract_year(value: str) -> str:
    match = YEAR_RE.search(value or "")
    return match.group(0) if match else ""


def doi_suffix(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    suffix = value.rsplit("/", 1)[-1]
    return sanitize_filename(suffix, max_chars=80)


def unique_strings(values: list[Any]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def clean_author(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return "unknown"
    value = re.split(r"\s+等\b|等\b|\s+et\s+al\.?\b|\s+and\s+|和|&|,", value, maxsplit=1, flags=re.I)[0]
    value = value.strip()
    if re.search(r"[A-Za-z]", value) and " " in value:
        value = value.split()[0]
    return sanitize_filename(value, max_chars=40) or "unknown"


def parse_filename_metadata(filename: str) -> dict[str, str]:
    stem = Path(filename).stem.strip()

    # Zotero style: "Author 等 - 2024 - Title.pdf".
    match = re.match(r"^(?P<author>.+?)\s+-\s+(?P<year>(?:19|20)\d{2})\s+-\s+(?P<title>.+)$", stem)
    if match:
        return {
            "year": match.group("year"),
            "author": clean_author(match.group("author")),
            "title": match.group("title").strip(),
        }

    # Chinese local style: "2019-Title_Author.pdf".
    match = re.match(r"^(?P<year>(?:19|20)\d{2})[-_](?P<body>.+)$", stem)
    if match:
        body = match.group("body").strip()
        title = body
        author = "unknown"
        if "_" in body:
            maybe_title, maybe_author = body.rsplit("_", 1)
            if maybe_title.strip() and maybe_author.strip():
                title = maybe_title.strip()
                author = clean_author(maybe_author)
        return {
            "year": match.group("year"),
            "author": author,
            "title": title,
        }

    # Local style without a year: "Title_Author.pdf".
    if "_" in stem:
        maybe_title, maybe_author = stem.rsplit("_", 1)
        if maybe_title.strip() and maybe_author.strip() and len(maybe_author.strip()) <= 20:
            return {
                "year": extract_year(stem),
                "author": clean_author(maybe_author),
                "title": maybe_title.strip(),
            }

    return {
        "year": extract_year(stem),
        "author": "unknown",
        "title": stem,
    }


def trusted_parent_metadata(record: dict[str, Any]) -> tuple[str, str]:
    if record.get("parent_overloaded") or record.get("metadata_conflict"):
        return "", ""
    titles = unique_strings(record.get("parent_titles") or [])
    dois = unique_strings(record.get("parent_dois") or [])
    title = titles[0] if len(titles) == 1 else ""
    doi = dois[0] if len(dois) == 1 else ""
    return title, doi


def build_pool_filename(record: dict[str, Any], *, max_chars: int = 220) -> str:
    source_filename = str(record.get("representative_filename") or "untitled.pdf")
    parsed = parse_filename_metadata(source_filename)
    parent_title, parent_doi = trusted_parent_metadata(record)
    candidate_id = str(record.get("candidate_id") or "ZOT-unknown")

    title = parent_title or parsed["title"] or Path(source_filename).stem
    year = parsed["year"] or extract_year(title) or "unknown-year"
    author = parsed["author"] or "unknown"
    suffix = doi_suffix(parent_doi) or candidate_id

    title_part = shorten_filename_part(title, 80)
    filename = f"{year}_{author}_{title_part}_{suffix}.pdf"
    return sanitize_filename(filename, max_chars=max_chars)
