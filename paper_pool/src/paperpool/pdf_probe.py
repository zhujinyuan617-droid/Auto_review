"""PDF probing helpers for page count and text snippets."""

from __future__ import annotations

import re
import logging
from pathlib import Path
from typing import Any

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover - import availability is reported in probe output.
    PdfReader = None  # type: ignore[assignment]


logging.getLogger("pypdf").setLevel(logging.ERROR)

MIN_HEALTHY_SIZE_BYTES = 50 * 1024
DEFAULT_TEXT_PAGES = 3
DEFAULT_TEXT_CHAR_LIMIT = 4000

DECISION_CANDIDATE = "candidate_for_pool"
DECISION_MANUAL = "needs_manual_review"
DECISION_BROKEN = "reject_broken_pdf"
DECISION_NON_BODY = "reject_non_literature_body"

CLASS_MAIN_ARTICLE = "main_article"
CLASS_REVIEW_ARTICLE = "review_article"
CLASS_METHOD_ARTICLE = "method_article"
CLASS_THESIS = "thesis_or_dissertation"
CLASS_REPORT_PREPRINT = "report_or_preprint"
CLASS_SUPPLEMENT = "supplement"
CLASS_CORRECTION = "correction_or_erratum"
CLASS_COVER_TOC = "cover_or_toc"
CLASS_GRAPHICAL_ABSTRACT = "graphical_abstract"
CLASS_UNKNOWN = "unknown"


FILENAME_FLAG_PATTERNS: list[tuple[str, str, str]] = [
    ("supplement", CLASS_SUPPLEMENT, r"\b(supplement|supplementary|supporting[-_ ]information|supporting[-_ ]material|si)\b"),
    ("correction_or_erratum", CLASS_CORRECTION, r"\b(correction|erratum|corrigendum|retraction)\b"),
    ("graphical_abstract", CLASS_GRAPHICAL_ABSTRACT, r"\b(graphical[-_ ]abstract|graphicalabstract)\b"),
    ("cover_or_toc", CLASS_COVER_TOC, r"\b(cover|table[-_ ]of[-_ ]contents|contents|toc|front[-_ ]matter)\b"),
    ("highlights", CLASS_GRAPHICAL_ABSTRACT, r"\b(highlights?)\b"),
]

TEXT_FLAG_PATTERNS: list[tuple[str, str, str]] = [
    ("supplement", CLASS_SUPPLEMENT, r"\b(supporting information|supplementary material|supplemental material)\b"),
    ("correction_or_erratum", CLASS_CORRECTION, r"\b(correction|erratum|corrigendum|retraction notice)\b"),
    ("graphical_abstract", CLASS_GRAPHICAL_ABSTRACT, r"\bgraphical abstract\b"),
    ("cover_or_toc", CLASS_COVER_TOC, r"\b(table of contents|front matter)\b"),
]


def _clean_text(value: str, limit: int) -> str:
    cleaned = re.sub(r"\s+", " ", value or "").strip()
    return cleaned[:limit]


def _match_flags(value: str, patterns: list[tuple[str, str, str]]) -> list[dict[str, str]]:
    lowered = value.lower()
    flags: list[dict[str, str]] = []
    for name, document_class, pattern in patterns:
        if re.search(pattern, lowered):
            flags.append({"flag": name, "document_class": document_class})
    return flags


def _first_flag_class(flags: list[dict[str, str]], default: str = CLASS_UNKNOWN) -> str:
    for flag in flags:
        value = flag.get("document_class") or ""
        if value:
            return value
    return default


def _is_missing_parser_dependency(exc: Exception) -> bool:
    text = f"{type(exc).__name__}:{exc}".lower()
    return "dependencyerror" in text or "cryptography" in text


def _infer_body_class(path: Path, text: str) -> str:
    combined = f"{path.name} {text[:1200]}".lower()
    if re.search(r"\b(review|综述|advances in|recent advances|progress in)\b", combined):
        return CLASS_REVIEW_ARTICLE
    if re.search(r"\b(method|protocol|workflow|benchmark|database|dataset|algorithm)\b", combined):
        return CLASS_METHOD_ARTICLE
    if re.search(r"\b(thesis|dissertation|学位论文|硕士|博士)\b", combined):
        return CLASS_THESIS
    if re.search(r"\b(preprint|arxiv|technical report|working paper)\b", combined):
        return CLASS_REPORT_PREPRINT
    return CLASS_MAIN_ARTICLE


