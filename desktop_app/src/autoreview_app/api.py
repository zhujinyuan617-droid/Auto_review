from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import AppConfig
from . import settings as app_settings
from .packaging.installer_manifest import consent_summary
from .decomposition import assemble_decomposition
from .discovery.records import CitationRecord
from .discovery.ris import parse_ris_text
from .jobs import JobRegistry
from .library_index import list_papers
from .network.edges import load_edges
from .groups.cluster import cluster_papers
from .groups.store import load_authors
from .store.sqlite_index import get_paper, query_papers, reindex
from .writing.gates import check_draft
from .writing.ideation import load_angles

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

# An import runner takes (pdf_path, progress_callback) and returns the new paper id.
ImportRunner = Callable[[Path, Callable[[str], None]], str]

# A search runner takes a query string and returns a list of record dicts.
SearchRunner = Callable[[str], list[dict[str, Any]]]

# A draft runner takes (brief, progress) and returns a writing-loop summary dict.
DraftRunner = Callable[[dict[str, Any], Callable[[str], None]], dict[str, Any]]

# An author-populate runner takes (progress) and returns {found, skipped}.
AuthorPopulateRunner = Callable[[Callable[[str], None]], dict[str, Any]]


class ImportRequest(BaseModel):
    pdf_path: str


class RisRequest(BaseModel):
    text: str


class SearchRequest(BaseModel):
    query: str


class DraftCheckRequest(BaseModel):
    draft: str


class DraftSelection(BaseModel):
    topic: str = ""
    paper_ids: list[str] = []
    concepts: list[str] = []
    section_count: int = 1
    word_target: int = 300


class ApiKeyRequest(BaseModel):
    api_key: str


def _record_to_dict(rec: CitationRecord) -> dict[str, Any]:
    return {
        "title": rec.title, "doi": rec.doi, "year": rec.year,
        "journal": rec.journal, "authors": list(rec.authors), "pdf_url": rec.pdf_url,
    }


def create_app(
    config: AppConfig,
    import_runner: ImportRunner | None = None,
    search_runner: SearchRunner | None = None,
    draft_runner: DraftRunner | None = None,
    author_populate_runner: AuthorPopulateRunner | None = None,
) -> FastAPI:
    app = FastAPI(title="Auto Review Desktop", version="0.1.0")
    jobs = JobRegistry()
    runner = import_runner if import_runner is not None else _default_import_runner(config)
    populate_runner = author_populate_runner if author_populate_runner is not None else _default_author_populate_runner(config)
    search_exec = search_runner if search_runner is not None else _default_search_runner(config)
    draft_exec = draft_runner if draft_runner is not None else _default_draft_runner(config)

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

    @app.post("/discovery/import-ris")
    def import_ris(req: RisRequest) -> dict:
        records = parse_ris_text(req.text)
        return {"records": [_record_to_dict(r) for r in records]}

    @app.post("/discovery/search")
    def search(req: SearchRequest) -> dict:
        return {"records": search_exec(req.query)}

    @app.get("/library/papers")
    def library_papers() -> dict:
        reindex(config.library_dir, config.index_db)
        return {"papers": query_papers(config.index_db)}

    @app.get("/papers/{paper_id}")
    def paper_detail(paper_id: str) -> dict[str, Any]:
        reindex(config.library_dir, config.index_db)
        paper = get_paper(config.index_db, paper_id)
        if paper is None:
            raise HTTPException(status_code=404, detail="unknown paper")
        return paper

    @app.get("/papers/{paper_id}/decomposition")
    def paper_decomposition(paper_id: str) -> dict[str, Any]:
        paper_dir = config.library_dir / paper_id
        if not paper_dir.is_dir():
            raise HTTPException(status_code=404, detail="unknown paper")
        return assemble_decomposition(paper_dir)

    @app.get("/network")
    def network() -> dict[str, Any]:
        if config.edges_path is None:
            return {"edges": [], "relation_counts": {}, "n_edges": 0}
        return load_edges(config.edges_path)

    @app.get("/groups")
    def groups() -> dict:
        reindex(config.library_dir, config.index_db)
        papers = query_papers(config.index_db)
        authors_by_doi = load_authors(config.authors_db)
        return {"groups": cluster_papers(papers, authors_by_doi)}

    @app.post("/groups/build")
    def groups_build() -> dict:
        job_id = jobs.submit(lambda report: populate_runner(report))
        return {"job_id": job_id}

    @app.post("/writing/check")
    def writing_check(req: DraftCheckRequest) -> dict[str, Any]:
        return check_draft(req.draft)

    @app.post("/writing/draft")
    def writing_draft(req: DraftSelection) -> dict:
        job_id = jobs.submit(lambda report: draft_exec(req.model_dump(), report))
        return {"job_id": job_id}

    @app.get("/writing/angles")
    def writing_angles() -> dict[str, Any]:
        if config.edges_path is None and config.concept_index_path is None:
            return {"tension": [], "gaps": [], "synthesis": []}
        edges_path = config.edges_path or (config.library_dir.parent / "edges.json")
        cidx_path = config.concept_index_path or (config.library_dir.parent / "concept_index.json")
        return load_angles(edges_path, cidx_path)

    @app.get("/settings/apikey")
    def get_apikey() -> dict:
        return {"configured": app_settings.has_api_key()}

    @app.post("/settings/apikey")
    def set_apikey(req: ApiKeyRequest) -> dict:
        try:
            app_settings.set_api_key(req.api_key)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"configured": True}

    @app.delete("/settings/apikey")
    def delete_apikey() -> dict:
        if app_settings.has_api_key():
            app_settings.clear_api_key()
        return {"configured": False}

    @app.get("/settings/setup-manifest")
    def setup_manifest() -> dict[str, Any]:
        return consent_summary()

    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR), name="assets")
    return app


def _default_author_populate_runner(config: AppConfig) -> AuthorPopulateRunner:
    def run(progress: Callable[[str], None]) -> dict[str, Any]:
        from .discovery.sources.crossref import CrossrefSource
        from .discovery.transport import UrllibTransport
        from .groups.populate import populate_authors
        source = CrossrefSource()
        transport = UrllibTransport()
        return populate_authors(
            config.library_dir, config.authors_db,
            lambda doi: source.fetch_by_doi(doi, transport), progress,
        )
    return run


def _default_search_runner(config: AppConfig) -> SearchRunner:
    """Wire a live Crossref search lazily so tests that inject a runner never hit the network."""

    def run(query: str) -> list[dict[str, Any]]:
        from .discovery.sources.crossref import CrossrefSource
        from .discovery.transport import UrllibTransport

        records = CrossrefSource().search(query, UrllibTransport())
        return [_record_to_dict(r) for r in records]

    return run


def _default_draft_runner(config: AppConfig) -> DraftRunner:
    """Wire the real draft runner lazily (engine brief build + writing loop + real AI client)."""

    def run(selection: dict[str, Any], progress: Callable[[str], None]) -> dict[str, Any]:
        from .ai.client import build_ai_client
        from .writing.draft_runner import run_draft

        engine_root = Path(__file__).resolve().parents[3] / "Document_Decomposer"
        return run_draft(selection, config.library_dir, lambda: build_ai_client(engine_root), progress)

    return run


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
