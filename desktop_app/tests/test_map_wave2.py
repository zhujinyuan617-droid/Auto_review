import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from autoreview_app.api import create_app
from autoreview_app.config import AppConfig
from autoreview_app.map import service as map_service
from autoreview_app.map.service import _merge_tiny_clusters


def _write_card(lib: Path, pid: str, topic_ids=None, year=None, title=None):
    d = lib / pid
    d.mkdir(parents=True, exist_ok=True)
    card = {"paper_id": pid,
            "paper": {"title": title or f"Paper {pid}", "year": year, "paper_type": None,
                      "journal": "", "doi": ""},
            "classification": {"topic_ids": topic_ids or []}}
    (d / "literature_card.json").write_text(json.dumps(card, ensure_ascii=False), encoding="utf-8")


def _write_elements_db(cfg: AppConfig, occ_rows, elem_rows=()):
    cfg.elements_db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(cfg.elements_db)
    conn.executescript(
        "CREATE TABLE elements (element_id TEXT PRIMARY KEY, facet TEXT, slug TEXT,"
        " display_name TEXT, aliases_json TEXT, human_locked INTEGER);"
        "CREATE TABLE occurrences (paper_id TEXT, element_id TEXT, facet TEXT, surface TEXT,"
        " quote TEXT, reading_block_id TEXT, role TEXT, digits_verified INTEGER, values_json TEXT);")
    conn.executemany("INSERT INTO elements VALUES (?,?,?,?,?,?)", list(elem_rows))
    conn.executemany("INSERT INTO occurrences VALUES (?,?,?,?,?,?,?,?,?)", list(occ_rows))
    conn.commit()
    conn.close()


def _client(tmp_path: Path):
    cfg = AppConfig(library_dir=tmp_path / "library")
    return TestClient(create_app(cfg)), cfg


# ------------------------------------------------------------- tiny merge ----

def test_merge_tiny_clusters_into_strongest_big():
    labels = {"A1": "A", "A2": "A", "A3": "A", "T1": "T", "X1": "X"}
    edges = [("T1", "A1", 2.0), ("X1", "X1", 0.0)]  # T 有边连向 A;X 无外边
    out = _merge_tiny_clusters(labels, edges, min_size=3)
    assert out["T1"] == "A"
    assert out["X1"] == "__misc__"
    assert out["A1"] == "A"


def test_merge_tiny_noop_when_no_big_cluster():
    labels = {"A1": "A", "B1": "B"}
    assert _merge_tiny_clusters(labels, [], min_size=3) == labels


# --------------------------------------------------------- label override ----

def test_cluster_label_override_survives_relayout(tmp_path: Path):
    client, cfg = _client(tmp_path)
    for pid in ("S01", "S02", "S03"):
        _write_card(cfg.library_dir, pid, topic_ids=["elem:topic/a", f"elem:topic/extra-{pid}"])
    body = client.get("/map?lens=topic").json()
    cluster_id = body["nodes"][0]["cluster"]
    resp = client.put("/map/cluster-label",
                      json={"lens": "topic", "cluster_id": cluster_id, "label": "我的命名"})
    assert resp.status_code == 200
    body2 = client.get("/map?lens=topic").json()
    labels = {c["id"]: c for c in body2["clusters"]}
    assert labels[cluster_id]["label"] == "我的命名"
    assert labels[cluster_id]["label_overridden"] is True
    # 显式重排后(成员相同 → 精确键命中)人工名仍在
    client.post("/map/relayout?lens=topic")
    body3 = client.get("/map?lens=topic").json()
    assert {c["id"]: c for c in body3["clusters"]}[cluster_id]["label"] == "我的命名"


def test_cluster_label_unknown_cluster_400(tmp_path: Path):
    client, cfg = _client(tmp_path)
    _write_card(cfg.library_dir, "S01", topic_ids=["elem:topic/a"])
    resp = client.put("/map/cluster-label",
                      json={"lens": "topic", "cluster_id": "nope", "label": "x"})
    assert resp.status_code == 400


# ----------------------------------------------------------- descriptions ----

class _DescribeFake:
    def __init__(self):
        self.calls = 0

    def chat_json(self, messages, hint):
        self.calls += 1
        payload = json.loads(messages[1]["content"])
        return {"descriptions": [
            {"cluster_id": c["cluster_id"], "sentence": f"这区研究{c['auto_label']}相关问题"}
            for c in payload["clusters"]]}


def test_describe_clusters_generates_once_and_caches(tmp_path: Path):
    client, cfg = _client(tmp_path)
    for pid in ("S01", "S02", "S03"):
        _write_card(cfg.library_dir, pid, topic_ids=["elem:topic/a", "elem:topic/b"])
    fake = _DescribeFake()
    out = map_service.describe_clusters(cfg, "topic", fake)
    assert out["ai_calls"] == 1 and out["generated"] >= 1
    body = client.get("/map?lens=topic").json()
    assert any(c.get("description") for c in body["clusters"])
    # 二跑:全部已有描述 → 零调用
    out2 = map_service.describe_clusters(cfg, "topic", fake)
    assert out2["ai_calls"] == 0 and fake.calls == 1
    # 无 client → 优雅缺省不炸
    out3 = map_service.describe_clusters(cfg, "topic", None)
    assert out3["ai_calls"] == 0