def probe_pdf(path: Path, *, text_pages: int = DEFAULT_TEXT_PAGES, text_char_limit: int = DEFAULT_TEXT_CHAR_LIMIT) -> dict[str, Any]:
    """Return objective PDF health/body signals without judging research topic."""
    resolved = path.resolve()
    result: dict[str, Any] = {
        "path": str(resolved),
        "filename": path.name,
        "exists": path.exists(),
        "size_bytes": 0,
        "pdf_magic_ok": False,
        "parser": "pypdf" if PdfReader is not None else "",
        "parser_error": "",
        "is_encrypted": False,
        "decrypt_attempted": False,
        "decrypt_ok": False,
        "page_count": 0,
        "text_pages_checked": 0,
        "extracted_text_chars": 0,
        "first_text": "",
        "filename_flags": [],
        "text_flags": [],
        "document_class": CLASS_UNKNOWN,
        "pool_decision": DECISION_MANUAL,
        "decision_reasons": [],
        "warnings": [],
    }
    reasons: list[str] = result["decision_reasons"]
    warnings: list[str] = result["warnings"]

    if not path.exists():
        reasons.append("file_missing")
        result["pool_decision"] = DECISION_BROKEN
        return result

    result["size_bytes"] = path.stat().st_size
    if result["size_bytes"] <= 0:
        reasons.append("empty_file")
        result["pool_decision"] = DECISION_BROKEN
        return result
    if result["size_bytes"] < MIN_HEALTHY_SIZE_BYTES:
        warnings.append("small_pdf_file")

    try:
        with path.open("rb") as handle:
            result["pdf_magic_ok"] = handle.read(5) == b"%PDF-"
    except OSError as exc:
        reasons.append(f"read_failed:{exc}")
        result["pool_decision"] = DECISION_BROKEN
        return result
    if not result["pdf_magic_ok"]:
        reasons.append("missing_pdf_magic")
        result["pool_decision"] = DECISION_BROKEN
        return result

    result["filename_flags"] = _match_flags(path.name, FILENAME_FLAG_PATTERNS)
    if PdfReader is None:
        warnings.append("pypdf_not_available")
        if result["filename_flags"]:
            result["document_class"] = _first_flag_class(result["filename_flags"])
            result["pool_decision"] = DECISION_NON_BODY
            reasons.append(f"filename_indicates_{result['document_class']}")
        return result

    text_parts: list[str] = []
    try:
        reader = PdfReader(str(path), strict=False)
        result["is_encrypted"] = bool(reader.is_encrypted)
        if reader.is_encrypted:
            result["decrypt_attempted"] = True
            try:
                result["decrypt_ok"] = bool(reader.decrypt(""))
            except Exception as exc:  # pypdf can raise provider-specific exceptions here.
                result["parser_error"] = f"decrypt_failed:{exc}"
                if _is_missing_parser_dependency(exc):
                    reasons.append("pdf_parser_dependency_missing")
                    result["pool_decision"] = DECISION_MANUAL
                    return result
                reasons.append("encrypted_pdf")
                result["pool_decision"] = DECISION_BROKEN
                return result
            if not result["decrypt_ok"]:
                reasons.append("encrypted_pdf")
                result["pool_decision"] = DECISION_BROKEN
                return result

        result["page_count"] = len(reader.pages)
        if result["page_count"] <= 0:
            reasons.append("no_pages")
            result["pool_decision"] = DECISION_BROKEN
            return result

        pages_to_check = min(text_pages, result["page_count"])
        for index in range(pages_to_check):
            try:
                text_parts.append(reader.pages[index].extract_text() or "")
                result["text_pages_checked"] += 1
            except Exception as exc:
                warnings.append(f"text_extract_page_{index + 1}_failed:{type(exc).__name__}")
    except Exception as exc:
        result["parser_error"] = f"{type(exc).__name__}:{exc}"
        if _is_missing_parser_dependency(exc):
            reasons.append("pdf_parser_dependency_missing")
            result["pool_decision"] = DECISION_MANUAL
            return result
        reasons.append("pdf_parse_failed")
        result["pool_decision"] = DECISION_BROKEN
        return result

    first_text = _clean_text(" ".join(text_parts), text_char_limit)
    result["first_text"] = first_text
    result["extracted_text_chars"] = len(first_text)
    result["text_flags"] = _match_flags(first_text[:1500], TEXT_FLAG_PATTERNS)

    filename_flags = result["filename_flags"]
    text_flags = result["text_flags"]
    if filename_flags:
        result["document_class"] = _first_flag_class(filename_flags)
        result["pool_decision"] = DECISION_NON_BODY
        reasons.append(f"filename_indicates_{result['document_class']}")
        return result

    if text_flags and result["page_count"] <= 2:
        result["document_class"] = _first_flag_class(text_flags)
        result["pool_decision"] = DECISION_NON_BODY
        reasons.append(f"short_pdf_text_indicates_{result['document_class']}")
        return result

    if result["page_count"] <= 1 and result["extracted_text_chars"] < 500:
        result["document_class"] = CLASS_UNKNOWN
        result["pool_decision"] = DECISION_MANUAL
        reasons.append("single_page_low_text")
        return result

    if result["extracted_text_chars"] < 300:
        result["document_class"] = CLASS_UNKNOWN
        result["pool_decision"] = DECISION_MANUAL
        reasons.append("low_extractable_text")
        return result

    result["document_class"] = _infer_body_class(path, first_text)
    result["pool_decision"] = DECISION_CANDIDATE
    reasons.append("pdf_looks_like_literature_body")
    return result
