import json
import os
import sqlite3
import time
from pathlib import Path

from fastapi.testclient import TestClient

from autoreview_app.api import create_app
from autoreview_app.config import AppConfig
from autoreview_app.map import service as map_service


def _write_card(lib: Path, pid: str, topic_ids=None, year=None, paper_type=None):
    d = lib / pid
    d.mkdir(parents=True, exist_ok=True)
    card = {
        "paper_id": pid,
        "paper": {"title": pid, "year": year, "paper_type": paper_type,
                  "journal": "", "doi": ""},
        "classification": {"topic_ids": topic_ids or []},
    }
    (d / "literature_card.json").write_text(json.dumps(card), encoding="utf-8")


def _write_elements_db(cfg: AppConfig, rows):
    cfg.elements_db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(cfg.elements_db)
    conn.executescript(
        "CREATE TABLE elements (element_id TEXT PRIMARY KEY, facet TEXT, slug TEXT,"
        " display_name TEXT, aliases_json TEXT, human_locked INTEGER);"
        "CREATE TABLE occurrences (paper_id TEXT, element_id TEXT, facet TEXT, surface TEXT,"
        " quote TEXT, reading_block_id TEXT, role TEXT, digits_verified INTEGER, values_json TEXT);")
    conn.executemany("INSERT INTO occurrences VALUES (?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()


def _client(tmp_path: Path) -> tuple[TestClient, AppConfig]:
    cfg = AppConfig(library_dir=tmp_path / "library")
    return TestClient(create_app(cfg)), cfg


def test_topic_lens_payload_shape_and_lit(tmp_path: Path):
    client, cfg = _client(tmp_path)
    _write_card(cfg.library_dir, "S01", topic_ids=["elem:topic/shale-gas"], year=2018)
    _write_card(cfg.library_dir, "S02", topic_ids=["elem:topic/shale-gas"], year=2022)
    _write_card(cfg.library_dir, "S03", topic_ids=[])  # 无 topic → 灰点
    body = client.get("/map?lens=topic").json()
    assert body["lens"] == "topic" and body["lenses"] == map_service.ALL_LENSES
    assert "time" not in body["lenses"]  # Wave-3 ①:时间镜头退役
    nodes = {n["id"]: n for n in body["nodes"]}
    assert set(nodes) == {"S01", "S02", "S03"}
    assert nodes["S01"]["lit"] and not nodes["S03"]["lit"]
    assert nodes["S01"]["cluster"] == nodes["S02"]["cluster"]  # 共享 topic 同区
    assert nodes["S01"]["year"] == 2018  # 年份随节点下发(区内年轮 + 区面板年代跨度用)
    # 灰点不再混进零散区,而是归「待构建」区(带 unbuilt 标志)
    assert nodes["S03"]["cluster"] == map_service.UNBUILT_CLUSTER
    unbuilt = [c for c in body["clusters"] if c.get("unbuilt")]
    assert len(unbuilt) == 1 and unbuilt[0]["n"] == 1 and unbuilt[0]["label"] == "待构建"
    assert (cfg.elements_data_dir / "map_layout_topic.json").exists()


def test_topic_lens_cache_hit_skips_layout(tmp_path: Path, monkeypatch):
    client, cfg = _client(tmp_path)
    _write_card(cfg.library_dir, "S01", topic_ids=["elem:topic/a"])
    _write_card(cfg.library_dir, "S02", topic_ids=["elem:topic/a"])
    client.get("/map?lens=topic")  # 建缓存

    calls = {"n": 0}
    real = map_service.radial_layout

    def counting(*a, **kw):
        calls["n"] += 1
        return real(*a, **kw)

    monkeypatch.setattr(map_service, "radial_layout", counting)
    client.get("/map?lens=topic")
    assert calls["n"] == 0  # 指纹命中,不重算


def test_topic_lens_incremental_keeps_old_coords(tmp_path: Path):
    client, cfg = _client(tmp_path)
    _write_card(cfg.library_dir, "S01", topic_ids=["elem:topic/a"])
    _write_card(cfg.library_dir, "S02", topic_ids=["elem:topic/a"])
    before = {n["id"]: (n["x"], n["y"]) for n in client.get("/map?lens=topic").json()["nodes"]}
    _write_card(cfg.library_dir, "S03", topic_ids=["elem:topic/a"])  # 新着陆
    after = client.get("/map?lens=topic").json()
    coords = {n["id"]: (n["x"], n["y"]) for n in after["nodes"]}
    assert coords["S01"] == before["S01"] and coords["S02"] == before["S02"]  # 老点不动
    assert "S03" in coords


def test_method_lens_503_without_index_then_200(tmp_path: Path):
    client, cfg = _client(tmp_path)
    _write_card(cfg.library_dir, "S01")
    assert client.get("/map?lens=method").status_code == 503
    _write_elements_db(cfg, [
        ("S01", "elem:simulation/gcmc", "simulation", "GCMC", "q", "S01-RB-0001", "used", 0, "[]"),
    ])
    body = client.get("/map?lens=method").json()
    assert {n["id"] for n in body["nodes"]} == {"S01"}


def test_unknown_lens_400(tmp_path: Path):
    client, cfg = _client(tmp_path)
    _write_card(cfg.library_dir, "S01")
    assert client.get("/map?lens=nope").status_code == 400


def test_time_lens_years(tmp_path: Path):
    client, cfg = _client(tmp_path)
    _write_card(cfg.library_dir, "S01", year=2021)
    _write_card(cfg.library_dir, "S02", year=None)
    nodes = {n["id"]: n for n in client.get("/map?lens=time").json()["nodes"]}
    assert nodes["S01"]["year"] == 2021 and nodes["S01"]["lit"]
    assert nodes["S02"]["year"] is None and not nodes["S02"]["lit"]


def _write_authorship(lib: Path, pid: str, inst_ids: list[str]):
    doc = {"paper_id": pid, "authors": [{"name": "A", "position": 1, "is_senior": True,
                                          "raw_affiliations": [], "institution_ids": inst_ids}],
           "source": "openalex", "fetched_at": "2026-06-10T00:00:00+00:00"}
    (lib / pid / "authorship.json").write_text(json.dumps(doc), encoding="utf-8")


def _write_institutions_registry(cfg: AppConfig, entries: dict):
    """entries: inst_id -> country_code(None=未补查)。"""
    cfg.institutions_registry_path.parent.mkdir(parents=True, exist_ok=True)
    reg = {"schema_version": "0.1.0", "facets": ["institution"], "entries": {
        i: {"id": i, "facet": "institution",
            "display_name": i.rsplit("/", 1)[-1].upper(),
            "aliases": [], "redirect_to": None,
            **({"country_code": cc} if cc else {})}
        for i, cc in entries.items()
    }}
    cfg.institutions_registry_path.write_text(json.dumps(reg), encoding="utf-8")


def test_institution_lens_continents(tmp_path: Path):
    # Wave-3 ④:论文 → 主机构 → 国别 → 洲;无机构数据 → __unknown__(nodata)
    client, cfg = _client(tmp_path)
    for pid, year in (("S01", 2018), ("S02", 2020), ("S03", 2021), ("S04", None)):
        _write_card(cfg.library_dir, pid, year=year)
    _write_authorship(cfg.library_dir, "S01", ["elem:institution/mit"])
    _write_authorship(cfg.library_dir, "S02", ["elem:institution/mit"])
    _write_authorship(cfg.library_dir, "S03", ["elem:institution/tsinghua"])
    # S04 无 authorship.json
    _write_institutions_registry(cfg, {
        "elem:institution/mit": "US",
        "elem:institution/tsinghua": "CN",
    })
    body = client.get("/map?lens=institution").json()
    nodes = {n["id"]: n for n in body["nodes"]}
    assert nodes["S01"]["cluster"] == nodes["S02"]["cluster"] == "cont:north-america"
    assert nodes["S03"]["cluster"] == "cont:asia"
    assert nodes["S04"]["cluster"] == "__unknown__" and not nodes["S04"]["lit"]
    assert nodes["S01"]["year"] == 2018  # 年轮数据随节点下发
    by_id = {c["id"]: c for c in body["clusters"]}
    assert by_id["cont:north-america"]["label"] == "北美洲"
    top = by_id["cont:north-america"]["top_institutions"]
    assert top[0]["papers"] == 2 and top[0]["id"] == "elem:institution/mit"
    assert by_id["__unknown__"].get("nodata") is True


def test_institution_lens_cache_invalidates_on_country_enrichment(tmp_path: Path):
    # 国别补查写回注册表后,机构镜头缓存指纹必须失效并重算分区
    client, cfg = _client(tmp_path)
    _write_card(cfg.library_dir, "S01")
    _write_authorship(cfg.library_dir, "S01", ["elem:institution/mit"])
    body1 = client.get("/map?lens=institution").json()
    assert body1["nodes"][0]["cluster"] == "__unknown__"  # 注册表还没有国别
    _write_institutions_registry(cfg, {"elem:institution/mit": "US"})
    body2 = client.get("/map?lens=institution").json()
    assert body2["nodes"][0]["cluster"] == "cont:north-america"


def test_relayout_recomputes(tmp_path: Path, monkeypatch):
    client, cfg = _client(tmp_path)
    _write_card(cfg.library_dir, "S01", topic_ids=["elem:topic/a"])
    _write_card(cfg.library_dir, "S02", topic_ids=["elem:topic/a"])
    client.get("/map?lens=topic")
    calls = {"n": 0}
    real = map_service.radial_layout

    def counting(*a, **kw):
        calls["n"] += 1
        return real(*a, **kw)

    monkeypatch.setattr(map_service, "radial_layout", counting)
    assert client.post("/map/relayout?lens=topic").status_code == 200
    assert calls["n"] == 1  # 显式重排必重算


def test_arrivals_latest_batch_only(tmp_path: Path):
    client, cfg = _client(tmp_path)
    for pid in ("S01", "S02", "S03"):
        _write_card(cfg.library_dir, pid, topic_ids=["elem:topic/a"])
    _write_card(cfg.library_dir, "S04", topic_ids=["elem:topic/a"])
    _write_card(cfg.library_dir, "S05", topic_ids=["elem:topic/b"])  # 与老库无共享 → isolated
    old = time.time() - 3 * 3600
    for pid in ("S01", "S02", "S03"):
        os.utime(cfg.library_dir / pid / "literature_card.json", (old, old))
    body = client.get("/map/arrivals").json()
    ids = {e["paper_id"] for e in body["batch"]}
    assert ids == {"S04", "S05"}
    by_id = {e["paper_id"]: e for e in body["batch"]}
    assert by_id["S04"]["neighbors"] and not by_id["S04"]["isolated"]
    assert by_id["S05"]["isolated"]


def test_arrivals_single_batch_library_empty(tmp_path: Path):
    client, cfg = _client(tmp_path)
    _write_card(cfg.library_dir, "S01", topic_ids=["elem:topic/a"])
    _write_card(cfg.library_dir, "S02", topic_ids=["elem:topic/a"])
    assert client.get("/map/arrivals").json()["batch"] == []


def test_route_review_first_then_size(tmp_path: Path):
    client, cfg = _client(tmp_path)
    # 4 篇:S01/S02 强连(a+b),S03 经 b 挂进同区(b 非烂大街:df=3/4),S04 独立区
    _write_card(cfg.library_dir, "S01", topic_ids=["elem:topic/a", "elem:topic/b"])
    _write_card(cfg.library_dir, "S02", topic_ids=["elem:topic/a", "elem:topic/b"])
    _write_card(cfg.library_dir, "S03", topic_ids=["elem:topic/b"], paper_type="Review Article")
    _write_card(cfg.library_dir, "S04", topic_ids=["elem:topic/c"])
    body = client.get("/map?lens=topic").json()
    nodes = {n["id"]: n for n in body["nodes"]}
    cluster = nodes["S01"]["cluster"]
    assert nodes["S03"]["cluster"] == cluster  # 前提:综述确在同区
    route = client.get(f"/map/route?lens=topic&cluster={cluster}").json()
    assert route["order"][0] == "S03"          # 综述优先
    assert route["order"][1] in ("S01", "S02")  # 其后按核心度
    assert len(route["start_with"]) <= 3


def test_region_elements_profile(tmp_path: Path):
    # Wave-3 ②:统计屏总览并入区面板 —— 区成员的 facet×要素 top 画像
    client, cfg = _client(tmp_path)
    _write_card(cfg.library_dir, "S01", topic_ids=["elem:topic/a"])
    _write_card(cfg.library_dir, "S02", topic_ids=["elem:topic/a"])
    _write_card(cfg.library_dir, "S03", topic_ids=["elem:topic/b"])  # 撑 idf>0,使 a 区成形
    _write_elements_db(cfg, [
        ("S01", "elem:simulation/gcmc", "simulation", "GCMC", "q", "S01-RB-0001", "used", 0, "[]"),
        ("S02", "elem:simulation/gcmc", "simulation", "GCMC", "q", "S02-RB-0001", "used", 0, "[]"),
        ("S02", "elem:material/kaolinite", "material", "kaolinite", "q", "S02-RB-0002", "used", 0, "[]"),
    ])
    conn = sqlite3.connect(cfg.elements_db)
    conn.executemany("INSERT INTO elements VALUES (?,?,?,?,?,?)", [
        ("elem:simulation/gcmc", "simulation", "gcmc", "GCMC", "[]", 0),
        ("elem:material/kaolinite", "material", "kaolinite", "Kaolinite", "[]", 0),
    ])
    conn.commit()
    conn.close()
    cluster = client.get("/map?lens=topic").json()["nodes"][0]["cluster"]
    body = client.get(f"/map/region-elements?lens=topic&cluster={cluster}").json()
    assert body["papers"] == 2
    sim = body["facets"]["simulation"]
    assert sim[0]["name"] == "GCMC" and sim[0]["papers"] == 2
    assert body["facets"]["material"][0]["papers"] == 1


def test_region_elements_slim_and_scoped_first_seen(tmp_path: Path):
    # 区面板瘦身(用户反馈):≥3 篇的区只列 ≥2 篇共用;×1 折叠计数;
    # condition/finding 整组撤出;首现支持区内口径(只看本区论文的要素)
    client, cfg = _client(tmp_path)
    for pid, year in (("S01", 2015), ("S02", 2018), ("S03", 2020), ("S04", 2021)):
        _write_card(cfg.library_dir, pid, topic_ids=["elem:topic/a"], year=year)
    _write_card(cfg.library_dir, "S05", topic_ids=["elem:topic/b"], year=2019)  # 区外
    rows = [(pid, "elem:simulation/gcmc", "simulation", "GCMC", "q", f"{pid}-RB-1", "used", 0, "[]")
            for pid in ("S01", "S02", "S03")]
    rows += [
        ("S01", "elem:material/kaolinite", "material", "kaolinite", "q", "S01-RB-2", "used", 0, "[]"),
        ("S02", "elem:condition/t300", "condition", "300 K", "q", "S02-RB-3", "used", 0, "[]"),
        ("S05", "elem:simulation/lbm", "simulation", "LBM", "q", "S05-RB-1", "used", 0, "[]"),
    ]
    _write_elements_db(cfg, rows)
    conn = sqlite3.connect(cfg.elements_db)
    conn.executemany("INSERT INTO elements VALUES (?,?,?,?,?,?)", [
        ("elem:simulation/gcmc", "simulation", "gcmc", "GCMC", "[]", 0),
        ("elem:material/kaolinite", "material", "kaolinite", "Kaolinite", "[]", 0),
        ("elem:condition/t300", "condition", "t300", "300 K", "[]", 0),
        ("elem:simulation/lbm", "simulation", "lbm", "LBM", "[]", 0),
    ])
    conn.commit()
    conn.close()
    nodes = client.get("/map?lens=topic").json()["nodes"]
    cluster = next(n["cluster"] for n in nodes if n["id"] == "S01")
    body = client.get(f"/map/region-elements?lens=topic&cluster={cluster}").json()
    assert list(body["facets"]) == ["simulation"]  # ×1 的 material 不上榜;condition 整组撤出
    assert body["facets"]["simulation"][0] == {"name": "GCMC", "papers": 3}
    assert body["singles"] == 1  # kaolinite 折叠计数(condition 不计入)

    fs = client.get(f"/map/first-seen?lens=topic&cluster={cluster}").json()
    names = [e["name"] for e in fs["elements"]]
    assert "LBM" not in names  # 区外论文的要素不进时间线
    assert set(names) == {"GCMC", "Kaolinite", "300 K"}
    assert fs["elements"][0]["first_year"] == 2015  # 按进场年升序
