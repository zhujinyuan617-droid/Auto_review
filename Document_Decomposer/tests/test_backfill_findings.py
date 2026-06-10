"""Tests for backfill_findings and build_finding_prompt (R2, TDD)."""
import json
from pathlib import Path

import pytest

from _fake_ai import SequencedFakeClient
from _fixtures import write_reading_blocks
from docdecomp.element_extraction import (
    FINDING_SCHEMA_HINT,
    _FINDING_SYSTEM,
    backfill_findings,
    build_finding_prompt,
)
from docdecomp.element_registry import load_seeds

ENGINE_ROOT = Path(__file__).resolve().parents[1]
SEEDS = load_seeds(ENGINE_ROOT / "config" / "element_seeds.json")

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _write_elements(paper_dir: Path, occurrences: list, dropped: list | None = None) -> None:
    """Write a minimal elements.json to paper_dir."""
    data = {
        "schema_version": "0.1.0",
        "paper_id": paper_dir.name,
        "occurrences": occurrences,
        "dropped": dropped or [],
    }
    (paper_dir / "elements.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _finding_response(paper_id: str, surface: str, quote: str, rb_id: str) -> dict:
    return {
        "paper_id": paper_id,
        "elements": [
            {
                "facet": "finding",
                "surface": surface,
                "quote": quote,
                "reading_block_id": rb_id,
                "role": "used",
            }
        ],
    }


# ---------------------------------------------------------------------------
# Test: prompt shape
# ---------------------------------------------------------------------------

def test_build_finding_prompt_facets_only_finding(tmp_path: Path):
    """build_finding_prompt payload must contain only 'finding' facet, not others."""
    paper_dir = write_reading_blocks(tmp_path, "S90")
    reading = json.loads((paper_dir / "reading_blocks.json").read_text(encoding="utf-8"))
    messages = build_finding_prompt(reading, SEEDS)

    # System message uses the finding-only system string.
    assert messages[0]["role"] == "system"
    assert "principal findings" in messages[0]["content"].lower()
    assert "verbatim" in messages[0]["content"].lower()

    user_payload = json.loads(messages[1]["content"].split("\n", 1)[1])
    facet_ids = [f["id"] for f in user_payload["facets"]]
    assert facet_ids == ["finding"], f"Expected only ['finding'], got {facet_ids}"
    # Other facets must NOT appear in the payload.
    for other in ("preparation", "characterization", "simulation", "material", "condition"):
        assert other not in facet_ids


def test_build_finding_prompt_system_mentions_principal_and_verbatim(tmp_path: Path):
    """_FINDING_SYSTEM must mention 'principal findings' and 'verbatim'."""
    assert "principal findings" in _FINDING_SYSTEM.lower() or "principal" in _FINDING_SYSTEM.lower()
    assert "verbatim" in _FINDING_SYSTEM.lower()


# ---------------------------------------------------------------------------
# Test: idempotency
# ---------------------------------------------------------------------------

def test_backfill_findings_idempotent(tmp_path: Path):
    """Paper with 2 non-finding + 1 OLD finding occ.
    After one backfill: 2 non-finding + 1 NEW finding.
    After a second identical backfill: still 3 total (old new finding removed, new one added).
    """
    # Blocks for the paper
    blocks = [
        ("S10-RB-0001", "XRD patterns were recorded with CuKa radiation.", "methods"),
        ("S10-RB-0002", "Methane adsorption was measured at 333 K.", "results"),
        ("S10-RB-0003", "Water strongly reduces methane adsorption capacity in clay.", "conclusion"),
    ]
    paper_dir = write_reading_blocks(tmp_path, "S10", blocks)

    # Pre-existing elements: 2 non-finding + 1 old finding.
    existing_occs = [
        {
            "facet": "characterization",
            "surface": "XRD",
            "quote": "XRD patterns were recorded with CuKa radiation.",
            "reading_block_id": "S10-RB-0001",
            "role": "used",
            "quote_verified": True,
            "digits_verified": False,
            "values": [],
            "canonical_id": None,
        },
        {
            "facet": "condition",
            "surface": "temperature",
            "quote": "Methane adsorption was measured at 333 K.",
            "reading_block_id": "S10-RB-0002",
            "role": "used",
            "quote_verified": True,
            "digits_verified": True,
            "values": [{"raw": "333 K", "num": "333", "unit": "K"}],
            "canonical_id": None,
        },
        {
            "facet": "finding",
            "surface": "old: water effect on adsorption",
            "quote": "OLD QUOTE — will be replaced",
            "reading_block_id": "S10-RB-0003",
            "role": "used",
            "quote_verified": True,
            "digits_verified": False,
            "values": [],
            "canonical_id": None,
        },
    ]
    _write_elements(paper_dir, existing_occs)

    new_quote = "Water strongly reduces methane adsorption capacity in clay."
    ai_response = _finding_response("S10", "water reduces CH4 adsorption", new_quote, "S10-RB-0003")

    # --- First run ---
    client = SequencedFakeClient([ai_response])
    stats = backfill_findings(paper_dir, client, SEEDS)

    data = json.loads((paper_dir / "elements.json").read_text(encoding="utf-8"))
    occs = data["occurrences"]
    assert len(occs) == 3, f"Expected 3 occs, got {len(occs)}: {[o['surface'] for o in occs]}"
    assert stats["added"] == 1
    assert stats["removed_old"] == 1

    finding_occs = [o for o in occs if o["facet"] == "finding"]
    assert len(finding_occs) == 1
    assert finding_occs[0]["surface"] == "water reduces CH4 adsorption"
    assert finding_occs[0]["quote"] == new_quote
    assert "OLD QUOTE" not in json.dumps(occs)

    # Non-finding facets must be untouched.
    non_finding = [o for o in occs if o["facet"] != "finding"]
    assert {o["facet"] for o in non_finding} == {"characterization", "condition"}

    # --- Second run (same AI response) — idempotent ---
    client2 = SequencedFakeClient([ai_response])
    stats2 = backfill_findings(paper_dir, client2, SEEDS)

    data2 = json.loads((paper_dir / "elements.json").read_text(encoding="utf-8"))
    occs2 = data2["occurrences"]
    assert len(occs2) == 3, f"Idempotent: expected 3, got {len(occs2)}"
    assert stats2["added"] == 1
    assert stats2["removed_old"] == 1
    finding_occs2 = [o for o in occs2 if o["facet"] == "finding"]
    assert len(finding_occs2) == 1
    assert finding_occs2[0]["surface"] == "water reduces CH4 adsorption"


# ---------------------------------------------------------------------------
# Test: non-finding facets from AI are DROPPED (bad_facet)
# ---------------------------------------------------------------------------

def test_non_finding_facets_in_ai_response_are_dropped(tmp_path: Path):
    """If AI returns a 'characterization' item mixed with a finding, only finding is kept."""
    blocks = [
        ("S11-RB-0001", "XRD patterns were recorded with CuKa radiation.", "methods"),
        ("S11-RB-0002", "Water strongly reduces methane adsorption capacity.", "conclusion"),
    ]
    paper_dir = write_reading_blocks(tmp_path, "S11", blocks)
    _write_elements(paper_dir, [])

    # AI misbehaves: returns one real finding + one non-finding facet.
    ai_response = {
        "paper_id": "S11",
        "elements": [
            {
                "facet": "finding",
                "surface": "water reduces CH4 adsorption",
                "quote": "Water strongly reduces methane adsorption capacity.",
                "reading_block_id": "S11-RB-0002",
                "role": "used",
            },
            {
                "facet": "characterization",
                "surface": "XRD",
                "quote": "XRD patterns were recorded with CuKa radiation.",
                "reading_block_id": "S11-RB-0001",
                "role": "used",
            },
        ],
    }
    client = SequencedFakeClient([ai_response])
    stats = backfill_findings(paper_dir, client, SEEDS)

    data = json.loads((paper_dir / "elements.json").read_text(encoding="utf-8"))
    occs = data["occurrences"]
    assert len(occs) == 1
    assert occs[0]["facet"] == "finding"
    assert stats["added"] == 1
    assert stats["dropped"] == 1  # the bad characterization item


# ---------------------------------------------------------------------------
# Test: quote verification failure → dropped with phase field
# ---------------------------------------------------------------------------

def test_fabricated_quote_dropped_with_phase_field(tmp_path: Path):
    """An AI-returned finding with a fabricated quote must be dropped, and the
    dropped entry must carry phase='finding_backfill'."""
    blocks = [
        ("S12-RB-0001", "Water reduces methane adsorption in real text.", "conclusion"),
    ]
    paper_dir = write_reading_blocks(tmp_path, "S12", blocks)
    _write_elements(paper_dir, [])

    # AI fabricates a quote not present in the block.
    ai_response = {
        "paper_id": "S12",
        "elements": [
            {
                "facet": "finding",
                "surface": "pressure increases adsorption",
                "quote": "Higher pressure monotonically increases total adsorption capacity",
                "reading_block_id": "S12-RB-0001",
                "role": "used",
            }
        ],
    }
    client = SequencedFakeClient([ai_response])
    stats = backfill_findings(paper_dir, client, SEEDS)

    data = json.loads((paper_dir / "elements.json").read_text(encoding="utf-8"))
    assert data["occurrences"] == []
    assert stats["added"] == 0
    assert stats["dropped"] == 1

    # The dropped entry must have phase='finding_backfill'.
    dropped = data["dropped"]
    assert len(dropped) == 1
    assert dropped[0].get("phase") == "finding_backfill"
    assert dropped[0].get("reason") == "quote_not_found"


# ---------------------------------------------------------------------------
# Test: missing elements.json → ValueError
# ---------------------------------------------------------------------------

def test_missing_elements_json_raises_value_error(tmp_path: Path):
    """backfill_findings must raise ValueError when elements.json is absent."""
    paper_dir = write_reading_blocks(tmp_path, "S13")
    # Do NOT write elements.json.
    client = SequencedFakeClient([])
    with pytest.raises(ValueError, match="elements.json not found"):
        backfill_findings(paper_dir, client, SEEDS)


# ---------------------------------------------------------------------------
# Test: canonical_id left null on new findings
# ---------------------------------------------------------------------------

def test_new_findings_have_null_canonical_id(tmp_path: Path):
    """Findings added by backfill must have canonical_id=None (matching is a separate step)."""
    blocks = [
        ("S14-RB-0001", "Temperature controls methane diffusion rate in shale.", "conclusion"),
    ]
    paper_dir = write_reading_blocks(tmp_path, "S14", blocks)
    _write_elements(paper_dir, [])

    ai_response = _finding_response(
        "S14",
        "temperature controls diffusion rate",
        "Temperature controls methane diffusion rate in shale.",
        "S14-RB-0001",
    )
    client = SequencedFakeClient([ai_response])
    backfill_findings(paper_dir, client, SEEDS)

    data = json.loads((paper_dir / "elements.json").read_text(encoding="utf-8"))
    assert data["occurrences"][0]["canonical_id"] is None
