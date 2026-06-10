import json
from pathlib import Path

from _fake_ai import SequencedFakeClient
from _fixtures import write_reading_blocks
from docdecomp.element_matching import match_paper_elements
from docdecomp.element_registry import load_seeds, new_registry_from_seeds

ENGINE_ROOT = Path(__file__).resolve().parents[1]
SEEDS = load_seeds(ENGINE_ROOT / "config" / "element_seeds.json")


def _write_elements(paper_dir: Path, occurrences):
    data = {"schema_version": "0.1.0", "paper_id": paper_dir.name,
            "occurrences": occurrences, "dropped": []}
    (paper_dir / "elements.json").write_text(json.dumps(data), encoding="utf-8")


def _occ(facet, surface):
    return {"facet": facet, "surface": surface, "quote": "q", "reading_block_id": "S90-RB-0001",
            "role": "used", "quote_verified": True, "digits_verified": False,
            "values": [], "canonical_id": None}


def test_exact_and_alias_resolve_without_ai(tmp_path: Path):
    paper_dir = write_reading_blocks(tmp_path, "S90")
    _write_elements(paper_dir, [_occ("characterization", "XRD"),
                                _occ("preparation", "ball-milled")])
    reg = new_registry_from_seeds(SEEDS)
    log = tmp_path / "log.jsonl"
    stats = match_paper_elements(paper_dir, reg, None, log)
    data = json.loads((paper_dir / "elements.json").read_text(encoding="utf-8"))
    ids = {o["surface"]: o["canonical_id"] for o in data["occurrences"]}
    assert ids["XRD"] == "elem:characterization/x-ray-diffraction"
    assert ids["ball-milled"] == "elem:preparation/ball-milling"
    assert stats["ai_calls"] == 0 and stats["created"] == 0


def test_unresolved_with_ai_match_and_create(tmp_path: Path):
    paper_dir = write_reading_blocks(tmp_path, "S90")
    _write_elements(paper_dir, [_occ("characterization", "powder X-ray diffraction"),
                                _occ("characterization", "neutron scattering")])
    reg = new_registry_from_seeds(SEEDS)
    log = tmp_path / "log.jsonl"
    client = SequencedFakeClient([
        {"matches": [
            {"surface": "powder X-ray diffraction", "element_id": "elem:characterization/x-ray-diffraction"},
            {"surface": "neutron scattering", "element_id": None},
        ]}
    ])
    stats = match_paper_elements(paper_dir, reg, client, log)
    data = json.loads((paper_dir / "elements.json").read_text(encoding="utf-8"))
    ids = {o["surface"]: o["canonical_id"] for o in data["occurrences"]}
    assert ids["powder X-ray diffraction"] == "elem:characterization/x-ray-diffraction"
    assert ids["neutron scattering"] == "elem:characterization/neutron-scattering"
    assert "powder X-ray diffraction" in reg["entries"]["elem:characterization/x-ray-diffraction"]["aliases"]
    assert stats["created"] == 1 and stats["ai_calls"] == 1


def test_no_client_creates_entries_directly(tmp_path: Path):
    paper_dir = write_reading_blocks(tmp_path, "S90")
    _write_elements(paper_dir, [_occ("material", "kerogen type II")])
    reg = new_registry_from_seeds(SEEDS)
    stats = match_paper_elements(paper_dir, reg, None, tmp_path / "log.jsonl")
    assert stats["created"] == 1
    data = json.loads((paper_dir / "elements.json").read_text(encoding="utf-8"))
    assert data["occurrences"][0]["canonical_id"] == "elem:material/kerogen-type-ii"
