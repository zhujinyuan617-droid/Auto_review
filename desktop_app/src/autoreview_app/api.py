from __future__ import annotations

from fastapi import FastAPI

from .config import AppConfig
from .library_index import list_papers


def create_app(config: AppConfig) -> FastAPI:
    app = FastAPI(title="Auto Review Desktop", version="0.1.0")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/library")
    def library() -> dict:
        return {"papers": list_papers(config.library_dir)}

    return app