# -------------------------------------------------------------- neighbors ----

def test_neighbors_true_shared_elements(tmp_path: Path):
    client, cfg = _client(tmp_path)
    _write_card(cfg.library_dir, "S01", topic_ids=["elem:topic/rare", "elem:topic/common"])
    _write_card(cfg.library_dir, "S02", topic_ids=["elem:topic/rare", "elem:topic/common"])
    _write_card(cfg.library_dir, "S03", topic_ids=["elem:topic/common"])
    _write_card(cfg.library_dir, "S04", topic_ids=["elem:topic/other"])
    body = client.get("/map/neighbors?paper_id=S01&lens=topic").json()
    ids = [n["paper_id"] for n in body["neighbors"]]
    assert ids and ids[0] == "S02"            # 共享罕见要素 → 最强邻
    assert "S04" not in ids                    # 零共享不入列
    assert body["neighbors"][0]["shared"]      # 带共享要素名


# -------------------------------------------------------------- first-seen ----

def test_first_seen_element_and_range(tmp_path: Path):
    client, cfg = _client(tmp_path)
    _write_card(cfg.library_dir, "S01", year=2015)
    _write_card(cfg.library_dir, "S02", year=2020)
    _write_elements_db(cfg, occ_rows=[
        ("S01", "elem:simulation/gcmc", "simulation", "GCMC", "q", "S01-RB-0001", "used", 0, "[]"),
        ("S02", "elem:simulation/gcmc", "simulation", "GCMC", "q", "S02-RB-0001", "used", 0, "[]"),
        ("S02", "elem:simulation/ml", "simulation", "ML", "q", "S02-RB-0002", "used", 0, "[]"),
    ], elem_rows=[
        ("elem:simulation/gcmc", "simulation", "gcmc", "GCMC", "[]", 0),
        ("elem:simulation/ml", "simulation", "ml", "Machine learning", "[]", 0),
    ])
    one = client.get("/map/first-seen?element_id=elem:simulation/gcmc").json()
    assert one["first_year"] == 2015 and one["first_paper"] == "S01"
    rng = client.get("/map/first-seen?year_from=2018&year_to=2025").json()
    names = [e["element_id"] for e in rng["elements"]]
    assert names == ["elem:simulation/ml"]     # gcmc 首现 2015,不在区间
    assert client.get("/map/first-seen").status_code == 400


# ------------------------------------------------- institution x elements ----

def test_institution_elements_cross(tmp_path: Path):
    client, cfg = _client(tmp_path)
    _write_card(cfg.library_dir, "S01")
    _write_card(cfg.library_dir, "S02")
    for pid, inst in (("S01", "elem:institution/mit"), ("S02", "elem:institution/other-u")):
        doc = {"paper_id": pid, "authors": [{"name": "A", "position": 1, "is_senior": True,
                                              "raw_affiliations": [], "institution_ids": [inst]}],
               "source": "openalex", "fetched_at": "2026-06-10T00:00:00+00:00"}
        (cfg.library_dir / pid / "authorship.json").write_text(json.dumps(doc), encoding="utf-8")
    _write_elements_db(cfg, occ_rows=[
        ("S01", "elem:simulation/gcmc", "simulation", "GCMC", "q", "S01-RB-0001", "used", 0, "[]"),
        ("S02", "elem:measurement/bet", "measurement", "BET", "q", "S02-RB-0001", "used", 0, "[]"),
    ], elem_rows=[
        ("elem:simulation/gcmc", "simulation", "gcmc", "GCMC", "[]", 0),
        ("elem:measurement/bet", "measurement", "bet", "BET", "[]", 0),
    ])
    body = client.get("/map/institution-elements?id=elem:institution/mit").json()
    assert body["papers"] == ["S01"]
    assert body["facets"]["simulation"][0]["name"] == "GCMC"
    assert "measurement" not in body["facets"]  # 别家的不混入


# ----------------------------------------------------- import batch marker ----

def test_import_batch_marker_feeds_arrivals(tmp_path: Path):
    cfg = AppConfig(library_dir=tmp_path / "library")

    def fake_runner(pdf_path, report):
        pid = "S" + Path(pdf_path).stem[-2:]
        _write_card(cfg.library_dir, pid, topic_ids=["elem:topic/a"])
        return pid

    client = TestClient(create_app(cfg, import_runner=fake_runner))
    for pid in ("S01", "S02", "S03"):
        _write_card(cfg.library_dir, pid, topic_ids=["elem:topic/a"])

    for stem in ("p04", "p05"):
        resp = client.post("/papers/import",
                           json={"pdf_path": f"C:/in/{stem}.pdf", "batch_id": "batch-X"})
        job = resp.json()["job_id"]
        for _ in range(100):
            if client.get(f"/jobs/{job}").json()["status"] != "running":
                break
    body = client.get("/map/arrivals").json()
    ids = {e["paper_id"] for e in body["batch"]}
    assert ids == {"S04", "S05"}               # 真实批次标记优先于 mtime 启发式
