"""P0-2 回归:并发导入不得丢注册表条目(last-writer-wins 雷)。"""
import json
import threading
from pathlib import Path

from _element_fixtures import write_reading_blocks
from autoreview_app.config import AppConfig
from autoreview_app.elements import service


class _NovelElementsClient:
    """每篇返回一个独有的生面孔要素;判同调用返回空 matches(全 create)。"""

    def __init__(self):
        self._lock = threading.Lock()

    def chat_json(self, messages, hint):
        user = messages[1]["content"]
        if user.startswith("Extract all research elements"):
            payload = json.loads(user.split("\n", 1)[1])
            pid = payload["paper_id"]
            # quote 必须能在夹具 RB-0001 文本里核真(loose 档:字母序一致)
            return {"paper_id": pid, "elements": [{
                "facet": "material",
                "surface": f"novelite-{pid}",
                "quote": "ball-milled for 4 h at 400 rpm",
                "reading_block_id": f"{pid}-RB-0001",
                "role": "used",
            }]}
        return {"matches": []}


def test_concurrent_imports_keep_both_registry_entries(tmp_path: Path):
    library = tmp_path / "library"
    d1 = write_reading_blocks(library, "SA1")
    d2 = write_reading_blocks(library, "SA2")
    cfg = AppConfig(library_dir=library)
    client = _NovelElementsClient()

    errors: list[BaseException] = []

    def run(paper_dir):
        try:
            service.run_elements_for_paper(paper_dir, client, cfg)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    t1 = threading.Thread(target=run, args=(d1,))
    t2 = threading.Thread(target=run, args=(d2,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    assert not errors, errors

    reg = json.loads(cfg.elements_registry_path.read_text(encoding="utf-8"))
    names = {e["display_name"] for e in reg["entries"].values()}
    # 两个生面孔都必须活下来——锁之前是 last-writer-wins,会丢一个
    assert "novelite-SA1" in names and "novelite-SA2" in names

    for pid in ("SA1", "SA2"):
        doc = json.loads((library / pid / "elements.json").read_text(encoding="utf-8"))
        for occ in doc["occurrences"]:
            assert occ["canonical_id"] in reg["entries"]  # 无悬空
