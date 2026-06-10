"""Tests for card_tags: mechanical tag derivation from extracted elements (zero AI).

Covers:
- derive_classification: used-role only, canonical_id required, top_n truncation,
  tie-break alphabetical.
- apply_derived_tags: writes research_objects + methods through to card.
- derive_topic_ids: case-insensitive surface match, unresolved tags skipped,
  duplicates deduplicated.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from docdecomp.card_tags import apply_derived_tags, derive_classification, derive_topic_ids
from docdecomp.element_registry import (
    create_entry,
    element_id,
    find_by_surface,
    load_seeds,
    new_registry_from_seeds,
)

ENGINE_ROOT = Path(__file__).resolve().parents[1]


def _seeds():
    return load_seeds(ENGINE_ROOT / "config" / "element_seeds.json")


# ---------------------------------------------------------------------------
# Registry helpers: build a minimal registry with known entries
# ---------------------------------------------------------------------------

def _make_registry(tmp_path: Path) -> dict:
    """Registry with a few material + method entries; no topic entries."""
    reg = new_registry_from_seeds(_seeds())
    log = tmp_path / "log.jsonl"
    # Materials
    reg["_mat_a"] = create_entry(reg, "material", "kerogen", "test", log)
    reg["_mat_b"] = create_entry(reg, "material", "montmorillonite", "test", log)
    # Methods (spanning the three method facets)
    reg["_sim"] = create_entry(reg, "simulation", "GCMC", "test", log)
    reg["_prep"] = create_entry(reg, "preparation", "ball milling", "test", log)
    reg["_meas"] = create_entry(reg, "measurement", "gas adsorption isotherm", "test", log)
    return reg


def _occ(canonical_id: str, role: str = "used") -> dict:
    return {
        "canonical_id": canonical_id,
        "role": role,
        "surface": "any",
        "facet": "any",
    }


# ---------------------------------------------------------------------------
# derive_classification
# ---------------------------------------------------------------------------

class TestDeriveClassification:
    def test_used_role_counted_material_and_methods(self, tmp_path):
        reg = _make_registry(tmp_path)
        mat_a = reg["_mat_a"]
        sim = reg["_sim"]
        elements_doc = {
            "occurrences": [
                _occ(mat_a),
                _occ(mat_a),
                _occ(sim),
            ]
        }
        result = derive_classification(elements_doc, reg)
        assert result["research_objects"] == ["kerogen"]
        assert result["methods"] == ["GCMC"]

    def test_mentioned_role_ignored(self, tmp_path):
        reg = _make_registry(tmp_path)
        mat_a = reg["_mat_a"]
        elements_doc = {
            "occurrences": [
                _occ(mat_a, role="mentioned"),
                _occ(mat_a, role="mentioned"),
            ]
        }
        result = derive_classification(elements_doc, reg)
        assert result["research_objects"] == []

    def test_none_canonical_id_skipped(self, tmp_path):
        reg = _make_registry(tmp_path)
        elements_doc = {
            "occurrences": [
                {"canonical_id": None, "role": "used", "surface": "x", "facet": "material"},
            ]
        }
        result = derive_classification(elements_doc, reg)
        assert result["research_objects"] == []

    def test_top_n_truncation(self, tmp_path):
        reg = _make_registry(tmp_path)
        log = tmp_path / "log.jsonl"
        # Create 4 extra materials so we have 5 total materials in the doc
        ids = [reg["_mat_a"], reg["_mat_b"]]
        for name in ["illite", "kaolinite", "quartz"]:
            ids.append(create_entry(reg, "material", name, "test", log))
        # Each material appears once → alphabetical tie-break applies
        occs = [_occ(eid) for eid in ids]
        elements_doc = {"occurrences": occs}
        result = derive_classification(elements_doc, reg, top_n=3)
        assert len(result["research_objects"]) == 3

    def test_count_descending_order(self, tmp_path):
        reg = _make_registry(tmp_path)
        mat_a = reg["_mat_a"]   # kerogen
        mat_b = reg["_mat_b"]   # montmorillonite
        elements_doc = {
            "occurrences": [
                _occ(mat_a),
                _occ(mat_a),
                _occ(mat_a),
                _occ(mat_b),
            ]
        }
        result = derive_classification(elements_doc, reg)
        assert result["research_objects"][0] == "kerogen"

    def test_tie_alphabetical(self, tmp_path):
        reg = _make_registry(tmp_path)
        log = tmp_path / "log.jsonl"
        id_alpha = create_entry(reg, "material", "alpha material", "test", log)
        id_beta = create_entry(reg, "material", "beta material", "test", log)
        elements_doc = {
            "occurrences": [_occ(id_alpha), _occ(id_beta)]
        }
        result = derive_classification(elements_doc, reg)
        objs = result["research_objects"]
        assert objs.index("alpha material") < objs.index("beta material")

    def test_all_three_method_facets_aggregated(self, tmp_path):
        reg = _make_registry(tmp_path)
        sim = reg["_sim"]
        prep = reg["_prep"]
        meas = reg["_meas"]
        elements_doc = {
            "occurrences": [_occ(sim), _occ(prep), _occ(meas)]
        }
        result = derive_classification(elements_doc, reg)
        assert set(result["methods"]) == {"GCMC", "ball milling", "gas adsorption isotherm"}

    def test_empty_occurrences(self, tmp_path):
        reg = _make_registry(tmp_path)
        result = derive_classification({"occurrences": []}, reg)
        assert result == {"research_objects": [], "methods": []}

    def test_missing_occurrences_key(self, tmp_path):
        reg = _make_registry(tmp_path)
        result = derive_classification({}, reg)
        assert result == {"research_objects": [], "methods": []}


# ---------------------------------------------------------------------------
# apply_derived_tags
# ---------------------------------------------------------------------------

class TestApplyDerivedTags:
    def test_writes_research_objects_and_methods(self):
        card = {"classification": {"domain_tags": ["shale"]}}
        derived = {"research_objects": ["kerogen"], "methods": ["GCMC"]}
        apply_derived_tags(card, derived)
        cls = card["classification"]
        assert cls["research_objects"] == ["kerogen"]
        assert cls["methods"] == ["GCMC"]
        assert cls["domain_tags"] == ["shale"]  # untouched

    def test_creates_classification_if_absent(self):
        card = {}
        derived = {"research_objects": ["clay"], "methods": []}
        apply_derived_tags(card, derived)
        assert card["classification"]["research_objects"] == ["clay"]
        assert card["classification"]["methods"] == []

    def test_overwrites_existing_values(self):
        card = {"classification": {"research_objects": ["old"], "methods": ["old_m"]}}
        derived = {"research_objects": ["new"], "methods": ["new_m"]}
        apply_derived_tags(card, derived)
        assert card["classification"]["research_objects"] == ["new"]
        assert card["classification"]["methods"] == ["new_m"]

    def test_returns_card(self):
        card = {}
        result = apply_derived_tags(card, {})
        assert result is card


# ---------------------------------------------------------------------------
# derive_topic_ids
# ---------------------------------------------------------------------------

class TestDeriveTopicIds:
    def _registry_with_topic(self, tmp_path: Path, display_name: str) -> dict:
        reg = new_registry_from_seeds(_seeds())
        log = tmp_path / "log.jsonl"
        create_entry(reg, "topic", display_name, "seed", log)
        return reg

    def test_exact_case_insensitive_hit(self, tmp_path):
        reg = self._registry_with_topic(tmp_path, "shale gas")
        expected_id = element_id("topic", "shale gas")
        card = {"classification": {"domain_tags": ["Shale Gas"]}}
        ids = derive_topic_ids(card, reg)
        assert ids == [expected_id]

    def test_unknown_tag_skipped(self, tmp_path):
        reg = self._registry_with_topic(tmp_path, "shale gas")
        card = {"classification": {"domain_tags": ["Shale Gas", "unknown topic xyz"]}}
        ids = derive_topic_ids(card, reg)
        assert len(ids) == 1
        assert element_id("topic", "shale gas") in ids

    def test_deduplicate_same_resolution(self, tmp_path):
        reg = self._registry_with_topic(tmp_path, "shale gas")
        expected_id = element_id("topic", "shale gas")
        # Two different surface forms that both resolve to same id
        from docdecomp.element_registry import add_alias
        log = tmp_path / "log.jsonl"
        add_alias(reg, expected_id, "shale gas reservoir", "test", log)
        card = {"classification": {"domain_tags": ["Shale Gas", "shale gas reservoir"]}}
        ids = derive_topic_ids(card, reg)
        assert ids.count(expected_id) == 1

    def test_empty_domain_tags_returns_empty(self, tmp_path):
        reg = self._registry_with_topic(tmp_path, "shale gas")
        card = {"classification": {"domain_tags": []}}
        assert derive_topic_ids(card, reg) == []

    def test_no_classification_returns_empty(self, tmp_path):
        reg = self._registry_with_topic(tmp_path, "shale gas")
        assert derive_topic_ids({}, reg) == []

    def test_preserves_order(self, tmp_path):
        reg = new_registry_from_seeds(_seeds())
        log = tmp_path / "log.jsonl"
        id_a = create_entry(reg, "topic", "adsorption", "seed", log)
        id_b = create_entry(reg, "topic", "nanopore", "seed", log)
        card = {"classification": {"domain_tags": ["adsorption", "nanopore"]}}
        ids = derive_topic_ids(card, reg)
        assert ids == [id_a, id_b]
