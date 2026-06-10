from __future__ import annotations

import json
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
from .elements import service as elements_service
from .map import service as map_service
from docdecomp.element_index import (
    build_index,
    get_element,
    paper_elements,
    query_combination,
    query_cooccurrence,
    query_overview,
    query_stats,
    refine_counts,
    search_elements,
)
from docdecomp.element_registry import (
    add_alias as registry_add_alias,
    load_registry,
    merge_entries,
    rename_entry,
    resolve_id,
    save_registry,
)

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

# An import runner takes (pdf_path, progress_callback) and returns the new paper id.
ImportRunner = Callable[[Path, Callable[[str], None]], str]

# A search runner takes a query string and returns a list of record dicts.
SearchRunner = Callable[[str], list[dict[str, Any]]]

# A draft runner takes (brief, progress) and returns a writing-loop summary dict.
DraftRunner = Callable[[dict[str, Any], Callable[[str], None]], dict[str, Any]]

# An author-populate runner takes (progress) and returns {found, skipped}.
AuthorPopulateRunner = Callable[[Callable[[str], None]], dict[str, Any]]

# An authorship runner takes (progress) and returns {populated, pdf_fallback, skipped_no_doi, failed}.
AuthorshipRunner = Callable[[Callable[[str], None]], dict[str, Any]]

# A bootstrap runner takes (progress) and returns a summary dict.
BootstrapRunner = Callable[[Callable[[str], None]], dict[str, Any]]


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


class ParallelRequest(BaseModel):
    flash: int
    pro: int


class ElementsQuery(BaseModel):
    element_ids: list[str]
    role: str = "used"


