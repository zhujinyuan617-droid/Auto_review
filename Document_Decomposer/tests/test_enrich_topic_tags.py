import sys
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT / "scripts" / "elements"))

from ai_enrich_topic_tags import MAX_TOTAL_TAGS, merge_tags


def test_merge_appends_dedupes_caseless_and_caps():
    card = {"classification": {"domain_tags": ["shale gas", "Adsorption"]}}
    added = merge_tags(card, ["adsorption", "confinement effect", "", "gas transport"])
    tags = card["classification"]["domain_tags"]
    assert added == 2
    assert tags == ["shale gas", "Adsorption", "confinement effect", "gas transport"]

    # 封顶:塞满后不再加
    card2 = {"classification": {"domain_tags": [f"t{i}" for i in range(MAX_TOTAL_TAGS)]}}
    assert merge_tags(card2, ["new one"]) == 0
    assert len(card2["classification"]["domain_tags"]) == MAX_TOTAL_TAGS


def test_merge_creates_classification_when_missing():
    card = {}
    assert merge_tags(card, ["diffusion"]) == 1
    assert card["classification"]["domain_tags"] == ["diffusion"]
