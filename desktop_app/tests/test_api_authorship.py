"""Tests for /authorship/populate and /authorship/coverage endpoints."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # for _library_fixtures

from _library_fixtures import write_card

from fastapi.testclient import TestClient

from autoreview_app.api import create_app
from autoreview_app.config import AppConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_authorship(paper_id: str) -> dict:
    return {
        "paper_id": paper_id,
        "authors": [],
        "source": "openalex",
        "fetched_at": "2026-01-01T00:00:00+00:00",
    }


def _write_authorship(paper_dir: Path, doc: dict) -> None:
    paper_dir.mkdir(parents=True, exist_ok=True)
    (paper_dir / "authorship.json").write_text(
        json.dumps(doc, ensure_ascii=False), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Tests: injected runner lifecycle (mirrors test_api_elements.py pattern)
# ---------------------------------------------------------------------------

def test_authorship_populate_runs_injected_runner(tmp_path: Path):
    lib = tmp_path / "library"
    lib.mkdir(parents=True)

    def fake_runner(progress):
        progress("processing 1/1 S01")
        return {"populated": 1, "pdf_fallback": 0, "skipped_no_doi": 0, "failed": 0}

    client = TestClient(create_app(AppConfig(library_dir=lib), authorship_runner=fake_runner))
    resp = client.post("/authorship/populate")
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]
    assert job_id

    # Poll until done
    for _ in range(50):
        status = client.get(f"/jobs/{job_id}").json()
        if status["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.05)

    assert status["status"] == "succeeded"
    result = status["result"]
    assert result["populated"] == 1
    assert result["pdf_fallback"] == 0
    assert result["skipped_no_doi"] == 0
    assert result["failed"] == 0


def test_authorship_populate_returns_job_id(tmp_path: Path):
    lib = tmp_path / "library"
    lib.mkdir(parents=True)

    def fake_runner(progress):
        return {"populated": 0, "pdf_fallback": 0, "skipped_no_doi": 0, "failed": 0}

    client = TestClient(create_app(AppConfig(library_dir=lib), authorship_runner=fake_runner))
    resp = client.post("/authorship/populate")
    assert resp.status_code == 200
    assert "job_id" in resp.json()


# ---------------------------------------------------------------------------
# Tests: coverage endpoint
# ---------------------------------------------------------------------------

def test_authorship_coverage_no_papers(tmp_path: Path):
    lib = tmp_path / "library"
    lib.mkdir(parents=True)
    client = TestClient(create_app(AppConfig(library_dir=lib)))
    resp = client.get("/authorship/coverage")
    assert resp.status_code == 200
    data = resp.json()
    assert data["papers"] == 0
    assert data["with_authorship"] == 0
    assert data["pending"] == []


def test_authorship_coverage_counts_done_and_pending(tmp_path: Path):
    lib = tmp_path / "library"
    write_card(lib, "S01", title="A", doi="10.1/a")
    write_card(lib, "S02", title="B", doi="10.1/b")
    write_card(lib, "S03", title="C", doi="10.1/c")

    # S01 has authorship.json; S02, S03 do not
    _write_authorship(lib / "S01", _minimal_authorship("S01"))

    client = TestClient(create_app(AppConfig(library_dir=lib)))
    resp = client.get("/authorship/coverage")
    assert resp.status_code == 200
    data = resp.json()
    assert data["papers"] == 3
    assert data["with_authorship"] == 1
    assert set(data["pending"]) == {"S02", "S03"}


def test_authorship_coverage_all_done(tmp_path: Path):
    lib = tmp_path / "library"
    for pid in ("S01", "S02"):
        write_card(lib, pid, title=pid, doi=f"10.1/{pid}")
        _write_authorship(lib / pid, _minimal_authorship(pid))

    client = TestClient(create_app(AppConfig(library_dir=lib)))
    data = client.get("/authorship/coverage").json()
    assert data["papers"] == 2
    assert data["with_authorship"] == 2
    assert data["pending"] == []


def test_authorship_populate_job_failure_reported(tmp_path: Path):
    lib = tmp_path / "library"
    lib.mkdir(parents=True)

    def failing_runner(progress):
        raise RuntimeError("something went wrong")

    client = TestClient(create_app(AppConfig(library_dir=lib), authorship_runner=failing_runner))
    resp = client.post("/authorship/populate")
    job_id = resp.json()["job_id"]

    for _ in range(50):
        status = client.get(f"/jobs/{job_id}").json()
        if status["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.05)

    assert status["status"] == "failed"
