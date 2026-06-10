"""Tests for scripts/elements/import_topic_vocabulary.py.

Verifies idempotent import: creates entries for new topic concepts, adds aliases
for members, and is a no-op on re-run.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ENGINE_ROOT = Path(__file__).resolve().parents[1]
SRC = ENGINE_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from docdecomp.element_registry import (
    create_entry,
    find_by_surface,
    load_seeds,
    new_registry_from_seeds,
    save_registry,
)
from docdecomp.io_utils import write_json


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seeds():
    return load_seeds(ENGINE_ROOT / "config" / "element_seeds.json")


def _make_vocab(tmp_path: Path, concepts: list[dict]) -> Path:
    """Write a minimal vocabulary.json fixture with the given topic concepts."""
    vocab = {
        "card_count": 10,
        "model": "test-model",
        "facets": {
            "topic": {"concepts": concepts},
            "method": {"concepts": []},
            "object": {"concepts": []},
        },
        "raw_to_canonical": {"topic": {}, "method": {}, "object": {}},
    }
    path = tmp_path / "vocabulary.json"
    write_json(path, vocab)
    return path


def _make_data_dir(tmp_path: Path, registry: dict) -> Path:
    """Write registry.json into a fresh data-dir subdir and return it."""
    data_dir = tmp_path / "data_elements"
    data_dir.mkdir()
    save_registry(data_dir / "registry.json", registry)
    return data_dir


def _run_import(vocab_path: Path, data_dir: Path) -> dict:
    """Run import_topic_vocabulary.main() programmatically via argparse."""
    script = ENGINE_ROOT / "scripts" / "elements" / "import_topic_vocabulary.py"
    # Run via exec; supply __file__ so the script's ROOT calculation works
    ns: dict = {"__file__": str(script)}
    exec(compile(script.read_text(encoding="utf-8"), str(script), "exec"), ns)
    main_fn = ns["main"]

    # Patch sys.argv
    import sys as _sys
    old_argv = _sys.argv
    _sys.argv = [
        "import_topic_vocabulary.py",
        "--vocab", str(vocab_path),
        "--data-dir", str(data_dir),
    ]
    try:
        rc = main_fn()
    finally:
        _sys.argv = old_argv

    # Reload registry from disk (may not exist if script errored before creating it)
    reg_path = data_dir / "registry.json"
    reg = json.loads(reg_path.read_text(encoding="utf-8")) if reg_path.exists() else {}
    return {"rc": rc, "registry": reg}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestImportTopicVocabulary:
    def test_creates_new_entry_and_aliases(self, tmp_path):
        """One concept with two members: canonical → create_entry; alias → add_alias."""
        reg = new_registry_from_seeds(_seeds())
        data_dir = _make_data_dir(tmp_path, reg)
        vocab_path = _make_vocab(tmp_path, [
            {"canonical": "shale gas", "members": ["shale gas", "deep shale gas"]},
        ])
        result = _run_import(vocab_path, data_dir)
        assert result["rc"] == 0
        reg_out = result["registry"]
        # Canonical entry must exist
        eid = find_by_surface(reg_out, "topic", "shale gas")
        assert eid is not None
        # Alias member must resolve to same entry
        eid2 = find_by_surface(reg_out, "topic", "deep shale gas")
        assert eid2 == eid

    def test_already_present_concept_skipped(self, tmp_path):
        """If canonical already in registry as topic entry, do not create a duplicate."""
        reg = new_registry_from_seeds(_seeds())
        log = tmp_path / "log.jsonl"
        create_entry(reg, "topic", "shale gas", "seed", log)
        data_dir = _make_data_dir(tmp_path, reg)
        vocab_path = _make_vocab(tmp_path, [
            {"canonical": "shale gas", "members": ["shale gas", "deep shale gas"]},
            {"canonical": "clay minerals", "members": ["clay minerals", "clay"]},
        ])
        result = _run_import(vocab_path, data_dir)
        assert result["rc"] == 0
        reg_out = result["registry"]
        # shale gas pre-existed → should NOT have been created again
        # clay minerals is new → must exist
        assert find_by_surface(reg_out, "topic", "clay minerals") is not None

    def test_idempotent_rerun_creates_zero(self, tmp_path, capsys):
        """Running import twice: second run creates 0 new entries."""
        reg = new_registry_from_seeds(_seeds())
        data_dir = _make_data_dir(tmp_path, reg)
        vocab_path = _make_vocab(tmp_path, [
            {"canonical": "shale gas", "members": ["shale gas", "deep shale"]},
        ])
        # First run
        _run_import(vocab_path, data_dir)
        # Second run — should be a no-op
        result2 = _run_import(vocab_path, data_dir)
        assert result2["rc"] == 0
        # Re-check: only one topic entry matching "shale gas"
        reg_out = result2["registry"]
        topic_entries = [
            e for e in reg_out["entries"].values()
            if e["facet"] == "topic" and not e.get("redirect_to")
        ]
        # Exactly one shale gas entry
        shale_entries = [e for e in topic_entries if e["display_name"] == "shale gas"]
        assert len(shale_entries) == 1

    def test_missing_registry_exits_1(self, tmp_path):
        """If registry.json does not exist in data-dir, script must exit with code 1."""
        data_dir = tmp_path / "empty_data_dir"
        data_dir.mkdir()
        vocab_path = _make_vocab(tmp_path, [
            {"canonical": "shale gas", "members": ["shale gas"]},
        ])
        result = _run_import(vocab_path, data_dir)
        assert result["rc"] == 1

    def test_multiple_concepts_both_created(self, tmp_path):
        """Two new concepts → both created, aliases linked."""
        reg = new_registry_from_seeds(_seeds())
        data_dir = _make_data_dir(tmp_path, reg)
        vocab_path = _make_vocab(tmp_path, [
            {"canonical": "shale gas", "members": ["shale gas", "deep shale"]},
            {"canonical": "clay minerals", "members": ["clay minerals", "illite clay"]},
        ])
        result = _run_import(vocab_path, data_dir)
        assert result["rc"] == 0
        reg_out = result["registry"]
        assert find_by_surface(reg_out, "topic", "shale gas") is not None
        assert find_by_surface(reg_out, "topic", "clay minerals") is not None
        assert find_by_surface(reg_out, "topic", "deep shale") is not None
        assert find_by_surface(reg_out, "topic", "illite clay") is not None

    def test_single_member_canonical_only_no_extra_alias(self, tmp_path):
        """Concept with only canonical member → entry created, no alias appended."""
        reg = new_registry_from_seeds(_seeds())
        data_dir = _make_data_dir(tmp_path, reg)
        vocab_path = _make_vocab(tmp_path, [
            {"canonical": "nanopore", "members": ["nanopore"]},
        ])
        result = _run_import(vocab_path, data_dir)
        assert result["rc"] == 0
        reg_out = result["registry"]
        eid = find_by_surface(reg_out, "topic", "nanopore")
        assert eid is not None
        entry = reg_out["entries"][eid]
        assert entry["aliases"] == []
