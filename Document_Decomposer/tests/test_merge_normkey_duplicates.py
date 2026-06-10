import json
import sys
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT / "scripts" / "elements"))

from docdecomp.element_registry import (
    create_entry,
    load_seeds,
    new_registry_from_seeds,
    save_registry,
)

from merge_normkey_duplicates import find_duplicate_groups, merge_duplicates, pick_target

SEEDS = load_seeds(ENGINE_ROOT / "config" / "element_seeds.json")


def _bare_registry() -> dict:
    return {"schema_version": "0.1.0", "facets": ["material"], "entries": {}}


def test_find_groups_same_facet_plural_folded(tmp_path: Path):
    reg = _bare_registry()
    log = tmp_path / "log.jsonl"
    create_entry(reg, "material", "carbon slit", "auto-stream", log)
    create_entry(reg, "material", "Carbon Slit", "auto-bulk", log)   # 大小写变体 → 入组
    create_entry(reg, "material", "carbon slits", "auto-bulk", log)  # 复数 → 同键入组
    create_entry(reg, "condition", "carbon slit", "auto-bulk", log)  # 异 facet → 不入组
    groups = find_duplicate_groups(reg)
    assert len(groups) == 1
    (facet, key), members = next(iter(groups.items()))
    assert facet == "material" and key == "carbon slit"
    assert len(members) == 3


def test_singularize_is_conservative():
    from merge_normkey_duplicates import dedupe_key
    assert dedupe_key("adsorption isotherms") == dedupe_key("adsorption isotherm")
    assert dedupe_key("Materials Studio") == dedupe_key("Material Studio")
    # 保护词:短词、ss/us/is 结尾不剥
    assert dedupe_key("gas") == "gas"
    assert dedupe_key("glass") == "glass"
    assert dedupe_key("porous media") == "porous media"  # us 结尾不剥
    assert dedupe_key("basis sets") == "basis set"       # is 结尾保护,普通复数剥


def test_pick_target_priority_locked_then_seed_then_aliases_then_id(tmp_path: Path):
    reg = _bare_registry()
    log = tmp_path / "log.jsonl"
    a = create_entry(reg, "material", "silica", "auto-bulk", log)
    b = create_entry(reg, "material", "Silica", "auto-stream", log)
    reg["entries"][b]["aliases"].append("SiO2 glass")
    # 无锁无种子 → 别名多者(b)为 target
    assert pick_target([reg["entries"][a], reg["entries"][b]])["id"] == b
    # seed 压过别名数
    reg["entries"][a]["origin"] = "seed"
    assert pick_target([reg["entries"][a], reg["entries"][b]])["id"] == a
    # human_locked 压过一切
    reg["entries"][b]["human_locked"] = True
    assert pick_target([reg["entries"][a], reg["entries"][b]])["id"] == b


def test_merge_redirects_and_is_idempotent(tmp_path: Path):
    reg = _bare_registry()
    log = tmp_path / "log.jsonl"
    a = create_entry(reg, "material", "carbonate", "seed", log)
    b = create_entry(reg, "material", "Carbonate", "auto-bulk", log)
    stats = merge_duplicates(reg, log, apply=True)
    assert stats["merged"] == 1
    assert reg["entries"][b]["redirect_to"] == a
    assert reg["entries"][a]["redirect_to"] is None
    # 幂等:redirect 条目被跳过
    stats2 = merge_duplicates(reg, log, apply=True)
    assert stats2["merged"] == 0


def test_two_human_locked_duplicates_left_for_human(tmp_path: Path):
    reg = _bare_registry()
    log = tmp_path / "log.jsonl"
    a = create_entry(reg, "material", "kaolinite", "auto-bulk", log)
    b = create_entry(reg, "material", "Kaolinite", "auto-bulk", log)
    reg["entries"][a]["human_locked"] = True
    reg["entries"][b]["human_locked"] = True
    stats = merge_duplicates(reg, log, apply=True)
    assert stats["merged"] == 0 and stats["skipped_locked"] == 1
    assert reg["entries"][a]["redirect_to"] is None
    assert reg["entries"][b]["redirect_to"] is None


def test_dry_run_changes_nothing(tmp_path: Path):
    reg = _bare_registry()
    log = tmp_path / "log.jsonl"
    create_entry(reg, "material", "quartz", "auto-bulk", log)
    create_entry(reg, "material", "Quartz", "auto-bulk", log)
    before = json.dumps(reg, sort_keys=True)
    stats = merge_duplicates(reg, log, apply=False)
    assert stats["groups"] == 1 and stats["merged"] == 0
    assert json.dumps(reg, sort_keys=True) == before


def test_seed_registry_has_no_internal_duplicates(tmp_path: Path):
    # 种子词表自身必须干净——否则脚本一跑会动种子
    reg = new_registry_from_seeds(SEEDS)
    assert find_duplicate_groups(reg) == {}
