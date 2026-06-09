from pathlib import Path

from fastapi.testclient import TestClient

from _library_fixtures import write_card

from autoreview_app.api import create_app
from autoreview_app.config import AppConfig
from autoreview_app.groups.store import save_authors


def test_groups_endpoint_clusters_by_senior_author(tmp_path: Path):
    library = tmp_path / "library"
    write_card(library, "S1", title="A", doi="10.1/a")
    write_card(library, "S2", title="B", doi="10.1/b")
    config = AppConfig(library_dir=library)

    save_authors(config.authors_db, "10.1/a", ["Junior, X", "Lee, Min"])
    save_authors(config.authors_db, "10.1/b", ["Other, Y", "Lee, M."])

    client = TestClient(create_app(config))
    resp = client.get("/groups")
    assert resp.status_code == 200
    groups = resp.json()["groups"]
    assert len(groups) == 1
    g = groups[0]
    assert g["anchor_identity"] == "lee_m"
    assert {p["paper_id"] for p in g["papers"]} == {"S1", "S2"}


def test_groups_endpoint_empty_when_no_authors(tmp_path: Path):
    library = tmp_path / "library"
    write_card(library, "S1", title="A", doi="10.1/a")
    client = TestClient(create_app(AppConfig(library_dir=library)))
    assert client.get("/groups").json() == {"groups": []}
