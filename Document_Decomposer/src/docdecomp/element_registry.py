"""Element registry: canonical entries + aliases + append-only log.

Entries are append-only: IDs never change and are never reused; merge = redirect.
Human events (source=="human") are the durable curation layer (SP3 seed).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .io_utils import write_json

SCHEMA_VERSION = "0.1.0"


def slugify(name: str) -> str:
    s = "".join(ch.lower() if ch.isalnum() else "-" for ch in name.strip())
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "unnamed"


def element_id(facet: str, name: str) -> str:
    return f"elem:{facet}/{slugify(name)}"


def norm_key(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def load_seeds(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def new_registry_from_seeds(seeds: dict) -> dict:
    reg = {"schema_version": SCHEMA_VERSION, "facets": seeds["facets"], "entries": {}}
    for facet, families in (seeds.get("synonyms") or {}).items():
        for canonical, aliases in families.items():
            eid = element_id(facet, canonical)
            reg["entries"][eid] = {
                "id": eid,
                "facet": facet,
                "display_name": canonical,
                "aliases": [a for a in aliases if norm_key(a) != norm_key(canonical)],
                "redirect_to": None,
                "origin": "seed",
                "human_locked": False,
            }
    return reg


def load_registry(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_registry(path: Path, registry: dict) -> None:
    write_json(Path(path), registry)


def append_log(log_path: Path, event: dict) -> None:
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    event = {**event, "ts": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def create_entry(registry: dict, facet: str, display_name: str, origin: str, log_path: Path) -> str:
    eid = element_id(facet, display_name)
    n = 2
    while eid in registry["entries"]:
        eid = f"{element_id(facet, display_name)}-{n}"
        n += 1
    registry["entries"][eid] = {
        "id": eid,
        "facet": facet,
        "display_name": display_name,
        "aliases": [],
        "redirect_to": None,
        "origin": origin,
        "human_locked": False,
    }
    append_log(log_path, {"event": "create", "element_id": eid, "detail": display_name, "source": origin, "facet": facet})
    return eid


def add_alias(registry: dict, eid: str, alias: str, source: str, log_path: Path) -> None:
    entry = registry["entries"][eid]
    if norm_key(alias) == norm_key(entry["display_name"]):
        return
    if any(norm_key(alias) == norm_key(a) for a in entry["aliases"]):
        return
    entry["aliases"].append(alias)
    append_log(log_path, {"event": "alias", "element_id": eid, "detail": alias, "source": source})


def merge_entries(registry: dict, from_id: str, into_id: str, source: str, log_path: Path) -> None:
    if from_id not in registry["entries"]:
        raise ValueError(f"merge source unknown: {from_id}")
    if into_id not in registry["entries"]:
        raise ValueError(f"merge target unknown: {into_id}")
    into_id = resolve_id(registry, into_id)
    if from_id == into_id:
        raise ValueError(f"cannot merge an entry into itself: {from_id}")
    registry["entries"][from_id]["redirect_to"] = into_id
    if source == "human":
        registry["entries"][into_id]["human_locked"] = True
    append_log(log_path, {"event": "merge", "element_id": from_id, "detail": into_id, "source": source})


def resolve_id(registry: dict, eid: str) -> str:
    seen = set()
    while eid in registry["entries"] and registry["entries"][eid].get("redirect_to"):
        if eid in seen:
            break
        seen.add(eid)
        eid = registry["entries"][eid]["redirect_to"]
    return eid


def rename_entry(registry: dict, eid: str, display_name: str, log_path: Path) -> None:
    entry = registry["entries"][eid]
    if norm_key(display_name) == norm_key(entry["display_name"]):
        return
    old_name = entry["display_name"]
    # Archive old display_name as alias so it stays searchable.
    # Bypass the norm_key == display_name guard in add_alias (old_name IS the current display_name).
    if not any(norm_key(old_name) == norm_key(a) for a in entry["aliases"]):
        entry["aliases"].append(old_name)
        append_log(log_path, {"event": "alias", "element_id": eid, "detail": old_name, "source": "human"})
    entry["display_name"] = display_name
    entry["human_locked"] = True
    append_log(log_path, {"event": "rename", "element_id": eid, "detail": display_name, "source": "human"})


def find_by_surface(registry: dict, facet: str, surface: str) -> str | None:
    key = norm_key(surface)
    for eid, entry in registry["entries"].items():
        if entry["facet"] != facet:
            continue
        if key == norm_key(entry["display_name"]) or any(key == norm_key(a) for a in entry["aliases"]):
            return resolve_id(registry, eid)
    return None
