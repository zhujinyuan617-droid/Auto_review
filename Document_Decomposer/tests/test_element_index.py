import json
from pathlib import Path

from _fixtures import write_reading_blocks
from docdecomp.element_index import (
    build_index,
    get_element,
    paper_elements,
    query_combination,
    query_cooccurrence,
    query_overview,
    query_stats,
    search_elements,
)
from docdecomp.element_registry import load_seeds, new_registry_from_seeds

ENGINE_ROOT = Path(__file__).resolve().parents[1]
SEEDS = load_seeds(ENGINE_ROOT / "config" / "element_seeds.json")

XRD = "elem:characterization/x-ray-diffraction"
BM = "elem:preparation/ball-milling"
GCMC = "elem:simulation/grand-canonical-monte-carlo"


def _paper(library, pid, items, role="used"):
    paper_dir = write_reading_blocks(library, pid)
    occ = [{"facet": eid.split(":")[1].split("/")[0], "surface": s, "quote": f"quote about {s}",
            "reading_block_id": f"{pid}-RB-0001", "role": role, "quote_verified": True,
            "digits_verified": False, "values": [], "canonical_id": eid} for eid, s in items]
    (paper_dir / "elements.json").write_text(
        json.dumps({"schema_version": "0.1.0", "paper_id": pid, "occurrences": occ, "dropped": []}),
        encoding="utf-8")


def _build(tmp_path):
    reg = new_registry_from_seeds(SEEDS)
    _paper(tmp_path, "S90", [(XRD, "XRD"), (BM, "ball milling")])
    _paper(tmp_path, "S91", [(XRD, "X-ray diffraction"), (GCMC, "GCMC")])
    _paper(tmp_path, "S92", [(XRD, "XRD")], role="mentioned")
    db = tmp_path / "elements_index.sqlite"
    n = build_index(tmp_path, reg, db)
    return reg, db, n


def test_build_counts_papers(tmp_path: Path):
    _, _, n = _build(tmp_path)
    assert n == 3


def test_stats_default_used_only(tmp_path: Path):
    _, db, _ = _build(tmp_path)
    items = query_stats(db, "characterization")
    row = next(i for i in items if i["id"] == XRD)
    assert row["papers"] == 2  # S92 是 mentioned, 不计
    assert row["display_name"] == "X-ray diffraction"
    all_items = query_stats(db, "characterization", role=None)
    assert next(i for i in all_items if i["id"] == XRD)["papers"] == 3


def test_overview_has_facets_and_top(tmp_path: Path):
    _, db, _ = _build(tmp_path)
    ov = query_overview(db, top_n=3)
    facets = {f["id"]: f for f in ov["facets"]}
    assert facets["characterization"]["top"][0]["id"] == XRD


def test_search_by_alias(tmp_path: Path):
    _, db, _ = _build(tmp_path)
    hits = search_elements(db, "xrd")
    assert any(h["id"] == XRD for h in hits)


def test_get_element_papers_and_quotes(tmp_path: Path):
    _, db, _ = _build(tmp_path)
    detail = get_element(db, "characterization", "x-ray-diffraction")
    assert detail["paper_count"] == 2
    pids = {p["paper_id"] for p in detail["papers"]}
    assert pids == {"S90", "S91"}
    assert get_element(db, "characterization", "nope") is None


def test_cooccurrence(tmp_path: Path):
    _, db, _ = _build(tmp_path)
    co = query_cooccurrence(db, "characterization", "x-ray-diffraction")
    assert co["m"] == 2
    flat = {i["id"]: i["n"] for g in co["groups"] for i in g["items"]}
    assert flat[BM] == 1 and flat[GCMC] == 1


def test_combination_query(tmp_path: Path):
    _, db, _ = _build(tmp_path)
    res = query_combination(db, [XRD, BM])
    assert [p["paper_id"] for p in res["papers"]] == ["S90"]
    assert res["papers"][0]["matches"][0]["quote"].startswith("quote about")


def test_paper_elements_grouped(tmp_path: Path):
    _, db, _ = _build(tmp_path)
    pe = paper_elements(db, "S90")
    facets = {g["facet"] for g in pe["groups"]}
    assert facets == {"characterization", "preparation"}


def test_redirect_resolved_at_build(tmp_path: Path):
    from docdecomp.element_registry import create_entry, merge_entries

    reg = new_registry_from_seeds(SEEDS)
    log = tmp_path / "log.jsonl"
    a = create_entry(reg, "material", "kerogen", "bootstrap", log)
    b = create_entry(reg, "material", "type II kerogen", "bootstrap", log)
    merge_entries(reg, b, a, "human", log)
    _paper(tmp_path, "S90", [(b, "type II kerogen")])  # occurrence cites the MERGED-AWAY id
    db = tmp_path / "elements_index.sqlite"
    build_index(tmp_path, reg, db)
    detail = get_element(db, "material", "kerogen")
    assert detail is not None and detail["paper_count"] == 1  # folded into target
    assert get_element(db, "material", "type-ii-kerogen") is None  # stub absent


def test_concurrent_reindex_and_query_do_not_error(tmp_path: Path):
    import threading

    reg, db, _ = _build(tmp_path)
    errors: list[Exception] = []

    def rebuild():
        try:
            for _ in range(10):
                build_index(tmp_path, reg, db)
        except Exception as exc:  # pragma: no cover - failure path
            errors.append(exc)

    def read():
        try:
            for _ in range(20):
                query_stats(db, "characterization")
                query_overview(db, top_n=3)
        except Exception as exc:  # pragma: no cover - failure path
            errors.append(exc)

    threads = [threading.Thread(target=rebuild) for _ in range(2)] + [
        threading.Thread(target=read) for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
