from autoreview_app.extract.docling_json import build_docling_json


def _items():
    return [
        {"page_no": 1, "text": "First block.", "bbox": {"l": 0, "t": 0, "r": 1, "b": 1}},
        {"page_no": 2, "text": "Second block.", "bbox": {"l": 0, "t": 0, "r": 1, "b": 1}},
    ]


def test_top_level_shape():
    doc = build_docling_json("mypaper", "mypaper.pdf", _items())
    assert doc["name"] == "mypaper"
    assert doc["origin"]["filename"] == "mypaper.pdf"
    assert doc["pictures"] == []
    assert doc["tables"] == []
    assert doc["groups"] == []


def test_body_children_reference_texts_in_order():
    doc = build_docling_json("mypaper", "mypaper.pdf", _items())
    assert [c["$ref"] for c in doc["body"]["children"]] == ["#/texts/0", "#/texts/1"]


def test_each_text_item_has_required_fields():
    doc = build_docling_json("mypaper", "mypaper.pdf", _items())
    t0 = doc["texts"][0]
    assert t0["label"] == "text"
    assert t0["content_layer"] == "body"
    assert t0["text"] == "First block."
    assert t0["orig"] == "First block."
    assert t0["prov"][0]["page_no"] == 1
    assert t0["prov"][0]["bbox"] == {"l": 0, "t": 0, "r": 1, "b": 1}


def test_empty_items_give_empty_body_and_texts():
    doc = build_docling_json("p", "p.pdf", [])
    assert doc["texts"] == []
    assert doc["body"]["children"] == []
