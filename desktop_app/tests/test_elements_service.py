import json
import threading
from pathlib import Path

from _element_fixtures import elements_ai_response, write_reading_blocks
from _fake_ai import SequencedFakeClient
from autoreview_app.config import AppConfig
from autoreview_app.elements import service


def test_config_elements_paths(tmp_path: Path):
    cfg = AppConfig(library_dir=tmp_path / "library")
    assert cfg.elements_data_dir == tmp_path / "data" / "elements"
    assert cfg.elements_db == tmp_path / "data" / "elements" / "elements_index.sqlite"
    assert cfg.elements_registry_path == tmp_path / "data" / "elements" / "registry.json"
    assert cfg.elements_log_path == tmp_path / "data" / "elements" / "registry_log.jsonl"


def test_run_elements_for_paper_extracts_matches_and_indexes(tmp_path: Path):
    library = tmp_path / "library"
    paper_dir = write_reading_blocks(library, "S90")
    cfg = AppConfig(library_dir=library)
    client = SequencedFakeClient([elements_ai_response("S90")])
    stats = service.run_elements_for_paper(paper_dir, client, cfg)
    data = json.loads((paper_dir / "elements.json").read_text(encoding="utf-8"))
    assert all(o["canonical_id"] for o in data["occurrences"])
    assert cfg.elements_db.exists()
    assert cfg.elements_registry_path.exists()
    assert stats["occurrences"] == 2


def test_coverage_counts(tmp_path: Path):
    library = tmp_path / "library"
    write_reading_blocks(library, "S90")
    paper91 = write_reading_blocks(library, "S91")
    cfg = AppConfig(library_dir=library)
    client = SequencedFakeClient([elements_ai_response("S91")])
    service.run_elements_for_paper(paper91, client, cfg)
    cov = service.coverage(cfg)
    assert cov["papers"] == 2 and cov["with_elements"] == 1
    assert cov["pending"] == ["S90"]


def test_bootstrap_second_run_skips_reconsolidation(tmp_path: Path):
    library = tmp_path / "library"
    cfg = AppConfig(library_dir=library)
    write_reading_blocks(library, "S90")
    client1 = SequencedFakeClient([
        elements_ai_response("S90"),
        {"groups": []},  # consolidation chunk: characterization(空组,机械兜底命中种子)
        {"groups": []},  # consolidation chunk: preparation
    ])
    service.run_bootstrap(cfg, client1, lambda m: None)
    assert cfg.elements_registry_path.exists()

    write_reading_blocks(library, "S91")
    client2 = SequencedFakeClient([elements_ai_response("S91")])
    summary = service.run_bootstrap(cfg, client2, lambda m: None)
    assert summary["papers_indexed"] == 2
    # 第二次只允许 1 次 AI 调用(S91 抽取);surfaces 全部 exact/alias 命中种子,
    # 不发生匹配 AI 调用,更绝不重新归并。
    assert client2.call_count == 1


def test_run_elements_for_paper_with_zero_occurrences(tmp_path: Path):
    library = tmp_path / "library"
    paper_dir = write_reading_blocks(library, "S90")
    cfg = AppConfig(library_dir=library)
    client = SequencedFakeClient([{"paper_id": "S90", "elements": []}])
    stats = service.run_elements_for_paper(paper_dir, client, cfg)
    assert stats == {"occurrences": 0, "dropped": 0}
    assert (paper_dir / "elements.json").exists()
    assert cfg.elements_db.exists()  # index built even when empty


# ---------------------------------------------------------------------------
# R8: parallel extraction + card-tag derivation tests
# ---------------------------------------------------------------------------

class _PaperKeyedFakeClient:
    """Thread-safe fake AI client for parallel bootstrap tests.

    For extraction calls (user message starts with "Extract all research elements"):
      - parses paper_id from JSON payload and returns the canned response
      - raises ValueError for paper_ids registered as 'fail'
    For any other call (consolidation, matching etc.): returns {"groups": []}.
    """

    def __init__(self, responses: dict, fail_ids: set | None = None):
        self._responses = responses      # paper_id -> dict
        self._fail_ids = fail_ids or set()
        self._lock = threading.Lock()
        self._calls: list[str] = []      # paper_ids seen, for assertion

    def chat_json(self, messages: list[dict], response_schema_hint: str) -> dict:
        user_content = messages[1]["content"]
        if not user_content.startswith("Extract all research elements"):
            # Consolidation or matching call — not an extraction
            return {"groups": []}
        # Parse paper_id from extraction prompt payload
        payload = json.loads(user_content.split("\n", 1)[1])
        paper_id = payload["paper_id"]
        with self._lock:
            self._calls.append(paper_id)
        if paper_id in self._fail_ids:
            raise ValueError(f"simulated extraction failure for {paper_id}")
        return self._responses[paper_id]

    @property
    def call_count(self) -> int:
        with self._lock:
            return len(self._calls)


