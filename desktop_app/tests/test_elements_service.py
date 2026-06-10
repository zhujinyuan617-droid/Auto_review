import json
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
