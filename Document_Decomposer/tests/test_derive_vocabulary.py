"""Tests for src/docdecomp/derive_vocabulary.py.

Covers:
- redirected entries absent from output
- method facet union (preparation+measurement+simulation)
- raw_to_canonical lower-key mapping
- collision (same lower member → different canonicals): first-wins + warning
- card_count propagated
- model is "derived-from-registry"
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ENGINE_ROOT = Path(__file__).resolve().parents[1]
SRC = ENGINE_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from docdecomp.element_registry import (
    create_entry,
    load_seeds,
    merge_entries,
    new_registry_from_seeds,
    save_registry,
)
from docdecomp.derive_vocabulary import derive_vocabulary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seeds():
    return load_seeds(ENGINE_ROOT / "config" / "element_seeds.json")


def _make_base_registry(tmp_path: Path) -> tuple[dict, Path]:
    """Registry with one topic + one simulation + one material entry."""
    reg = new_registry_from_seeds(_seeds())
    log = tmp_path / "log.jsonl"
    create_entry(reg, "topic", "shale gas", "seed", log)
    create_entry(reg, "simulation", "GCMC", "seed", log)
    create_entry(reg, "material", "kerogen", "seed", log)
    return reg, log


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDeriveVocabulary:
    def test_metadata_fields(self, tmp_path):
        reg, _ = _make_base_registry(tmp_path)
        out = derive_vocabulary(reg, card_count=42)
        assert out["card_count"] == 42
        assert out["model"] == "derived-from-registry"
        assert "warnings" in out

    def test_output_facets_are_topic_method_object(self, tmp_path):
        reg, _ = _make_base_registry(tmp_path)
        out = derive_vocabulary(reg, card_count=10)
        assert set(out["facets"].keys()) == {"topic", "method", "object"}
        assert set(out["raw_to_canonical"].keys()) == {"topic", "method", "object"}

    def test_topic_entry_present(self, tmp_path):
        reg, _ = _make_base_registry(tmp_path)
        out = derive_vocabulary(reg, card_count=10)
        topic_canonicals = [c["canonical"] for c in out["facets"]["topic"]["concepts"]]
        assert "shale gas" in topic_canonicals

    def test_redirected_entry_absent(self, tmp_path):
        reg, log = _make_base_registry(tmp_path)
        # Add second topic entry and merge (redirect) it into the first
        eid_b = create_entry(reg, "topic", "shale gas extraction", "test", log)
        eid_a = next(
            eid for eid, e in reg["entries"].items()
            if e["facet"] == "topic" and e["display_name"] == "shale gas"
        )
        merge_entries(reg, eid_b, eid_a, "test", log)
        out = derive_vocabulary(reg, card_count=10)
        topic_canonicals = [c["canonical"] for c in out["facets"]["topic"]["concepts"]]
        # The redirected entry must NOT appear as its own concept
        assert "shale gas extraction" not in topic_canonicals

    def test_simulation_maps_to_method_facet(self, tmp_path):
        reg, _ = _make_base_registry(tmp_path)
        out = derive_vocabulary(reg, card_count=10)
        method_canonicals = [c["canonical"] for c in out["facets"]["method"]["concepts"]]
        assert "GCMC" in method_canonicals

    def test_material_maps_to_object_facet(self, tmp_path):
        reg, _ = _make_base_registry(tmp_path)
        out = derive_vocabulary(reg, card_count=10)
        obj_canonicals = [c["canonical"] for c in out["facets"]["object"]["concepts"]]
        assert "kerogen" in obj_canonicals

    def test_method_includes_preparation_and_measurement(self, tmp_path):
        reg, log = _make_base_registry(tmp_path)
        create_entry(reg, "preparation", "ball milling", "seed", log)
        create_entry(reg, "measurement", "gas adsorption isotherm", "seed", log)
        out = derive_vocabulary(reg, card_count=10)
        method_canonicals = [c["canonical"] for c in out["facets"]["method"]["concepts"]]
        assert "ball milling" in method_canonicals
        assert "gas adsorption isotherm" in method_canonicals

    def test_raw_to_canonical_lower_keys(self, tmp_path):
        reg, log = _make_base_registry(tmp_path)
        # "shale gas" has canonical "shale gas"; members is exactly [display_name] since no aliases
        out = derive_vocabulary(reg, card_count=10)
        r2c = out["raw_to_canonical"]["topic"]
        assert r2c.get("shale gas") == "shale gas"

    def test_alias_member_in_raw_to_canonical(self, tmp_path):
        reg, log = _make_base_registry(tmp_path)
        from docdecomp.element_registry import add_alias
        eid = next(
            eid for eid, e in reg["entries"].items()
            if e["facet"] == "topic" and e["display_name"] == "shale gas"
        )
        add_alias(reg, eid, "Deep Shale Gas", "test", log)
        out = derive_vocabulary(reg, card_count=10)
        r2c = out["raw_to_canonical"]["topic"]
        # Member lower-cased key must map to canonical
        assert r2c.get("deep shale gas") == "shale gas"

    def test_concepts_sorted_alphabetically(self, tmp_path):
        reg, log = _make_base_registry(tmp_path)
        # Add two more topics so we can check order
        create_entry(reg, "topic", "adsorption", "seed", log)
        create_entry(reg, "topic", "nanopore", "seed", log)
        out = derive_vocabulary(reg, card_count=10)
        canonicals = [c["canonical"] for c in out["facets"]["topic"]["concepts"]]
        assert canonicals == sorted(canonicals)

    def test_members_are_sorted_set(self, tmp_path):
        reg, log = _make_base_registry(tmp_path)
        from docdecomp.element_registry import add_alias
        eid = next(
            eid for eid, e in reg["entries"].items()
            if e["facet"] == "topic" and e["display_name"] == "shale gas"
        )
        add_alias(reg, eid, "Deep shale", "test", log)
        add_alias(reg, eid, "shale gas extraction", "test", log)
        out = derive_vocabulary(reg, card_count=10)
        topic_concepts = {c["canonical"]: c for c in out["facets"]["topic"]["concepts"]}
        members = topic_concepts["shale gas"]["members"]
        assert members == sorted(members)

    def test_collision_first_wins_and_warning_emitted(self, tmp_path):
        """Two entries with the same alias lower-key → first (sorted by canonical) wins."""
        reg, log = _make_base_registry(tmp_path)
        from docdecomp.element_registry import add_alias
        # Create two topic entries that share a lower-cased alias
        eid_a = create_entry(reg, "topic", "alpha topic", "test", log)
        eid_b = create_entry(reg, "topic", "beta topic", "test", log)
        add_alias(reg, eid_a, "shared alias", "test", log)
        add_alias(reg, eid_b, "Shared Alias", "test", log)  # same lower-key
        out = derive_vocabulary(reg, card_count=10)
        r2c = out["raw_to_canonical"]["topic"]
        # First in sorted canonical order wins
        assert r2c.get("shared alias") == "alpha topic"
        # A warning must be emitted
        assert len(out["warnings"]) >= 1
        assert any("shared alias" in w.lower() for w in out["warnings"])

    def test_empty_registry_produces_empty_facets(self, tmp_path):
        """A registry with zero entries (no seeds, no entries) gives empty facets."""
        from docdecomp.element_registry import SCHEMA_VERSION
        reg = {"schema_version": SCHEMA_VERSION, "facets": {}, "entries": {}}
        out = derive_vocabulary(reg, card_count=0)
        assert out["facets"]["topic"]["concepts"] == []
        assert out["facets"]["method"]["concepts"] == []
        assert out["facets"]["object"]["concepts"] == []
        assert out["warnings"] == []