class ElementUpdate(BaseModel):
    display_name: str | None = None
    add_alias: str | None = None
    merge_into: str | None = None


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
    elements_bootstrap_runner: BootstrapRunner | None = None,
    authorship_runner: AuthorshipRunner | None = None,
) -> FastAPI:
    app = FastAPI(title="Auto Review Desktop", version="0.1.0")
    jobs = JobRegistry()
    runner = import_runner if import_runner is not None else _default_import_runner(config)
    if import_runner is None:
        runner = _wrap_import_with_elements(runner, config)
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

    @app.get("/settings/parallel")
    def get_parallel_settings() -> dict[str, Any]:
        values = app_settings.get_parallel(config.app_settings_path)
        return {**values, "limits": app_settings.PARALLEL_LIMITS}

    @app.put("/settings/parallel")
    def put_parallel_settings(req: ParallelRequest) -> dict[str, Any]:
        try:
            stored = app_settings.set_parallel(config.app_settings_path, req.flash, req.pro)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {**stored, "limits": app_settings.PARALLEL_LIMITS}

    @app.get("/settings/setup-manifest")
    def setup_manifest() -> dict[str, Any]:
        return consent_summary()

    def _elements_db_or_503() -> Path:
        if not config.elements_db.exists():
            raise HTTPException(status_code=503, detail="elements index not built")
        return config.elements_db

    def _role(role: str) -> str | None:
        # query param convention: "used"(默认) / "mentioned" / "all"(=不过滤)
        return None if role == "all" else role

    @app.get("/elements/overview")
    def elements_overview(top_n: int = 5, role: str = "used") -> dict:
        return query_overview(_elements_db_or_503(), top_n=top_n, role=_role(role))

    @app.get("/elements/coverage")
    def elements_coverage() -> dict:
        return elements_service.coverage(config)

    @app.get("/elements/stats")
    def elements_stats(facet: str, role: str = "used") -> dict:
        return {"facet": facet, "items": query_stats(_elements_db_or_503(), facet, _role(role))}

    @app.get("/elements")
    def elements_search(q: str = "", facet: str | None = None) -> dict:
        return {"elements": search_elements(_elements_db_or_503(), q, facet)}

    @app.post("/elements/query")
    def elements_query(req: ElementsQuery) -> dict:
        ids = list(dict.fromkeys(req.element_ids))  # dedup, preserve order (engine requires unique ids)
        return query_combination(_elements_db_or_503(), ids, req.role)

    @app.post("/elements/refine")
    def elements_refine(req: ElementsQuery) -> dict[str, Any]:
        # 检索屏联动计数(spec §4c):一次返回交集命中论文 + 全树条件计数
        papers, counts = refine_counts(_elements_db_or_503(), req.element_ids, _role(req.role))
        return {"papers": papers, "counts": counts}

    @app.post("/elements/bootstrap")
    def elements_bootstrap() -> dict:
        _runner = elements_bootstrap_runner or _default_bootstrap_runner(config)
        return {"job_id": jobs.submit(_runner)}

    @app.get("/elements/{facet}/{slug}/cooccurrence")
    def element_cooccurrence(facet: str, slug: str, role: str = "used") -> dict:
        return query_cooccurrence(_elements_db_or_503(), facet, slug, role)

    @app.get("/elements/{facet}/{slug}")
    def element_detail(facet: str, slug: str, role: str = "all") -> dict:
        detail = get_element(_elements_db_or_503(), facet, slug, role=_role(role))
        if detail is None:
            raise HTTPException(status_code=404, detail="unknown element")
        return detail

    @app.put("/elements/{facet}/{slug}")
    def element_update(facet: str, slug: str, req: ElementUpdate) -> dict:
        if not config.elements_registry_path.exists():
            raise HTTPException(status_code=503, detail="elements index not built")
        registry = load_registry(config.elements_registry_path)
        eid = f"elem:{facet}/{slug}"
        if eid not in registry["entries"]:
            raise HTTPException(status_code=404, detail="unknown element")
        if req.merge_into:
            if req.display_name or req.add_alias:
                raise HTTPException(
                    status_code=400, detail="merge_into cannot be combined with other operations"
                )
            if req.merge_into not in registry["entries"]:
                raise HTTPException(status_code=400, detail="merge target unknown")
            if resolve_id(registry, req.merge_into) == eid:
                raise HTTPException(status_code=400, detail="cannot merge entry into itself")
        if req.display_name:
            rename_entry(registry, eid, req.display_name, config.elements_log_path)
        if req.add_alias:
            registry_add_alias(registry, eid, req.add_alias, "human", config.elements_log_path)
        if req.merge_into:
            try:
                merge_entries(registry, eid, req.merge_into, "human", config.elements_log_path)
            except ValueError as exc:  # defense in depth: engine guards map to 400
                raise HTTPException(status_code=400, detail=str(exc))
        save_registry(config.elements_registry_path, registry)
        build_index(config.library_dir, registry, config.elements_db)
        return {"entry": registry["entries"][eid]}

    @app.get("/papers/{paper_id}/elements")
    def paper_elements_route(paper_id: str) -> dict:
        return paper_elements(_elements_db_or_503(), paper_id)

    @app.post("/authorship/populate")
    def authorship_populate(force: bool = False) -> dict:
        runner = authorship_runner if authorship_runner is not None else _default_authorship_runner(config, force)
        return {"job_id": jobs.submit(runner)}

    @app.get("/authorship/coverage")
    def authorship_coverage() -> dict:
        papers = [p.parent for p in sorted(config.library_dir.glob("*/literature_card.json"))]
        done = [p.name for p in papers if (p / "authorship.json").exists()]
        return {"papers": len(papers), "with_authorship": len(done),
                "pending": [p.name for p in papers if p.name not in set(done)]}

    # ---- 图墙(SP-Map Task 7):Docling 已抽取图片的浏览;零 AI ----

    _FIGURE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp")

    def _paper_dir_or_404(paper_id: str) -> Path:
        d = (config.library_dir / paper_id)
        if "/" in paper_id or "\\" in paper_id or ".." in paper_id or not d.is_dir():
            raise HTTPException(status_code=404, detail="paper not found")
        return d

    @app.get("/papers/{paper_id}/figures")
    def paper_figures(paper_id: str) -> dict[str, Any]:
        fig_dir = _paper_dir_or_404(paper_id) / "figures"
        if not fig_dir.is_dir():
            return {"paper_id": paper_id, "figures": []}
        names = sorted(
            p.name for p in fig_dir.iterdir()
            if p.is_file() and p.suffix.lower() in _FIGURE_EXTS
        )
        return {"paper_id": paper_id, "figures": names}

    @app.get("/papers/{paper_id}/figures/{name}")
    def paper_figure_file(paper_id: str, name: str):
        fig_dir = _paper_dir_or_404(paper_id) / "figures"
        target = fig_dir / name
        if (
            "/" in name or "\\" in name or ".." in name
            or not target.is_file() or target.parent != fig_dir
            or target.suffix.lower() not in _FIGURE_EXTS
        ):
            raise HTTPException(status_code=404, detail="figure not found")
        return FileResponse(target)

    # ---- 知识地图(SP-Map):镜头布局 / 着陆 / 重排 / 阅读路线;全机械零 AI ----

    def _check_lens(lens: str) -> None:
        if lens not in map_service.ALL_LENSES:
            raise HTTPException(status_code=400, detail=f"unknown lens: {lens}")
        if lens in ("method", "material"):
            _elements_db_or_503()  # 要素镜头依赖索引;topic/time/institution 不依赖

    @app.get("/map")
    def map_lens(lens: str = "topic") -> dict[str, Any]:
        _check_lens(lens)
        return map_service.lens_payload(config, lens)

    @app.post("/map/relayout")
    def map_relayout(lens: str = "topic") -> dict[str, Any]:
        _check_lens(lens)
        return map_service.relayout(config, lens)

    @app.get("/map/arrivals")
    def map_arrivals() -> dict[str, Any]:
        return map_service.arrivals(config)

    @app.get("/map/route")
    def map_route(lens: str = "topic", cluster: str = "") -> dict[str, Any]:
        _check_lens(lens)
        return map_service.route(config, lens, cluster)

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


