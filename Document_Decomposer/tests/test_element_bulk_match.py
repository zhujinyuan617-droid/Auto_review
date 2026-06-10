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
