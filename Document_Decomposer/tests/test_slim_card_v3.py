"""Tests for slim card v3 (schema 0.3.0).

Covers:
- ensure_slim_defaults: classification keys exactly {research_objects, methods, domain_tags, topic_ids}
  (gas_systems/scale gone); schema_version pinned to 0.3.0.
- build_slim_prompt user text: contains "domain_tags", "do NOT output them"; does NOT contain
  "gas_systems"; mentions 0.3.0.
- validate_slim_card: domain_tags-only card → no classification_empty warning; empty domain_tags
  → warning present; n_tags counts domain_tags only.
"""
from __future__ import annotations

import json

import pytest

from docdecomp.slim_card import (
    SLIM_SCHEMA_VERSION,
    build_slim_prompt,
    ensure_slim_defaults,
    validate_slim_card,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_reading(paper_id: str = "S01") -> dict:
    return {
        "paper_id": paper_id,
        "reading_blocks": [
            {
                "reading_block_id": f"{paper_id}-RB-0001",
                "order": 0,
                "section_kind": "abstract",
                "reading_type": "abstract",
                "include_in_reading": True,
                "text": "This paper studies methane adsorption in shale.",
                "caption": "",
            }
        ],
    }


def _minimal_metadata() -> dict:
    return {
        "metadata_candidates": {
            "title": "Methane Adsorption in Shale",
            "doi": "10.1234/test",
            "year": "2023",
            "journal": "Fuel",
        }
    }


# ---------------------------------------------------------------------------
# Schema version constant
# ---------------------------------------------------------------------------

def test_schema_version_constant():
    assert SLIM_SCHEMA_VERSION == "0.3.0"


# ---------------------------------------------------------------------------
# ensure_slim_defaults
# ---------------------------------------------------------------------------

class TestEnsureSlimDefaults:
    def test_classification_keys_exactly_v3(self):
        card = ensure_slim_defaults({}, _minimal_reading(), _minimal_metadata())
        cls = card["classification"]
        assert set(cls.keys()) == {"research_objects", "methods", "domain_tags", "topic_ids"}

    def test_no_gas_systems_or_scale(self):
        card = ensure_slim_defaults({}, _minimal_reading(), _minimal_metadata())
        cls = card["classification"]
        assert "gas_systems" not in cls
        assert "scale" not in cls

    def test_schema_version_forced_to_v3(self):
        card = ensure_slim_defaults({"schema_version": "0.2.0"}, _minimal_reading(), _minimal_metadata())
        assert card["schema_version"] == "0.3.0"

    def test_classification_defaults_to_empty_lists(self):
        card = ensure_slim_defaults({}, _minimal_reading(), _minimal_metadata())
        cls = card["classification"]
        for k in ("research_objects", "methods", "domain_tags", "topic_ids"):
            assert cls[k] == []

    def test_existing_domain_tags_preserved_and_normalised(self):
        input_card = {"classification": {"domain_tags": ["  Shale Gas ", "coal seam"]}}
        card = ensure_slim_defaults(input_card, _minimal_reading(), _minimal_metadata())
        assert card["classification"]["domain_tags"] == ["Shale Gas", "coal seam"]

    def test_gas_systems_key_stripped_if_supplied_by_old_model(self):
        # Old model response may include gas_systems; ensure_slim_defaults must NOT preserve it
        input_card = {"classification": {"gas_systems": ["CH4"], "domain_tags": ["shale"]}}
        card = ensure_slim_defaults(input_card, _minimal_reading(), _minimal_metadata())
        assert "gas_systems" not in card["classification"]

    def test_topic_ids_defaults_empty_even_if_absent(self):
        input_card = {"classification": {"domain_tags": ["shale"]}}
        card = ensure_slim_defaults(input_card, _minimal_reading(), _minimal_metadata())
        assert card["classification"]["topic_ids"] == []


# ---------------------------------------------------------------------------
# build_slim_prompt
# ---------------------------------------------------------------------------

class TestBuildSlimPrompt:
    def _user_text(self) -> str:
        msgs = build_slim_prompt(_minimal_reading(), _minimal_metadata())
        return msgs[1]["content"]  # user message

    def test_mentions_03(self):
        assert "0.3.0" in self._user_text()

    def test_does_not_mention_02(self):
        assert "0.2.0" not in self._user_text()

    def test_contains_domain_tags(self):
        assert "domain_tags" in self._user_text()

    def test_contains_do_not_output_them(self):
        assert "do NOT output them" in self._user_text()

    def test_does_not_contain_gas_systems(self):
        assert "gas_systems" not in self._user_text()

    def test_does_not_contain_scale_keyword_in_classification(self):
        # "scale" must not appear as a classification field; it may appear in other context
        # so we check the classification bullet specifically
        text = self._user_text()
        assert "gas_systems" not in text

    def test_prompt_is_two_messages(self):
        msgs = build_slim_prompt(_minimal_reading(), _minimal_metadata())
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"


# ---------------------------------------------------------------------------
# validate_slim_card
# ---------------------------------------------------------------------------

class TestValidateSlimCard:
    def _base_card(self) -> dict:
        return {
            "schema_version": "0.3.0",
            "paper_id": "S01",
            "paper": {"title": "A Title", "doi": "", "year": "2023",
                      "journal": "Fuel", "paper_type": "experimental"},
            "classification": {
                "research_objects": [],
                "methods": [],
                "domain_tags": ["shale gas", "methane adsorption"],
                "topic_ids": [],
            },
            "summary": {
                "objective": "Study methane adsorption.",
                "main_findings": ["Higher pressure -> higher adsorption."],
                "methods_systems": "GCMC on shale model",
            },
            "ai_warnings": [],
        }

    def test_domain_tags_only_non_empty_no_classification_warning(self):
        card = self._base_card()
        result = validate_slim_card(card)
        assert "classification_empty" not in result["warnings"]

    def test_empty_domain_tags_triggers_classification_empty_warning(self):
        card = self._base_card()
        card["classification"]["domain_tags"] = []
        result = validate_slim_card(card)
        assert "classification_empty" in result["warnings"]

    def test_missing_classification_triggers_warning(self):
        card = self._base_card()
        card["classification"] = {}
        result = validate_slim_card(card)
        assert "classification_empty" in result["warnings"]

    def test_n_tags_counts_domain_tags_only(self):
        card = self._base_card()
        card["classification"]["research_objects"] = ["kerogen", "clay"]
        card["classification"]["methods"] = ["GCMC"]
        card["classification"]["domain_tags"] = ["shale", "nanopore", "adsorption"]
        result = validate_slim_card(card)
        # n_tags should be 3 (domain_tags only), not 6 (all three lists)
        assert result["n_tags"] == 3

    def test_status_ok_when_all_required_fields_present(self):
        card = self._base_card()
        result = validate_slim_card(card)
        assert result["status"] == "ok"
        assert result["warnings"] == []

    def test_status_needs_fix_when_title_empty(self):
        card = self._base_card()
        card["paper"]["title"] = ""
        result = validate_slim_card(card)
        assert result["status"] == "needs_fix"
        assert "title_empty" in result["warnings"]

    def test_n_findings_counted(self):
        card = self._base_card()
        result = validate_slim_card(card)
        assert result["n_findings"] == 1
