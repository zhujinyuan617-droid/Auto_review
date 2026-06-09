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


def test_groups_build_runs_injected_runner(tmp_path):
    from autoreview_app.api import create_app
    from autoreview_app.config import AppConfig
    from fastapi.testclient import TestClient

    def fake_runner(progress):
        progress("1/1 S01")
        return {"found": 1, "skipped": 0}

    app = create_app(AppConfig(library_dir=tmp_path / "library"), author_populate_runner=fake_runner)
    client = TestClient(app)
    r = client.post("/groups/build")
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    status = client.get(f"/jobs/{job_id}").json()
    # job runs on a thread; poll a few times
    import time
    for _ in range(50):
        status = client.get(f"/jobs/{job_id}").json()
        if status["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.05)
    assert status["status"] == "succeeded"
    assert status["result"]["found"] == 1
