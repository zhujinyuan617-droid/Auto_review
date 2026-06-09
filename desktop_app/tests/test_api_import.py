from pathlib import Path

from fastapi.testclient import TestClient

from autoreview_app.api import create_app
from autoreview_app.config import AppConfig


def _client(tmp_path: Path, import_runner):
    app = create_app(AppConfig(library_dir=tmp_path / "library"), import_runner=import_runner)
    return TestClient(app)


def test_import_starts_a_job_and_reports_success(tmp_path: Path):
    def fake_runner(pdf_path, progress):
        progress("working")
        return "S1"

    client = _client(tmp_path, fake_runner)
    resp = client.post("/papers/import", json={"pdf_path": str(tmp_path / "x.pdf")})
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    import time
    status = None
    for _ in range(200):
        status = client.get(f"/jobs/{job_id}").json()
        if status["status"] in {"succeeded", "failed"}:
            break
        time.sleep(0.02)
    assert status is not None and status["status"] == "succeeded", f"job did not finish: {status}"
    assert status["result"] == "S1"


def test_unknown_job_404(tmp_path: Path):
    client = _client(tmp_path, lambda pdf_path, progress: "S1")
    assert client.get("/jobs/nope").status_code == 404
