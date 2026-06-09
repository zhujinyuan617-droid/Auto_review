from pathlib import Path

from autoreview_app.config import AppConfig
from autoreview_app.main import with_connection_paths


def test_sets_paths_when_files_exist(tmp_path: Path):
    conn = tmp_path / "connection"
    conn.mkdir()
    (conn / "edges.json").write_text("{}", encoding="utf-8")
    (conn / "concept_index.json").write_text("{}", encoding="utf-8")
    cfg = with_connection_paths(AppConfig(library_dir=tmp_path / "library"), conn)
    assert cfg.edges_path == conn / "edges.json"
    assert cfg.concept_index_path == conn / "concept_index.json"


def test_leaves_paths_none_when_files_missing(tmp_path: Path):
    conn = tmp_path / "connection"  # does not exist
    cfg = with_connection_paths(AppConfig(library_dir=tmp_path / "library"), conn)
    assert cfg.edges_path is None
    assert cfg.concept_index_path is None
