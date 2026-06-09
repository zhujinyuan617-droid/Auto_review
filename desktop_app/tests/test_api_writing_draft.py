import time
from pathlib import Path

from fastapi.testclient import TestClient

from autoreview_app.api import create_app
from autoreview_app.config import AppConfig


def _client(tmp_path: Path, draft_runner):
    app = create_app(AppConfig(library_dir=tmp_path / "library"), draft_runner=draft_runner)
    return TestClient(app)


def test_draft_runs_as_job(tmp_path: Path):
    def fake_runner(brief, progress):
        progress("writing")
        return {"status": "internal_acceptance_gate", "rounds": 1}

    client = _client(tmp_path, fake_runner)
    resp = client.post("/writing/draft", json={"brief": {"topic": "methane"}})
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


def test_draft_runner_not_configured_503(tmp_path: Path):
    app = create_app(AppConfig(library_dir=tmp_path / "library"))  # no draft_runner
    client = TestClient(app)
    assert client.post("/writing/draft", json={"brief": {}}).status_code == 503
