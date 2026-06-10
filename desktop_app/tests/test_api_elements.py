import time
from pathlib import Path

from fastapi.testclient import TestClient

from _element_fixtures import elements_ai_response, write_reading_blocks
from _fake_ai import SequencedFakeClient
from autoreview_app.api import create_app
from autoreview_app.config import AppConfig
from autoreview_app.elements import service


def _built_library(tmp_path: Path) -> AppConfig:
    library = tmp_path / "library"
    cfg = AppConfig(library_dir=library)
    for pid in ("S90", "S91"):
        paper_dir = write_reading_blocks(library, pid)
        client = SequencedFakeClient([elements_ai_response(pid)])
        service.run_elements_for_paper(paper_dir, client, cfg)
    return cfg


def _client(cfg: AppConfig, **kw) -> TestClient:
    return TestClient(create_app(cfg, **kw))


def test_elements_endpoints_503_before_build(tmp_path: Path):
    cfg = AppConfig(library_dir=tmp_path / "library")
    (tmp_path / "library").mkdir()
    c = _client(cfg)
    assert c.get("/elements/overview").status_code == 503
    assert c.get("/elements/stats?facet=characterization").status_code == 503


def test_overview_stats_search_detail_cooccurrence(tmp_path: Path):
    cfg = _built_library(tmp_path)
    c = _client(cfg)
    ov = c.get("/elements/overview").json()
    assert ov["library_papers"] == 2
    stats = c.get("/elements/stats?facet=characterization").json()
    assert stats["items"][0]["papers"] == 2
    hits = c.get("/elements?q=xrd").json()["elements"]
    assert hits and hits[0]["facet"] == "characterization"
    detail = c.get("/elements/characterization/x-ray-diffraction").json()
    assert detail["paper_count"] == 2 and detail["papers"][0]["quotes"]
    co = c.get("/elements/preparation/ball-milling/cooccurrence").json()
    assert co["m"] == 2
    assert c.get("/elements/characterization/nope").status_code == 404


def test_combination_query_and_paper_elements(tmp_path: Path):
    cfg = _built_library(tmp_path)
    c = _client(cfg)
    res = c.post("/elements/query", json={"element_ids": [
        "elem:characterization/x-ray-diffraction", "elem:preparation/ball-milling",
        "elem:characterization/x-ray-diffraction"]}).json()  # duplicate id must be deduped by API
    assert {p["paper_id"] for p in res["papers"]} == {"S90", "S91"}
    pe = c.get("/papers/S90/elements").json()
    assert {g["facet"] for g in pe["groups"]} == {"characterization", "preparation"}


def test_put_rename_and_merge_rebuilds_index(tmp_path: Path):
    cfg = _built_library(tmp_path)
    c = _client(cfg)
    r = c.put("/elements/characterization/x-ray-diffraction",
              json={"display_name": "X 射线衍射"})
    assert r.status_code == 200 and r.json()["entry"]["display_name"] == "X 射线衍射"
    stats = c.get("/elements/stats?facet=characterization").json()
    assert stats["items"][0]["display_name"] == "X 射线衍射"
    log = cfg.elements_log_path.read_text(encoding="utf-8")
    assert '"rename"' in log and '"human"' in log
    assert c.put("/elements/characterization/nope", json={"display_name": "x"}).status_code == 404
    bad = c.put("/elements/characterization/x-ray-diffraction", json={"merge_into": "elem:characterization/ghost"})
    assert bad.status_code == 400
    self_merge = c.put("/elements/characterization/x-ray-diffraction",
                       json={"merge_into": "elem:characterization/x-ray-diffraction"})
    assert self_merge.status_code == 400


def test_coverage_and_bootstrap_job(tmp_path: Path):
    library = tmp_path / "library"
    cfg = AppConfig(library_dir=library)
    write_reading_blocks(library, "S90")

    def fake_bootstrap(report):
        report("bootstrapping")
        return {"papers_indexed": 1}

    c = _client(cfg, elements_bootstrap_runner=fake_bootstrap)
    cov = c.get("/elements/coverage").json()
    assert cov["papers"] == 1 and cov["pending"] == ["S90"]
    job_id = c.post("/elements/bootstrap").json()["job_id"]
    for _ in range(50):
        status = c.get(f"/jobs/{job_id}").json()
        if status["status"] != "running":
            break
        time.sleep(0.05)
    assert status["status"] == "succeeded"
    assert status["result"]["papers_indexed"] == 1
