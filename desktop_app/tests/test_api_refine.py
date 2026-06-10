"""POST /elements/refine — 检索屏联动计数(spec §4c)。

假库 3 篇:S01{xrd,gcmc}、S02{xrd}、S03{sem}(均 used)+ S03 一条 mentioned 的
gcmc,用来验证 role 过滤。建库方式与 test_api_elements.py 相同(fake AI 走
真实抽取+判同管线;surface 都是种子别名,判同零 AI 调用)。
"""
from pathlib import Path

from fastapi.testclient import TestClient

from _element_fixtures import write_reading_blocks
from _fake_ai import SequencedFakeClient
from autoreview_app.api import create_app
from autoreview_app.config import AppConfig
from autoreview_app.elements import service

XRD = "elem:characterization/x-ray-diffraction"
GCMC = "elem:simulation/grand-canonical-monte-carlo"
SEM = "elem:characterization/scanning-electron-microscopy"
TEM = "elem:characterization/transmission-electron-microscopy"  # 种子里有、全库没人用


def _elem(facet: str, surface: str, quote: str, rb_id: str, role: str = "used") -> dict:
    return {"facet": facet, "surface": surface, "quote": quote,
            "reading_block_id": rb_id, "role": role}


def _built_library(tmp_path: Path) -> AppConfig:
    library = tmp_path / "library"
    cfg = AppConfig(library_dir=library)
    papers = {
        "S01": ([("S01-RB-0001", "XRD patterns were recorded. GCMC simulations were performed.", "methods")],
                [_elem("characterization", "XRD", "XRD patterns were recorded", "S01-RB-0001"),
                 _elem("simulation", "GCMC", "GCMC simulations were performed", "S01-RB-0001")]),
        "S02": ([("S02-RB-0001", "XRD patterns were recorded with CuKa radiation.", "methods")],
                [_elem("characterization", "XRD", "XRD patterns were recorded", "S02-RB-0001")]),
        "S03": ([("S03-RB-0001", "SEM images were collected. GCMC is discussed in prior work.", "methods")],
                [_elem("characterization", "SEM", "SEM images were collected", "S03-RB-0001"),
                 _elem("simulation", "GCMC", "GCMC is discussed in prior work", "S03-RB-0001",
                       role="mentioned")]),
    }
    for pid, (blocks, elems) in papers.items():
        paper_dir = write_reading_blocks(library, pid, blocks)
        client = SequencedFakeClient([{"paper_id": pid, "elements": elems}])
        service.run_elements_for_paper(paper_dir, client, cfg)
    return cfg


def _client(cfg: AppConfig) -> TestClient:
    return TestClient(create_app(cfg))


def test_refine_503_before_build(tmp_path: Path):
    cfg = AppConfig(library_dir=tmp_path / "library")
    (tmp_path / "library").mkdir()
    c = _client(cfg)
    assert c.post("/elements/refine", json={"element_ids": []}).status_code == 503


def test_refine_empty_selection_counts_whole_library(tmp_path: Path):
    c = _client(_built_library(tmp_path))
    r = c.post("/elements/refine", json={"element_ids": []}).json()
    assert r["papers"] == ["S01", "S02", "S03"]
    assert r["counts"][XRD] == 2
    assert r["counts"][GCMC] == 1  # S03 的 gcmc 是 mentioned,默认 role=used 不计
    assert r["counts"][SEM] == 1
    assert r["counts"][TEM] == 0  # 全表条目都要有计数,零也在(前端靠它灰显)


def test_refine_single_selection_narrows_counts(tmp_path: Path):
    c = _client(_built_library(tmp_path))
    r = c.post("/elements/refine", json={"element_ids": [XRD]}).json()
    assert r["papers"] == ["S01", "S02"]
    assert r["counts"][XRD] == 2
    assert r["counts"][GCMC] == 1  # S01 同时有 gcmc
    assert r["counts"][SEM] == 0   # sem 只在 S03,与 xrd 无交集


def test_refine_combination_and_duplicate_ids(tmp_path: Path):
    c = _client(_built_library(tmp_path))
    r = c.post("/elements/refine", json={"element_ids": [XRD, GCMC, XRD]}).json()  # 重复 id 必须去重
    assert r["papers"] == ["S01"]
    assert r["counts"][XRD] == 1 and r["counts"][GCMC] == 1 and r["counts"][SEM] == 0


def test_refine_role_filter(tmp_path: Path):
    c = _client(_built_library(tmp_path))
    r = c.post("/elements/refine", json={"element_ids": [GCMC], "role": "mentioned"}).json()
    assert r["papers"] == ["S03"]
    assert r["counts"][GCMC] == 1
    assert r["counts"][SEM] == 0  # S03 的 sem 是 used,mentioned 视角下不计
    assert r["counts"][XRD] == 0
    # role=all(=不过滤):两种 role 都算
    r2 = c.post("/elements/refine", json={"element_ids": [GCMC], "role": "all"}).json()
    assert r2["papers"] == ["S01", "S03"]
    assert r2["counts"][GCMC] == 2 and r2["counts"][SEM] == 1 and r2["counts"][XRD] == 1
