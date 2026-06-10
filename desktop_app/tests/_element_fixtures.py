import json
from pathlib import Path


def write_reading_blocks(library: Path, paper_id: str, blocks=None) -> Path:
    paper_dir = library / paper_id
    paper_dir.mkdir(parents=True, exist_ok=True)
    default = [
        (f"{paper_id}-RB-0001", "The montmorillonite was ball-milled for 4 h at 400 rpm under N2.", "methods"),
        (f"{paper_id}-RB-0002", "XRD patterns were recorded with CuKa radiation.", "methods"),
    ]
    rbs = [{"reading_block_id": bid, "order": i, "section_kind": kind, "reading_type": kind,
            "include_in_reading": True, "text": text, "caption": ""}
           for i, (bid, text, kind) in enumerate(blocks or default)]
    (paper_dir / "reading_blocks.json").write_text(
        json.dumps({"schema_version": "0.1.0", "paper_id": paper_id, "reading_blocks": rbs}),
        encoding="utf-8")
    return paper_dir


def elements_ai_response(paper_id: str):
    return {"paper_id": paper_id, "elements": [
        {"facet": "preparation", "surface": "ball milling",
         "quote": "ball-milled for 4 h at 400 rpm",
         "reading_block_id": f"{paper_id}-RB-0001", "role": "used"},
        {"facet": "characterization", "surface": "XRD",
         "quote": "XRD patterns were recorded with CuKa radiation",
         "reading_block_id": f"{paper_id}-RB-0002", "role": "used"},
    ]}
