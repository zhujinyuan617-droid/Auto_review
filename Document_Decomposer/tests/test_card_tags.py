"""Tests for card_tags: mechanical tag derivation from extracted elements (zero AI).

Covers:
- derive_classification: used-role only, canonical_id required, top_n truncation,
  tie-break alphabetical.
- apply_derived_tags: writes research_objects + methods through to card.
- derive_topic_ids: case-insensitive surface match, unresolved tags skipped,
  duplicates deduplicated.
- resolve_topics_bulk: library-wide domain_tags → registry topic entries, AI path,
  no-client path, idempotency.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from docdecomp.card_tags import (
    apply_derived_tags,
    derive_classification,
    derive_topic_ids,
    resolve_topics_bulk,
)
from docdecomp.element_registry import (
    create_entry,
    element_id,
    find_by_surface,
    load_seeds,
    new_registry_from_seeds,
    save_registry,
)
from docdecomp.io_utils import write_json

# Pull in the fake client
_TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_TESTS_DIR))
from _fake_ai import SequencedFakeClient

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
        result = derive_classification(elements_doc, reg, top_objects=3)
        assert len(result["research_objects"]) == 3

    def test_finding_protagonist_never_truncated(self, tmp_path):
        # 审计 S43:propane 是"选择性序"发现的主角,却被 top-5 字典序截掉。
        reg = _make_registry(tmp_path)
        log = tmp_path / "log.jsonl"
        names = ["aaa-gas", "bbb-gas", "ccc-gas", "ddd-gas", "eee-gas", "propane"]
        ids = [create_entry(reg, "material", n, "test", log) for n in names]
        occs = [_occ(eid) for eid in ids]
        occs.append({"facet": "finding", "surface": "selectivity order: propane > ethane > methane",
                     "quote": "q", "reading_block_id": "S43-RB-0001", "role": "used",
                     "quote_verified": True, "digits_verified": False, "values": [],
                     "canonical_id": None})
        result = derive_classification({"occurrences": occs}, reg, top_objects=3)
        assert "propane" in result["research_objects"]       # 主角保席
        assert result["research_objects"][0] == "propane"    # 且排最前

    def test_seed_method_beats_auto_component_on_tie(self, tmp_path):
        # 审计 S307:平票字典序让 'Darkrim' 组件挤掉 GCMC;种子条目应优先。
        reg = _make_registry(tmp_path)
        log = tmp_path / "log.jsonl"
        comp = create_entry(reg, "simulation", "Aardvark thermostat", "auto-bulk", log)
        seed = create_entry(reg, "simulation", "zz-grand canonical monte carlo", "test", log)
        reg["entries"][seed]["origin"] = "seed"
        occs = [_occ(comp), _occ(seed)]
        result = derive_classification({"occurrences": occs}, reg, top_methods=2)
        assert result["methods"][0] == "zz-grand canonical monte carlo"

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


# ---------------------------------------------------------------------------
# Helpers for resolve_topics_bulk tests
# ---------------------------------------------------------------------------

def _make_library(tmp_path: Path, cards: list[dict]) -> Path:
    """Create a minimal library dir with numbered paper subdirs each containing
    a literature_card.json.
    """
    lib = tmp_path / "library"
    lib.mkdir()
    for i, card in enumerate(cards):
        paper_dir = lib / f"P{i+1:02d}"
        paper_dir.mkdir()
        write_json(paper_dir / "literature_card.json", card)
    return lib


def _make_registry_file(tmp_path: Path, reg: dict) -> Path:
    """Write registry.json to a data-dir and return data-dir."""
    data_dir = tmp_path / "data_elements"
    data_dir.mkdir(exist_ok=True)
    reg_path = data_dir / "registry.json"
    save_registry(reg_path, reg)
    return reg_path


# ---------------------------------------------------------------------------
# resolve_topics_bulk
# ---------------------------------------------------------------------------

class TestResolveTopicsBulk:
    def test_exact_match_no_ai(self, tmp_path):
        """Tag already in registry → resolved_exact, card updated, no AI calls."""
        reg = new_registry_from_seeds(_seeds())
        log_tmp = tmp_path / "log.jsonl"
        eid = create_entry(reg, "topic", "shale gas", "seed", log_tmp)

        cards = [{"classification": {"domain_tags": ["shale gas"]}}]
        lib = _make_library(tmp_path, cards)
        reg_path = _make_registry_file(tmp_path, reg)
        log_path = tmp_path / "registry_log.jsonl"

        stats = resolve_topics_bulk(lib, reg_path, log_path, client=None)
        assert stats["resolved_exact"] == 1
        assert stats["created"] == 0
        assert stats["cards_updated"] == 1
        assert stats["ai_calls"] == 0

        card_data = json.loads((lib / "P01" / "literature_card.json").read_text(encoding="utf-8"))
        assert eid in card_data["classification"]["topic_ids"]

    def test_unresolved_no_client_creates_entry(self, tmp_path):
        """Tag NOT in registry, client=None → create_entry with origin auto-stream."""
        reg = new_registry_from_seeds(_seeds())

        cards = [{"classification": {"domain_tags": ["unknown novel tag"]}}]
        lib = _make_library(tmp_path, cards)
        reg_path = _make_registry_file(tmp_path, reg)
        log_path = tmp_path / "registry_log.jsonl"

        stats = resolve_topics_bulk(lib, reg_path, log_path, client=None)
        assert stats["created"] == 1
        assert stats["resolved_exact"] == 0
        assert stats["cards_updated"] == 1

        # Card must have topic_ids
        card_data = json.loads((lib / "P01" / "literature_card.json").read_text(encoding="utf-8"))
        assert len(card_data["classification"]["topic_ids"]) == 1

    def test_ai_maps_surface_to_existing_entry(self, tmp_path):
        """AI maps unresolved surface to existing entry → resolved_ai, alias added."""
        reg = new_registry_from_seeds(_seeds())
        log_tmp = tmp_path / "log.jsonl"
        eid = create_entry(reg, "topic", "shale gas", "seed", log_tmp)

        cards = [{"classification": {"domain_tags": ["shale gas extraction"]}}]
        lib = _make_library(tmp_path, cards)
        reg_path = _make_registry_file(tmp_path, reg)
        log_path = tmp_path / "registry_log.jsonl"

        fake_client = SequencedFakeClient([
            {"matches": [{"surface": "shale gas extraction", "element_id": eid}]}
        ])

        stats = resolve_topics_bulk(lib, reg_path, log_path, client=fake_client)
        assert stats["resolved_ai"] == 1
        assert stats["ai_calls"] == 1
        assert stats["created"] == 0
        assert stats["cards_updated"] == 1

        card_data = json.loads((lib / "P01" / "literature_card.json").read_text(encoding="utf-8"))
        assert eid in card_data["classification"]["topic_ids"]

    def test_ai_null_response_creates_entry(self, tmp_path):
        """AI returns null for surface → create_entry (origin='auto-stream')."""
        reg = new_registry_from_seeds(_seeds())

        cards = [{"classification": {"domain_tags": ["truly new concept"]}}]
        lib = _make_library(tmp_path, cards)
        reg_path = _make_registry_file(tmp_path, reg)
        log_path = tmp_path / "registry_log.jsonl"

        fake_client = SequencedFakeClient([
            {"matches": [{"surface": "truly new concept", "element_id": None}]}
        ])

        stats = resolve_topics_bulk(lib, reg_path, log_path, client=fake_client)
        assert stats["created"] == 1
        assert stats["ai_calls"] == 1
        assert stats["cards_updated"] == 1

    def test_two_cards_one_existing_one_new(self, tmp_path):
        """Two cards: one tag known, one unknown (no client). Both get topic_ids."""
        reg = new_registry_from_seeds(_seeds())
        log_tmp = tmp_path / "log.jsonl"
        eid = create_entry(reg, "topic", "shale gas", "seed", log_tmp)

        cards = [
            {"classification": {"domain_tags": ["shale gas"]}},
            {"classification": {"domain_tags": ["clay minerals"]}},
        ]
        lib = _make_library(tmp_path, cards)
        reg_path = _make_registry_file(tmp_path, reg)
        log_path = tmp_path / "registry_log.jsonl"

        stats = resolve_topics_bulk(lib, reg_path, log_path, client=None)
        assert stats["resolved_exact"] == 1
        assert stats["created"] == 1
        assert stats["cards_updated"] == 2

    def test_idempotent_second_run(self, tmp_path):
        """Running twice: second run all exact, ai_calls=0, cards_updated=0."""
        reg = new_registry_from_seeds(_seeds())

        cards = [{"classification": {"domain_tags": ["shale gas"]}}]
        lib = _make_library(tmp_path, cards)
        reg_path = _make_registry_file(tmp_path, reg)
        log_path = tmp_path / "registry_log.jsonl"

        # First run
        resolve_topics_bulk(lib, reg_path, log_path, client=None)
        # Second run
        stats2 = resolve_topics_bulk(lib, reg_path, log_path, client=None)
        assert stats2["resolved_exact"] >= 1
        assert stats2["ai_calls"] == 0
        assert stats2["cards_updated"] == 0

    def test_deduplicates_domain_tags(self, tmp_path):
        """Same tag appearing twice in a card's domain_tags → topic_ids deduped."""
        reg = new_registry_from_seeds(_seeds())
        log_tmp = tmp_path / "log.jsonl"
        eid = create_entry(reg, "topic", "shale gas", "seed", log_tmp)

        cards = [{"classification": {"domain_tags": ["shale gas", "shale gas"]}}]
        lib = _make_library(tmp_path, cards)
        reg_path = _make_registry_file(tmp_path, reg)
        log_path = tmp_path / "registry_log.jsonl"

        stats = resolve_topics_bulk(lib, reg_path, log_path, client=None)
        card_data = json.loads((lib / "P01" / "literature_card.json").read_text(encoding="utf-8"))
        topic_ids = card_data["classification"]["topic_ids"]
        assert topic_ids.count(eid) == 1

    def test_card_without_domain_tags_not_updated(self, tmp_path):
        """Card with no domain_tags key → topic_ids set to [] but card unchanged if already empty."""
        reg = new_registry_from_seeds(_seeds())

        cards = [{"classification": {}}]  # no domain_tags
        lib = _make_library(tmp_path, cards)
        reg_path = _make_registry_file(tmp_path, reg)
        log_path = tmp_path / "registry_log.jsonl"

        stats = resolve_topics_bulk(lib, reg_path, log_path, client=None)
        # No changes needed; cards_updated should be 0
        assert stats["cards_updated"] == 0

    def test_returns_all_counter_keys(self, tmp_path):
        """Return dict has all required keys."""
        reg = new_registry_from_seeds(_seeds())
        lib = _make_library(tmp_path, [])
        reg_path = _make_registry_file(tmp_path, reg)
        log_path = tmp_path / "registry_log.jsonl"

        stats = resolve_topics_bulk(lib, reg_path, log_path, client=None)
        for key in ("tags_total", "resolved_exact", "resolved_ai", "created", "cards_updated", "ai_calls"):
            assert key in stats, f"missing key: {key}"
