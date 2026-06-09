from __future__ import annotations

import re
import unicodedata


def _ascii_fold(value: str) -> str:
    """Fold accents to ASCII (Müller -> Muller) so accented names key the same."""
    decomposed = unicodedata.normalize("NFD", value)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _parts(name: str) -> tuple[str, str]:
    """Return (family, given) from 'Family, Given' or 'Given Family'."""
    name = re.sub(r"\s+", " ", name).strip()
    if not name:
        return "", ""
    if "," in name:
        family, _, given = name.partition(",")
        return family.strip(), given.strip()
    tokens = name.split(" ")
    if len(tokens) == 1:
        return tokens[0], ""
    return tokens[-1], " ".join(tokens[:-1])


def author_identity(name: str) -> str:
    """A coarse identity key: lowercased family name + first given initial.

    Coarse on purpose — it merges 'Smith, John' / 'J Smith' / 'Smith, J.'.
    Accents are folded (Müller -> muller). A stronger key (ORCID/OpenAlex id)
    is preferred when available; this is the name-only fallback. Known limits:
    it cannot tell two distinct 'Smith, J' apart, and a comma-less East-Asian
    name written family-first (e.g. 'Wang Li') is read as given-first. Returns
    "" for an empty/blank name.
    """
    family, given = _parts(name)
    family_key = re.sub(r"[^a-z]", "", _ascii_fold(family).lower())
    if not family_key:
        return ""
    initial = ""
    given = given.strip()
    if given:
        first_alpha = re.sub(r"[^a-z]", "", _ascii_fold(given).lower())
        initial = first_alpha[:1]
    return f"{family_key}_{initial}" if initial else family_key


def anchor_author(authors: list[str]) -> str:
    """The senior author used as the group anchor. Default: the last author."""
    return authors[-1] if authors else ""
