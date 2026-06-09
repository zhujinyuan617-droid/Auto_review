from __future__ import annotations

from typing import Any

# A "text item" is a plain dict with REQUIRED keys {"page_no": int, "text": str,
# "bbox": dict}; the caller must supply all three (a missing key is a caller bug).
# This module shapes a list of them into a Docling-compatible JSON that the
# engine's build_clean_package consumes. Pure data; no I/O, no fitz.
#
# Two fields the engine does NOT read are kept on purpose so the output stays
# faithful to real Docling export: `schema_name` (document marker) and per-item
# `self_ref`. Keeping them means a real Docling loader / downstream tool would
# see the same shape. `label` is always "text" here because the caller feeds
# flat body paragraphs; section/heading typing is the AI `sections` stage's job
# (M2b), not this shaping step.


def build_docling_json(
    name: str,
    origin_filename: str,
    text_items: list[dict[str, Any]],
) -> dict[str, Any]:
    texts: list[dict[str, Any]] = []
    children: list[dict[str, str]] = []
    for index, item in enumerate(text_items):
        ref = f"#/texts/{index}"
        texts.append(
            {
                "self_ref": ref,
                "label": "text",
                "text": item["text"],
                "orig": item["text"],
                "content_layer": "body",
                "prov": [{"page_no": item["page_no"], "bbox": item["bbox"]}],
            }
        )
        children.append({"$ref": ref})
    return {
        "schema_name": "DoclingDocument",
        "name": name,
        "origin": {"filename": origin_filename},
        "body": {"children": children},
        "groups": [],
        "texts": texts,
        "pictures": [],
        "tables": [],
    }
