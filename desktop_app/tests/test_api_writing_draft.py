import time
from pathlib import Path

from fastapi.testclient import TestClient

from autoreview_app.api import create_app, _default_draft_runner
from autoreview_app.config import AppConfig


def _client(tmp_path: Path, draft_runner):
    app = create_app(AppConfig(library_dir=tmp_path / "library"), draft_runner=draft_runner)
    return TestClient(app)


def test_draft_runs_as_job(tmp_path: Path):
    def fake_runner(selection, progress):
        progress("writing")
        return {"status": "internal_acceptance_gate", "rounds": 1, "selection": selection}

    client = _client(tmp_path, fake_runner)
    resp = client.post("/writing/draft", json={"topic": "methane", "paper_ids": ["S09"]})
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    status = None
    for _ in range(200):
        status = client.get(f"/jobs/{job_id}").json()
        if status["status"] in {"succeeded", "failed"}:
            break
        time.sleep(0.02)
    assert status is not None and status["status"] == "succeeded", status
    assert status["result"]["status"] == "internal_acceptance_gate"
    assert status["result"]["selection"]["paper_ids"] == ["S09"]


def test_default_draft_runner_is_callable(tmp_path: Path):
    runner = _default_draft_runner(AppConfig(library_dir=tmp_path / "library"))
    assert callable(runner)
