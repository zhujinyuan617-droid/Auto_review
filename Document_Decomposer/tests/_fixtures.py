import json
from pathlib import Path

DEFAULT_TEXTS = [
    ("The montmorillonite was ball-milled for 4 h at 400 rpm under N2.", "methods"),
    ("XRD patterns were recorded with CuKa radiation.", "methods"),
    ("Methane adsorption isotherms were measured at 333 K up to 25 MPa.", "results"),
]


def write_reading_blocks(
    library: Path,
    paper_id: str,
    blocks: list[tuple[str, str, str]] | None = None,
) -> Path:
    """Minimal real-schema reading_blocks.json for one paper. Returns paper dir.

    Block ids derive from paper_id (Sxx-RB-0001...), matching the engine format.
    """
    paper_dir = library / paper_id
    paper_dir.mkdir(parents=True, exist_ok=True)
    if blocks is None:
        blocks = [
            (f"{paper_id}-RB-{i + 1:04d}", text, kind)
            for i, (text, kind) in enumerate(DEFAULT_TEXTS)
        ]
    rbs = [
        {
            "reading_block_id": bid,
            "order": i,
            "section_kind": kind,
            "reading_type": kind,
            "include_in_reading": True,
            "text": text,
            "caption": "",
        }
        for i, (bid, text, kind) in enumerate(blocks)
    ]
    data = {"schema_version": "0.1.0", "paper_id": paper_id, "reading_blocks": rbs}
    (paper_dir / "reading_blocks.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return paper_dir