def _default_authorship_runner(config: AppConfig, force: bool = False) -> AuthorshipRunner:
    def run(progress: Callable[[str], None]) -> dict[str, Any]:
        import time as _time
        from .discovery.sources.openalex import OpenAlexSource
        from .discovery.transport import UrllibTransport
        from .groups.authorship import populate_authorship
        source = OpenAlexSource()
        transport = UrllibTransport()

        def _polite_fetch(doi: str) -> dict[str, Any] | None:
            _time.sleep(0.2)
            return source.fetch_authorship(doi, transport)

        return populate_authorship(
            config.library_dir, config.institutions_data_dir, _polite_fetch, progress, force=force,
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


def _default_bootstrap_runner(config: AppConfig) -> BootstrapRunner:
    def run(report: Callable[[str], None]) -> dict[str, Any]:
        from .ai.client import build_ai_client
        client = build_ai_client(elements_service.engine_root())
        # 并行度来自设置页(按所用模型的档位取值;flash/pro 上限见 settings.PARALLEL_LIMITS)
        parallel = app_settings.parallel_for_model(config.app_settings_path, client.config.model)
        return elements_service.run_bootstrap(config, client, report, parallel=parallel)
    return run


def _wrap_import_with_elements(base: ImportRunner, config: AppConfig) -> ImportRunner:
    """After a successful default import, extract+index elements. Failures mark
    the paper pending (elements_pending.json) instead of failing the job (P0)."""
    def run(pdf_path: Path, report: Callable[[str], None]) -> str:
        paper_id = base(pdf_path, report)
        paper_dir = config.library_dir / paper_id
        if (paper_dir / "language_gate.json").exists():
            return paper_id
        try:
            from .ai.client import build_ai_client
            client = build_ai_client(elements_service.engine_root())
            elements_service.run_elements_for_paper(paper_dir, client, config, report)
        except Exception as exc:  # noqa: BLE001 — graceful: paper stays usable
            report(f"elements pending: {type(exc).__name__}")
            (paper_dir / "elements_pending.json").write_text(
                json.dumps({"error": str(exc)}, ensure_ascii=False), encoding="utf-8")
        return paper_id
    return run
