"""OpenAlex authorship source: DOI -> authors with institutions (stateless, transport-injected)."""
from __future__ import annotations

from typing import Any

from ..transport import Transport

OPENALEX_WORKS_URL = "https://api.openalex.org/works/doi:{doi}"


class OpenAlexSource:
    def fetch_authorship(self, doi: str, transport: Transport) -> dict[str, Any] | None:
        data = transport.get_json(OPENALEX_WORKS_URL.format(doi=doi.strip().lower()), {})
        authorships = data.get("authorships") or []
        if not authorships:
            return None
        authors = []
        for i, a in enumerate(authorships):
            if not isinstance(a, dict):
                continue
            name = ((a.get("author") or {}).get("display_name") or "").strip()
            insts = [str(inst.get("display_name") or "").strip()
                     for inst in (a.get("institutions") or [])
                     if isinstance(inst, dict) and inst.get("display_name")]
            authors.append({"name": name, "position": i + 1,
                            "is_senior": i == len(authorships) - 1,
                            "raw_affiliations": insts})
        return {"authors": authors, "source": "openalex"}
