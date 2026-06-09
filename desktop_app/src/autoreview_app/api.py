from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .config import AppConfig
from .jobs import JobRegistry
from .library_index import list_papers

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

# An import runner takes (pdf_path, progress_callback) and returns the new paper id.
ImportRunner = Callable[[Path, Callable[[str], None]], str]


class ImportRequest(BaseModel):
    pdf_path: str


def create_app(config: AppConfig, import_runner: ImportRunner | None = None) -> FastAPI:
    app = FastAPI(title="Auto Review Desktop", version="0.1.0")
    jobs = JobRegistry()
    runner = import_runner if import_runner is not None else _default_import_runner(config)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/library")
    def library() -> dict:
        return {"papers": list_papers(config.library_dir)}

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "index.html")

    @app.post("/papers/import")
    def import_paper(req: ImportRequest) -> dict:
        pdf_path = Path(req.pdf_path)
        job_id = jobs.submit(lambda report: runner(pdf_path, report))
        return {"job_id": job_id}

    @app.get("/jobs/{job_id}")
    def job_status(job_id: str) -> dict[str, Any]:
        status = jobs.get(job_id)
        if status is None:
            raise HTTPException(status_code=404, detail="unknown job")
        return status

    return app


def _default_import_runner(config: AppConfig) -> ImportRunner:
    """Wire the real importer lazily so tests that inject a runner never import it."""

    def run(pdf_path: Path, progress: Callable[[str], None]) -> str:
        from .ai.client import build_ai_client
        from .extract.pymupdf_extractor import PyMuPDFExtractor
        from .importer import import_pdf

        engine_root = Path(__file__).resolve().parents[3] / "Document_Decomposer"
        docling_dir = config.library_dir.parent / "docling_json"
        return import_pdf(
            pdf_path=pdf_path,
            library_dir=config.library_dir,
            docling_json_dir=docling_dir,
            extractor=PyMuPDFExtractor(),
            client_factory=lambda paper_dir: build_ai_client(engine_root),
            progress=progress,
        )

    return run
