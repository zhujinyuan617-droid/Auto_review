from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from .config import AppConfig
from .library_index import list_papers

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


def create_app(config: AppConfig) -> FastAPI:
    app = FastAPI(title="Auto Review Desktop", version="0.1.0")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/library")
    def library() -> dict:
        return {"papers": list_papers(config.library_dir)}

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "index.html")

    return app
