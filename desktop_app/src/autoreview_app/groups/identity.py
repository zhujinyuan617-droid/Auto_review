from __future__ import annotations

import re


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
    A stronger key (ORCID/OpenAlex id) would be preferred when available; this
    is the name-only fallback. Returns "" for an empty/blank name.
    """
    family, given = _parts(name)
    family_key = re.sub(r"[^a-z]", "", family.lower())
    if not family_key:
        return ""
    initial = ""
    given = given.strip()
    if given:
        first_alpha = re.sub(r"[^a-z]", "", given.lower())
        initial = first_alpha[:1]
    return f"{family_key}_{initial}" if initial else family_key


def anchor_author(authors: list[str]) -> str:
    """The senior author used as the group anchor. Default: the last author."""
    return authors[-1] if authors else ""
