import json
from pathlib import Path

import pytest

from docdecomp.element_registry import (
    add_alias,
    create_entry,
    element_id,
    find_by_surface,
    load_registry,
    load_seeds,
    merge_entries,
    new_registry_from_seeds,
    norm_key,
    rename_entry,
    resolve_id,
    save_registry,
    slugify,
)

ENGINE_ROOT = Path(__file__).resolve().parents[1]


def _seeds():
    return load_seeds(ENGINE_ROOT / "config" / "element_seeds.json")


def test_slug_and_id():
    assert slugify("Grand canonical Monte Carlo!") == "grand-canonical-monte-carlo"
    assert element_id("simulation", "GCMC method") == "elem:simulation/gcmc-method"


def test_seeds_load_and_registry_init():
    seeds = _seeds()
    assert {f["id"] for f in seeds["facets"]} >= {"preparation", "characterization", "condition"}
    reg = new_registry_from_seeds(seeds)
    eid = "elem:characterization/x-ray-diffraction"
    assert eid in reg["entries"]
    assert "XRD" in reg["entries"][eid]["aliases"]
    assert reg["entries"][eid]["origin"] == "seed"


def test_find_by_surface_matches_display_and_alias_normalized():
    reg = new_registry_from_seeds(_seeds())
    eid = "elem:characterization/x-ray-diffraction"
    assert find_by_surface(reg, "characterization", "xrd") == eid
    assert find_by_surface(reg, "characterization", "X-ray  Diffraction") == eid
    assert find_by_surface(reg, "characterization", "neutron scattering") is None


def test_create_alias_merge_resolve_and_log(tmp_path: Path):
    log = tmp_path / "registry_log.jsonl"
    reg = new_registry_from_seeds(_seeds())
    a = create_entry(reg, "preparation", "acid washing", "auto-stream", log)
    b = create_entry(reg, "preparation", "acid treatment", "auto-stream", log)
    add_alias(reg, a, "HCl washing", "auto-stream", log)
    assert find_by_surface(reg, "preparation", "hcl washing") == a
    merge_entries(reg, b, a, "human", log)
    assert reg["entries"][b]["redirect_to"] == a
    assert resolve_id(reg, b) == a
    rename_entry(reg, a, "acid washing treatment", log)
    assert reg["entries"][a]["display_name"] == "acid washing treatment"
    assert reg["entries"][a]["human_locked"] is True
    events = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert [e["event"] for e in events] == ["create", "create", "alias", "merge", "alias", "rename"]


def test_create_entry_id_collision_gets_suffix(tmp_path: Path):
    log = tmp_path / "log.jsonl"
    reg = new_registry_from_seeds(_seeds())
    a = create_entry(reg, "material", "kerogen", "bootstrap", log)
    b = create_entry(reg, "material", "Kerogen", "bootstrap", log)
    assert a == "elem:material/kerogen"
    assert b == "elem:material/kerogen-2"


def test_save_and_load_roundtrip(tmp_path: Path):
    reg = new_registry_from_seeds(_seeds())
    p = tmp_path / "registry.json"
    save_registry(p, reg)
    assert load_registry(p) == reg


def test_norm_key():
    assert norm_key("  Ball-Milling ") == norm_key("ball milling")


def test_merge_guards_and_target_resolution(tmp_path: Path):
    log = tmp_path / "log.jsonl"
    reg = new_registry_from_seeds(_seeds())
    a = create_entry(reg, "material", "kerogen", "bootstrap", log)
    b = create_entry(reg, "material", "type II kerogen", "bootstrap", log)
    c = create_entry(reg, "material", "kerogen II-D", "bootstrap", log)
    with pytest.raises(ValueError):
        merge_entries(reg, a, "elem:material/ghost", "human", log)
    with pytest.raises(ValueError):
        merge_entries(reg, a, a, "human", log)
    merge_entries(reg, b, a, "human", log)
    merge_entries(reg, c, b, "human", log)  # target b is redirected -> must attach to a
    assert reg["entries"][c]["redirect_to"] == a
    assert resolve_id(reg, c) == a


def test_rename_to_same_name_is_noop(tmp_path: Path):
    log = tmp_path / "log.jsonl"
    reg = new_registry_from_seeds(_seeds())
    a = create_entry(reg, "preparation", "acid washing", "bootstrap", log)
    before_events = len(log.read_text(encoding="utf-8").splitlines())
    rename_entry(reg, a, "Acid  Washing", log)  # same name modulo norm_key
    assert reg["entries"][a]["aliases"] == []
    assert reg["entries"][a]["display_name"] == "acid washing"
    assert len(log.read_text(encoding="utf-8").splitlines()) == before_events


def test_seed_aliases_deduped_against_canonical():
    reg = new_registry_from_seeds(_seeds())
    bm = reg["entries"]["elem:preparation/ball-milling"]
    assert "ball-milling" not in bm["aliases"]  # norm_key-equal to display name
    assert "mechanical milling" in bm["aliases"]


def test_create_event_carries_facet(tmp_path: Path):
    log = tmp_path / "log.jsonl"
    reg = new_registry_from_seeds(_seeds())
    create_entry(reg, "analysis", "tortuosity analysis", "bootstrap", log)
    event = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert event["event"] == "create" and event["facet"] == "analysis"
