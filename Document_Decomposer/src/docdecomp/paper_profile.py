from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


MAINLINE_PROFILE = "english_mainline"
DEFERRED_NON_ENGLISH = "deferred_non_english"
DEFERRED_NON_ARTICLE = "deferred_non_article"
DEFERRED_PROFILES = {DEFERRED_NON_ENGLISH, DEFERRED_NON_ARTICLE}


@dataclass(frozen=True)
class PaperProfile:
    processing_profile: str
    language_hint: str
    profile_reason: str

    @property
    def is_mainline(self) -> bool:
        return self.processing_profile == MAINLINE_PROFILE

    @property
    def is_deferred(self) -> bool:
        return self.processing_profile in DEFERRED_PROFILES


def _record_text(record: dict[str, Any]) -> str:
    def basename(value: str) -> str:
        if not value:
            return ""
        return value.replace("\\", "/").rsplit("/", 1)[-1]

    values = [
        str(record.get("original_filename") or ""),
        basename(str(record.get("staged_pdf") or "")),
        basename(str(record.get("original_path") or "")),
        str(record.get("identity_key") or ""),
    ]
    return " ".join(value for value in values if value)


def _ascii_title_tokens(text: str) -> list[str]:
    stopwords = {"pdf", "zot", "doi", "tokens", "s0066", "index"}
    tokens = [token.lower() for token in re.findall(r"[A-Za-z]{3,}", text)]
    return [token for token in tokens if token not in stopwords]


# A cleaned paper body above this CJK ratio is treated as non-English (bilingual
# Chinese papers with an English title/abstract sit well above this; true English
# papers are ~0). Used as a post-Docling content gate, since the filename-based
# classifier cannot see a Chinese body behind an English title.
CONTENT_CJK_DEFER_THRESHOLD = 0.05


def cjk_ratio(text: str) -> float:
    if not text:
        return 0.0
    cjk = sum(1 for ch in text if "㐀" <= ch <= "鿿")
    return cjk / len(text)


def classify_paper_text(text: str) -> PaperProfile:
    lowered = text.lower()
    if re.search(r"(?:^|[^a-z0-9])subject[\s_.-]*index(?:$|[^a-z0-9])", lowered):
        return PaperProfile(DEFERRED_NON_ARTICLE, "en", "subject_index")

    # Book front/back-matter (e.g. an Index chapter) carries an ISBN-style book id
    # (B978...) together with the word "index". Conservative: requires both signals.
    if re.search(r"b97[89][\d.\-]", lowered) and re.search(r"(?:^|[^a-z0-9])index(?:$|[^a-z0-9])", lowered):
        return PaperProfile(DEFERRED_NON_ARTICLE, "en", "book_index")

    if re.search(r"[\u3400-\u9fff]", text):
        return PaperProfile(DEFERRED_NON_ENGLISH, "non_en", "cjk_filename")

    non_ascii = sum(1 for char in text if ord(char) > 127)
    text_len = max(1, len(text))
    tokens = _ascii_title_tokens(text)
    # Mojibake Chinese filenames often contain many non-ASCII Latin-1 characters
    # plus very few usable English title tokens.
    if non_ascii / text_len >= 0.15 and len(tokens) < 4:
        return PaperProfile(DEFERRED_NON_ENGLISH, "non_en", "mostly_non_ascii_filename")

    if len(tokens) >= 4:
        return PaperProfile(MAINLINE_PROFILE, "en", "english_title_tokens")

    return PaperProfile(MAINLINE_PROFILE, "unknown", "no_defer_signal")


def classify_record(record: dict[str, Any]) -> PaperProfile:
    explicit = str(record.get("processing_profile") or "")
    if explicit == MAINLINE_PROFILE:
        return PaperProfile(
            MAINLINE_PROFILE,
            str(record.get("language_hint") or "en"),
            str(record.get("profile_reason") or "manifest_profile"),
        )
    if explicit in DEFERRED_PROFILES:
        return PaperProfile(
            explicit,
            str(record.get("language_hint") or "unknown"),
            str(record.get("profile_reason") or "manifest_profile"),
        )
    return classify_paper_text(_record_text(record))


def apply_profile(record: dict[str, Any]) -> None:
    profile = classify_paper_text(_record_text(record))
    record["processing_profile"] = profile.processing_profile
    record["language_hint"] = profile.language_hint
    record["profile_reason"] = profile.profile_reason
    if profile.is_deferred and record.get("status") == "active":
        record["status"] = "deferred"
        record["deferred_reason"] = profile.profile_reason


def profile_label(record: dict[str, Any]) -> str:
    profile = classify_record(record)
    paper_id = str(record.get("paper_id") or "?")
    return f"{paper_id} ({profile.processing_profile}, {profile.profile_reason})"
