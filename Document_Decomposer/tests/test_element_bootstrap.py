import json
from pathlib import Path

from _fake_ai import SequencedFakeClient
from _fixtures import write_reading_blocks
from docdecomp.element_bootstrap import bootstrap_registry, collect_surfaces, superbucket_report
from docdecomp.element_registry import load_seeds

ENGINE_ROOT = Path(__file__).resolve().parents[1]
SEEDS = load_seeds(ENGINE_ROOT / "config" / "element_seeds.json")


def _paper_with_elements(library: Path, pid: str, surfaces: list[tuple[str, str]]):
    paper_dir = write_reading_blocks(library, pid)
    occ = [{"facet": f, "surface": s, "quote": "q", "reading_block_id": f"{pid}-RB-0001",
            "role": "used", "quote_verified": True, "digits_verified": False,
            "values": [], "canonical_id": None} for f, s in surfaces]
    (paper_dir / "elements.json").write_text(
        json.dumps({"schema_version": "0.1.0", "paper_id": pid, "occurrences": occ, "dropped": []}),
        encoding="utf-8")


def test_collect_surfaces_counts(tmp_path: Path):
    _paper_with_elements(tmp_path, "S90", [("characterization", "XRD"), ("simulation", "GCMC")])
    _paper_with_elements(tmp_path, "S91", [("characterization", "X-ray diffraction")])
    counts = collect_surfaces(tmp_path)
    assert counts["characterization"]["XRD"] == 1
    assert counts["characterization"]["X-ray diffraction"] == 1
    assert counts["simulation"]["GCMC"] == 1


def test_bootstrap_groups_assigns_and_handles_unassigned(tmp_path: Path):
    _paper_with_elements(tmp_path, "S90",
                         [("characterization", "powder XRD"), ("characterization", "SAXS")])
    _paper_with_elements(tmp_path, "S91", [("characterization", "small-angle X-ray scattering")])
    data_dir = tmp_path / "data" / "elements"
    # AI 归并: powder XRD 归入种子 X-ray diffraction;SAXS 与全称成一组;漏掉的 surface 由机械兜底建条目
    client = SequencedFakeClient([
        {"groups": [
            {"canonical": "X-ray diffraction", "members": ["powder XRD"]},
            {"canonical": "small-angle X-ray scattering", "members": ["SAXS", "small-angle X-ray scattering"]},
        ]}
    ])
    reg = bootstrap_registry(tmp_path, SEEDS, client, data_dir)
    assert (data_dir / "registry.json").exists() and (data_dir / "registry_log.jsonl").exists()
    saxs_id = "elem:characterization/small-angle-x-ray-scattering"
    assert saxs_id in reg["entries"]
    assert "SAXS" in reg["entries"][saxs_id]["aliases"]
    # 全部 occurrence 已赋 canonical_id
    for pid in ("S90", "S91"):
        data = json.loads((tmp_path / pid / "elements.json").read_text(encoding="utf-8"))
        assert all(o["canonical_id"] for o in data["occurrences"])
    d90 = json.loads((tmp_path / "S90" / "elements.json").read_text(encoding="utf-8"))
    ids = {o["surface"]: o["canonical_id"] for o in d90["occurrences"]}
    assert ids["powder XRD"] == "elem:characterization/x-ray-diffraction"


def test_superbucket_report_flags_oversized():
    reg = {"entries": {"elem:a/x": {"id": "elem:a/x", "facet": "a", "display_name": "x",
                                    "aliases": [f"a{i}" for i in range(15)],
                                    "redirect_to": None, "origin": "bootstrap", "human_locked": False}}}
    flagged = superbucket_report(reg, max_aliases=12)
    assert flagged and flagged[0]["id"] == "elem:a/x"
