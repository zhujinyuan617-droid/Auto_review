import json
from pathlib import Path

from _fake_ai import SequencedFakeClient
from _fixtures import write_reading_blocks
from docdecomp.element_extraction import build_elements_prompt, run_element_extraction
from docdecomp.element_registry import load_seeds

ENGINE_ROOT = Path(__file__).resolve().parents[1]
SEEDS = load_seeds(ENGINE_ROOT / "config" / "element_seeds.json")


def _ai_response():
    return {
        "paper_id": "S90",
        "elements": [
            {"facet": "preparation", "surface": "ball milling",
             "quote": "ball-milled for 4 h at 400 rpm", "reading_block_id": "S90-RB-0001", "role": "used"},
            {"facet": "characterization", "surface": "XRD",
             "quote": "XRD patterns were recorded with CuKa radiation",
             "reading_block_id": "S90-RB-0002", "role": "used"},
            {"facet": "condition", "surface": "temperature",
             "quote": "measured at 333 K up to 25 MPa", "reading_block_id": "S90-RB-0003", "role": "used"},
            {"facet": "preparation", "surface": "acid washing",
             "quote": "samples were acid washed overnight in HCl",
             "reading_block_id": "S90-RB-0001", "role": "used"},
            {"facet": "nonsense-facet", "surface": "foo",
             "quote": "ball-milled for 4 h at 400 rpm", "reading_block_id": "S90-RB-0001", "role": "used"},
        ],
    }


def test_prompt_contains_facets_and_blocks(tmp_path: Path):
    paper_dir = write_reading_blocks(tmp_path, "S90")
    reading = json.loads((paper_dir / "reading_blocks.json").read_text(encoding="utf-8"))
    messages = build_elements_prompt(reading, SEEDS)
    joined = json.dumps(messages, ensure_ascii=False)
    assert "preparation" in joined and "S90-RB-0001" in joined
    assert messages[0]["role"] == "system"


def test_run_extraction_verifies_drops_and_writes(tmp_path: Path):
    paper_dir = write_reading_blocks(tmp_path, "S90")
    client = SequencedFakeClient([_ai_response()])
    result = run_element_extraction(paper_dir, client, SEEDS)

    occ = result["occurrences"]
    surfaces = {o["surface"] for o in occ}
    assert surfaces == {"ball milling", "XRD", "temperature"}  # 编造的 acid washing 被核真丢弃, 坏 facet 被丢弃
    cond = next(o for o in occ if o["facet"] == "condition")
    assert cond["digits_verified"] is True
    assert {"raw": "333 K", "num": "333", "unit": "K"} in cond["values"]
    assert all(o["canonical_id"] is None for o in occ)
    reasons = {d["reason"] for d in result["dropped"]}
    assert "quote_not_found" in reasons and "bad_facet" in reasons

    on_disk = json.loads((paper_dir / "elements.json").read_text(encoding="utf-8"))
    assert on_disk["paper_id"] == "S90" and len(on_disk["occurrences"]) == 3
