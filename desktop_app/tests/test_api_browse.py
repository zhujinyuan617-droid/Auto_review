import json
from pathlib import Path

from fastapi.testclient import TestClient

from _library_fixtures import write_card

from autoreview_app.api import create_app
from autoreview_app.config import AppConfig


def _client(library: Path, edges_path: Path | None = None):
    config = AppConfig(library_dir=library, edges_path=edges_path)
    return TestClient(create_app(config))


def test_library_papers_lists_indexed_cards(tmp_path: Path):
    library = tmp_path / "library"
    write_card(library, "S1", title="Alpha", doi="10.1/a", tags=["methane"])
    write_card(library, "S2", title="Beta")

    resp = _client(library).get("/library/papers")
    assert resp.status_code == 200
    papers = resp.json()["papers"]
    assert {p["paper_id"] for p in papers} == {"S1", "S2"}
    s1 = next(p for p in papers if p["paper_id"] == "S1")
    assert s1["title"] == "Alpha"
    assert s1["research_objects"] == ["methane"]


def test_paper_detail(tmp_path: Path):
    library = tmp_path / "library"
    write_card(library, "S1", title="Alpha")
    client = _client(library)
    assert client.get("/papers/S1").json()["title"] == "Alpha"
    assert client.get("/papers/missing").status_code == 404


def test_network_reads_edges(tmp_path: Path):
    library = tmp_path / "library"
    write_card(library, "S1", title="A")
    edges_path = tmp_path / "edges.json"
    edges_path.write_text(json.dumps({
        "relation_counts": {"supports": 1},
        "edges": [{"a": "S1", "b": "S2", "relation": "supports"}],
    }), encoding="utf-8")

    resp = _client(library, edges_path=edges_path).get("/network")
    assert resp.status_code == 200
    assert resp.json()["n_edges"] == 1


def test_network_missing_edges_is_empty(tmp_path: Path):
    library = tmp_path / "library"
    resp = _client(library, edges_path=tmp_path / "nope.json").get("/network")
    assert resp.json() == {"edges": [], "relation_counts": {}, "n_edges": 0}