def test_parallel_bootstrap_extracts_all_papers(tmp_path: Path):
    """3 papers extracted in parallel; 1 fails; other 2 have elements.json written."""
    library = tmp_path / "library"
    for pid in ("SA1", "SA2", "SA3"):
        write_reading_blocks(library, pid)
    cfg = AppConfig(library_dir=library)

    client = _PaperKeyedFakeClient(
        responses={
            "SA1": elements_ai_response("SA1"),
            "SA2": elements_ai_response("SA2"),
            "SA3": elements_ai_response("SA3"),
        },
        fail_ids={"SA2"},
    )

    msgs: list[str] = []
    summary = service.run_bootstrap(cfg, client, report=msgs.append, parallel=3)

    # SA2 failed, SA1+SA3 succeeded
    assert summary["extracted"] == 2
    assert summary["extract_failed"] == 1
    assert (library / "SA1" / "elements.json").exists()
    assert not (library / "SA2" / "elements.json").exists()
    assert (library / "SA3" / "elements.json").exists()
    # Index covers 2 successfully-extracted papers
    assert summary["papers_indexed"] == 2


def test_run_elements_for_paper_derives_card_tags(tmp_path: Path):
    """After run_elements_for_paper, card gets research_objects/methods/topic_ids."""
    library = tmp_path / "library"
    paper_dir = write_reading_blocks(library, "S90")
    # Write a minimal literature_card with classification stub
    card = {
        "paper_id": "S90",
        "title": "Test paper",
        "classification": {"domain_tags": []},
    }
    (paper_dir / "literature_card.json").write_text(
        json.dumps(card), encoding="utf-8"
    )
    cfg = AppConfig(library_dir=library)
    client = SequencedFakeClient([elements_ai_response("S90")])
    service.run_elements_for_paper(paper_dir, client, cfg)

    updated = json.loads((paper_dir / "literature_card.json").read_text(encoding="utf-8"))
    cls = updated["classification"]
    # Keys must exist (values depend on seed matching; may be empty lists)
    assert "research_objects" in cls
    assert "methods" in cls
    assert "topic_ids" in cls
    assert isinstance(cls["research_objects"], list)
    assert isinstance(cls["methods"], list)
    assert isinstance(cls["topic_ids"], list)


def test_bootstrap_derives_card_tags_for_all_papers(tmp_path: Path):
    """run_bootstrap writes card tags for papers that have both files."""
    library = tmp_path / "library"
    paper_dir = write_reading_blocks(library, "S90")
    card = {
        "paper_id": "S90",
        "classification": {"domain_tags": []},
    }
    (paper_dir / "literature_card.json").write_text(
        json.dumps(card), encoding="utf-8"
    )
    cfg = AppConfig(library_dir=library)
    client = SequencedFakeClient([
        elements_ai_response("S90"),
        {"groups": []},  # consolidation characterization chunk
        {"groups": []},  # consolidation preparation chunk
    ])
    service.run_bootstrap(cfg, client, lambda m: None)

    updated = json.loads((paper_dir / "literature_card.json").read_text(encoding="utf-8"))
    cls = updated["classification"]
    assert "research_objects" in cls
    assert "methods" in cls
    assert "topic_ids" in cls


def test_bootstrap_tail_uses_bulk_with_parallel(tmp_path: Path, monkeypatch):
    """registry 已存在时,尾巴走 bulk_match_elements 且并行数透传。"""
    library = tmp_path / "library"
    cfg = AppConfig(library_dir=library)
    write_reading_blocks(library, "S90")
    client1 = SequencedFakeClient([
        elements_ai_response("S90"),
        {"groups": []}, {"groups": []},
    ])
    service.run_bootstrap(cfg, client1, lambda m: None)   # 建出 registry

    captured = {}

    def fake_bulk(paper_dirs, registry, client, log_path, *, parallel=8, chunk_size=30):
        captured["n_papers"] = len(list(paper_dirs))
        captured["parallel"] = parallel
        return {"resolved_exact": 0, "resolved_ai": 0, "created": 0,
                "ai_calls": 0, "judge_failed_chunks": 0, "papers_written": 0,
                "groups_total": 0}

    monkeypatch.setattr(service, "bulk_match_elements", fake_bulk)
    write_reading_blocks(library, "S91")
    client2 = SequencedFakeClient([elements_ai_response("S91")])
    service.run_bootstrap(cfg, client2, lambda m: None, parallel=33)
    assert captured["parallel"] == 33
    assert captured["n_papers"] == 2
