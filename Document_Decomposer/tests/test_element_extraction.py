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


def test_malformed_items_are_dropped_not_crashing(tmp_path: Path):
    paper_dir = write_reading_blocks(tmp_path, "S90")
    client = SequencedFakeClient([{
        "paper_id": "S90",
        "elements": [
            None,
            "XRD",
            42,
            {"facet": "characterization", "surface": "XRD",
             "quote": "XRD patterns were recorded with CuKa radiation",
             "reading_block_id": "S90-RB-0002", "role": "used"},
        ],
    }])
    result = run_element_extraction(paper_dir, client, SEEDS)
    assert [o["surface"] for o in result["occurrences"]] == ["XRD"]
    assert sum(1 for d in result["dropped"] if d["reason"] == "bad_item") == 3


def test_elements_not_a_list_yields_empty(tmp_path: Path):
    paper_dir = write_reading_blocks(tmp_path, "S90")
    client = SequencedFakeClient([{"paper_id": "S90", "elements": {"oops": True}}])
    result = run_element_extraction(paper_dir, client, SEEDS)
    assert result["occurrences"] == [] and result["dropped"] == []


def test_prompt_lists_finding_facet(tmp_path: Path):
    paper_dir = write_reading_blocks(tmp_path, "S90")
    reading = json.loads((paper_dir / "reading_blocks.json").read_text(encoding="utf-8"))
    messages = build_elements_prompt(reading, SEEDS)
    joined = json.dumps(messages, ensure_ascii=False)
    # '"finding"' checked in the user-message content directly (json.dumps double-escapes inner quotes)
    assert '"finding"' in messages[1]["content"]  # facet 定义随 seeds 进入 prompt
    assert "conclusions this paper itself establishes" in messages[1]["content"].lower()


def test_finding_facet_extracted_with_quote(tmp_path: Path):
    blocks = [("S90-RB-0001", "Our results demonstrate that water content strongly reduces methane adsorption capacity in montmorillonite.", "conclusion")]
    paper_dir = write_reading_blocks(tmp_path, "S90", blocks)
    client = SequencedFakeClient([{"paper_id": "S90", "elements": [
        {"facet": "finding", "surface": "water reduces methane adsorption capacity",
         "quote": "water content strongly reduces methane adsorption capacity",
         "reading_block_id": "S90-RB-0001", "role": "used"},
    ]}])
    result = run_element_extraction(paper_dir, client, SEEDS)
    occ = result["occurrences"]
    assert len(occ) == 1 and occ[0]["facet"] == "finding" and occ[0]["quote_verified"] is True


def test_finding_fabricated_quote_dropped(tmp_path: Path):
    blocks = [("S90-RB-0001", "Our results demonstrate that water content strongly reduces methane adsorption capacity.", "conclusion")]
    paper_dir = write_reading_blocks(tmp_path, "S90", blocks)
    client = SequencedFakeClient([{"paper_id": "S90", "elements": [
        {"facet": "finding", "surface": "pressure increases adsorption",
         "quote": "higher pressure monotonically increases total adsorption",
         "reading_block_id": "S90-RB-0001", "role": "used"},
    ]}])
    result = run_element_extraction(paper_dir, client, SEEDS)
    assert result["occurrences"] == []
    assert result["dropped"][0]["reason"] == "quote_not_found"


def test_finding_mentioned_role_survives(tmp_path: Path):
    blocks = [("S90-RB-0001", "Smith et al. concluded that water content strongly reduces methane adsorption capacity.", "introduction")]
    paper_dir = write_reading_blocks(tmp_path, "S90", blocks)
    client = SequencedFakeClient([{"paper_id": "S90", "elements": [
        {"facet": "finding", "surface": "water reduces methane adsorption capacity",
         "quote": "water content strongly reduces methane adsorption capacity",
         "reading_block_id": "S90-RB-0001", "role": "mentioned"},
    ]}])
    result = run_element_extraction(paper_dir, client, SEEDS)
    assert len(result["occurrences"]) == 1 and result["occurrences"][0]["role"] == "mentioned"
