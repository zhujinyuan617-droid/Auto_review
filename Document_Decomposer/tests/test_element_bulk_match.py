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
    occ_ball = docs[p1 / "elements.json"]["occurrences"][2]
    assert occ_ball["canonical_id"] == "elem:preparation/ball-milling"
    assert (p2 / "elements.json") not in dirty        # p2 无任何就地改写


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


# ---------------------------------------------------------------------------
# Task 3: _pack_chunks + _judge_chunks — bulk-match parallel judging
# ---------------------------------------------------------------------------


def test_pack_chunks_by_size_and_candidate_cap():
    from docdecomp.element_matching import _pack_chunks
    def item(n, k):
        return {"facet": "material", "surface": f"s{n}",
                "candidates": [{"id": f"c{n}-{j}"} for j in range(k)]}
    items = [item(n, 5) for n in range(70)]
    chunks = _pack_chunks(items, chunk_size=30, candidate_cap=120)
    assert all(len(c) <= 30 for c in chunks)
    for c in chunks:
        union = {x["id"] for it in c for x in it["candidates"]}
        assert len(union) <= 120
    assert sum(len(c) for c in chunks) == 70


def test_judge_chunks_maps_by_normkey_and_isolates_failures():
    from docdecomp.element_matching import _judge_chunks

    class _OneBoomClient:
        def __init__(self):
            self.n = 0
        def chat_json(self, messages, hint):
            self.n += 1
            if self.n == 1:
                raise RuntimeError("boom")
            return {"matches": [{"surface": "Powder XRD",
                                 "element_id": "elem:characterization/x-ray-diffraction"}]}

    chunk_a = [{"facet": "characterization", "surface": "weird thing one", "candidates": []}]
    chunk_b = [{"facet": "characterization", "surface": "powder xrd",
                "candidates": [{"id": "elem:characterization/x-ray-diffraction",
                                "display_name": "X-ray diffraction", "aliases": ["XRD"]}]}]
    verdicts, failed, n_ok, n_failed = _judge_chunks(
        {"characterization": [chunk_a, chunk_b]}, _OneBoomClient(), parallel=1)
    assert ("characterization", "powder xrd") in verdicts          # norm_key 键
    assert verdicts[("characterization", "powder xrd")] == "elem:characterization/x-ray-diffraction"
    assert ("characterization", "weird thing one") in failed       # 失败块只标记不扩散
    assert n_ok == 1 and n_failed == 1


def test_judge_chunks_runs_concurrently_and_passes_candidates():
    import threading
    from docdecomp.element_matching import _judge_chunks

    class _BarrierClient:
        """两个调用都到齐才放行——若串行执行会死锁超时,故能钉住真并发。"""
        def __init__(self):
            self.barrier = threading.Barrier(2, timeout=10)
            self.threads = set()
            self.payloads = []
        def chat_json(self, messages, hint):
            self.threads.add(threading.current_thread().name)
            self.payloads.append(messages[1]["content"])
            self.barrier.wait()
            return {"matches": []}

    cand = {"id": "elem:material/quartz", "display_name": "quartz", "aliases": []}
    chunk_a = [{"facet": "material", "surface": "alpha quartz", "candidates": [cand]}]
    chunk_b = [{"facet": "material", "surface": "beta quartz", "candidates": [cand]}]
    client = _BarrierClient()
    verdicts, failed, n_ok, n_failed = _judge_chunks(
        {"material": [chunk_a, chunk_b]}, client, parallel=2)
    assert n_ok == 2 and n_failed == 0
    assert len(client.threads) == 2                      # 真并发(两个不同线程)
    assert all("quartz" in p for p in client.payloads)   # 候选并集确实进了提示词


# ---------------------------------------------------------------------------
# Task 4: bulk_match_elements — end-to-end orchestrator
# ---------------------------------------------------------------------------


def test_bulk_match_end_to_end_and_idempotent(tmp_path: Path):
    from docdecomp.element_matching import bulk_match_elements
    reg = new_registry_from_seeds(SEEDS)
    log = tmp_path / "log.jsonl"
    p1, p2 = tmp_path / "S01", tmp_path / "S02"
    _write_elements(p1, [
        _occ("characterization", "XRD"),                    # exact
        _occ("characterization", "powder X-ray diffraction"),  # AI → match
        _occ("material", "kerogen type II"),                # AI → null → create
        _occ("proposed:instrument", "weird gadget"),        # proposed → 直接 create,不上 AI
    ])
    _write_elements(p2, [_occ("material", "Kerogen Type II")])  # 去重共组

    client = SequencedFakeClient([
        # 两个 facet 各一块;块完成顺序不定,故两个响应都写全两类 surface,
        # 引擎按 (facet, norm_key) 查组,查不到的回显键自然被忽略。
        {"matches": [
            {"surface": "powder X-ray diffraction",
             "element_id": "elem:characterization/x-ray-diffraction"},
            {"surface": "kerogen type II", "element_id": None},
        ]},
        {"matches": [
            {"surface": "powder X-ray diffraction",
             "element_id": "elem:characterization/x-ray-diffraction"},
            {"surface": "kerogen type II", "element_id": None},
        ]},
    ])
    stats = bulk_match_elements([p1, p2], reg, client, log, parallel=2)

    d1 = json.loads((p1 / "elements.json").read_text(encoding="utf-8"))
    ids = {o["surface"]: o["canonical_id"] for o in d1["occurrences"]}
    assert ids["XRD"] == "elem:characterization/x-ray-diffraction"
    assert ids["powder X-ray diffraction"] == "elem:characterization/x-ray-diffraction"
    assert ids["kerogen type II"] == "elem:material/kerogen-type-ii"
    assert ids["weird gadget"] == "elem:proposed:instrument/weird-gadget"
    d2 = json.loads((p2 / "elements.json").read_text(encoding="utf-8"))
    assert d2["occurrences"][0]["canonical_id"] == "elem:material/kerogen-type-ii"
    assert stats["ai_calls"] == 2 and stats["created"] == 2
    assert "powder X-ray diffraction" in reg["entries"]["elem:characterization/x-ray-diffraction"]["aliases"]

    # 幂等:第二次零 AI、零新建、零写盘
    stats2 = bulk_match_elements([p1, p2], reg, None, log, parallel=2)
    assert stats2["ai_calls"] == 0 and stats2["created"] == 0 and stats2["papers_written"] == 0


def test_bulk_match_no_client_creates_directly(tmp_path: Path):
    from docdecomp.element_matching import bulk_match_elements
    reg = new_registry_from_seeds(SEEDS)
    p1 = tmp_path / "S01"
    _write_elements(p1, [_occ("material", "montmorillonite-illite mixed layer")])
    stats = bulk_match_elements([p1], reg, None, tmp_path / "log.jsonl", parallel=4)
    assert stats["created"] == 1 and stats["ai_calls"] == 0


def test_bulk_match_failed_chunk_left_unresolved(tmp_path: Path):
    from docdecomp.element_matching import bulk_match_elements

    class _AlwaysBoom:
        def chat_json(self, messages, hint):
            raise RuntimeError("429")

    reg = new_registry_from_seeds(SEEDS)
    p1 = tmp_path / "S01"
    _write_elements(p1, [_occ("material", "kerogen type II")])
    stats = bulk_match_elements([p1], reg, _AlwaysBoom(), tmp_path / "log.jsonl", parallel=2)
    d1 = json.loads((p1 / "elements.json").read_text(encoding="utf-8"))
    assert d1["occurrences"][0]["canonical_id"] is None      # 留空待重试
    assert stats["created"] == 0 and stats["judge_failed_chunks"] >= 1
