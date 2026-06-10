import json
from pathlib import Path

import pytest
from _fake_ai import SequencedFakeClient
from docdecomp.element_matching import _shortlist_candidates
from docdecomp.element_registry import load_seeds, new_registry_from_seeds

ENGINE_ROOT = Path(__file__).resolve().parents[1]
SEEDS = load_seeds(ENGINE_ROOT / "config" / "element_seeds.json")


def test_shortlist_same_facet_ranked_by_overlap():
    reg = new_registry_from_seeds(SEEDS)
    out = _shortlist_candidates(reg, "characterization", "powder x-ray diffraction patterns")
    assert out, "expect at least the XRD seed entry"
    assert out[0]["id"] == "elem:characterization/x-ray-diffraction"
    assert all(e["facet"] == "characterization" for e in out)


def test_shortlist_zero_overlap_excluded_and_capped():
    reg = new_registry_from_seeds(SEEDS)
    assert _shortlist_candidates(reg, "characterization", "zzz qqq") == []
    # cap 真正钉住切片:人工注册表,3 个同 facet 重叠条目
    reg2 = {"schema_version": "0.1.0", "facets": ["material"], "entries": {}}
    for name in ("alpha clay", "beta clay", "gamma clay"):
        eid = f"elem:material/{name.replace(' ', '-')}"
        reg2["entries"][eid] = {"id": eid, "facet": "material", "display_name": name,
                                "aliases": [], "redirect_to": None,
                                "origin": "seed", "human_locked": False}
    assert len(_shortlist_candidates(reg2, "material", "clay sample", cap=2)) == 2
    assert len(_shortlist_candidates(reg2, "material", "clay sample")) == 3


def test_shortlist_skips_redirected_entries():
    reg = new_registry_from_seeds(SEEDS)
    eids = [e for e in reg["entries"] if e.startswith("elem:characterization/")]
    src = "elem:characterization/x-ray-diffraction"
    dst = next(e for e in eids if e != src)
    reg["entries"][src]["redirect_to"] = dst
    out = _shortlist_candidates(reg, "characterization", "x-ray diffraction")
    assert all(e["id"] != src for e in out)


# ---------------------------------------------------------------------------
# Task 2: collect_unresolved — bulk collect phase helpers
# ---------------------------------------------------------------------------


def _occ(facet, surface, canonical_id=None):
    return {"facet": facet, "surface": surface, "quote": "q",
            "reading_block_id": "SX-RB-0001", "role": "used",
            "quote_verified": True, "digits_verified": False,
            "values": [], "canonical_id": canonical_id}


def _write_elements(paper_dir: Path, occurrences):
    paper_dir.mkdir(parents=True, exist_ok=True)
    data = {"schema_version": "0.1.0", "paper_id": paper_dir.name,
            "occurrences": occurrences, "dropped": []}
    (paper_dir / "elements.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_collect_exact_hits_dangling_and_dedup(tmp_path: Path):
    from docdecomp.element_matching import collect_unresolved
    reg = new_registry_from_seeds(SEEDS)
    p1, p2 = tmp_path / "S01", tmp_path / "S02"
    _write_elements(p1, [
        _occ("characterization", "XRD"),                       # alias 命中种子
        _occ("material", "kerogen type II"),                   # 生面孔
        _occ("preparation", "ball milling",
             canonical_id="elem:preparation/ball-milling"),    # 已解析且有效 → 不动
    ])
    _write_elements(p2, [
        _occ("material", "Kerogen Type II"),                   # 同 norm_key → 与 p1 去重
        _occ("material", "frankenite-x99", canonical_id="elem:material/ghost-entry"),  # 悬空+生造词 → 视同未解析
    ])
    docs, dirty, groups = collect_unresolved([p1, p2], reg)

    assert (p1 / "elements.json") in dirty            # XRD exact 命中,文件已脏
    occ_xrd = docs[p1 / "elements.json"]["occurrences"][0]
    assert occ_xrd["canonical_id"] == "elem:characterization/x-ray-diffraction"

    keys = {(g["facet"], g["surface"].lower()) for g in groups}
    assert ("material", "kerogen type ii") in keys
    assert ("material", "frankenite-x99") in keys     # 悬空被收集 → 可自愈
    kerogen = next(g for g in groups if g["surface"].lower().startswith("kerogen"))
    assert len(kerogen["refs"]) == 2                  # 两篇引用同一组


def test_collect_repoints_redirected_canonical(tmp_path: Path):
    from docdecomp.element_matching import collect_unresolved
    from docdecomp.element_registry import merge_entries
    reg = new_registry_from_seeds(SEEDS)
    log = tmp_path / "log.jsonl"
    eids = [e for e in reg["entries"] if e.startswith("elem:characterization/")]
    src, dst = eids[0], eids[1]
    merge_entries(reg, src, dst, "human", log)
    p1 = tmp_path / "S01"
    _write_elements(p1, [_occ("characterization", "whatever", canonical_id=src)])
    docs, dirty, groups = collect_unresolved([p1], reg)
    assert docs[p1 / "elements.json"]["occurrences"][0]["canonical_id"] == dst
    assert (p1 / "elements.json") in dirty and groups == []
