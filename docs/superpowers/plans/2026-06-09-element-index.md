# 研究要素索引 + 检索/统计屏 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给引擎加一个「研究要素」新层(从每篇 reading blocks 抽出 制备/测量/表征/模拟/分析/材料/条件 要素,逐字锚点核真,注册表归一,SQLite 索引),并在桌面 app 加两个屏:要素检索(三栏工作台)与全库统计(总览→大图→共现)。

**Architecture:** 纯新增层,不改引擎已有代码:引擎侧 7 个新模块 + `scripts/elements/` CLI;桌面侧经 `engine_bridge` 包装为后台任务 + API + 2 个前端视图。数据:每篇 `library/Sxx/elements.json`(可重生)+ `data/elements/`(registry.json + registry_log.jsonl 为长期状态,sqlite 可重建)+ `config/element_seeds.json`(进 git)。三段式归一:种子→引导期一次归并→流式到货匹配。

**Tech Stack:** Python 3.x(stdlib + 引擎现有 ai_client/io_utils)、FastAPI、SQLite、原生 JS(hash 路由 + el() helpers)、pytest(desktop venv)。

**Spec:** `docs/superpowers/specs/2026-06-09-element-index-design.md`(数据模型、原则、界面均以 spec 为准)

---

## 仓库纪律(执行者必读)

1. **git:** 全部工作在分支 `feature/element-index` 上;commit 仅当用户在开工时明确授权(若未授权,跳过所有 Commit 步骤,工作树保留改动);**永不 push**。commit message 不夸大。
2. **不改引擎已有文件**(`Document_Decomposer/src/docdecomp/` 现有模块、现有 scripts);只新增。desktop 侧允许修改的现有文件仅:`config.py`、`api.py`、`importer.py`、`frontend/app.js`、`frontend/index.html`、`frontend/styles.css`、`README.md`。
3. **测试命令**(全部从对应目录运行,desktop venv 已存在):
   - 引擎测试:`cd D:\Project\Vibe_coding\Auto_review\Document_Decomposer` 后运行 `..\desktop_app\.venv\Scripts\python -m pytest tests -q`
   - 桌面测试:`cd D:\Project\Vibe_coding\Auto_review\desktop_app` 后运行 `.venv\Scripts\python -m pytest -q`(已有 119 个测试必须保持全绿)
4. **AI 一律注入**(`chat_json(messages, hint)` 协议);测试用 fake,绝不真调 DeepSeek。
5. 控制台输出用英文 + `flush=True`(沿 build_vocabulary.py 风格);前端文案用中文。

## 关键引擎事实(探索已核实,直接引用勿再猜)

- 逐字事实底座 = `library/<Sxx>/reading_blocks.json`,块结构:`{"reading_block_id": "S09-RB-0003", "text": "...", "caption": "", "section_kind": "front_matter", "include_in_reading": true, ...}`,顶层 `{"paper_id", "reading_blocks": [...]}`。
- AI 客户端:`docdecomp.ai_client.OpenAICompatibleClient(config).chat_json(messages: list[dict], response_schema_hint: str) -> dict`;`load_ai_config(root, config_path)`;异常 `AIClientError`。
- IO:`docdecomp.io_utils.write_json(path, data)`(原子写)、`atomic_write_text(path, text, encoding="utf-8")`。
- 桌面 fake:`tests/_fake_ai.py` 的 `SequencedFakeClient(responses: list[dict])`,`chat_json` 按序吐 canned dict。
- 桌面 job:`jobs.JobRegistry.submit(job: Callable[[report], Any]) -> job_id`;`GET /jobs/{id}`。
- 前端:视图 = `frontend/views/<name>.js` 导出 `async render(view, params)`;注册 = `app.js` 的 `ROUTES` + `index.html` nav 链接 `href="#/<name>"`;工具 = `api.js`(getJSON/postJSON/delJSON)、`ui.js`(el/clear/loading/empty/errorState)。
- `AppConfig.library_dir`;派生路径放 `library_dir.parent` 下(现有 index.db/authors.db 即此模式)。
- 引擎**无测试设施**(本计划 Task 0 创建)。

## 文件结构(全量)

**引擎新增:**
```
Document_Decomposer/
├── config/element_seeds.json                  # 种子:facet 定义 + 同义词族(进 git)
├── src/docdecomp/
│   ├── element_quotes.py                      # 引文核真(宽松存在性 + 数字保真两档)
│   ├── element_values.py                      # 条件数值/单位机械解析
│   ├── element_registry.py                    # 种子加载 + 注册表 CRUD + 流水账 + 重定向
│   ├── element_extraction.py                  # AI 抽取一篇 → elements.json
│   ├── element_matching.py                    # 到货匹配(精确/别名 → AI 批量判)
│   ├── element_bootstrap.py                   # 引导期全局归并 + 超大桶审计
│   └── element_index.py                       # SQLite 建库 + 全部查询函数
├── scripts/elements/
│   ├── ai_extract_elements.py                 # CLI:抽取(单篇/全库缺失)
│   ├── bootstrap_element_registry.py          # CLI:引导期(抽缺→归并→建索引)
│   ├── build_elements_index.py                # CLI:重建 SQLite
│   └── audit_element_buckets.py               # CLI:超大桶审计报告
└── tests/
    ├── conftest.py                            # src/ 上 sys.path
    ├── _fake_ai.py                            # SequencedFakeClient(与桌面同款)
    ├── _fixtures.py                           # 造最小 reading_blocks/elements 的 helper
    └── test_element_{quotes,values,registry,extraction,matching,bootstrap,index}.py
```

**桌面新增/修改:**
```
desktop_app/
├── src/autoreview_app/
│   ├── language_gate.py                       # 新:CJK 语言闸(stdlib only)
│   ├── elements/__init__.py                   # 新:空
│   ├── elements/service.py                    # 新:包装引擎(单篇要素/引导/覆盖率)
│   ├── config.py                              # 改:+4 个 elements 派生路径
│   ├── importer.py                            # 改:包构建后插语言闸
│   └── api.py                                 # 改:+10 条 elements 路由 + import wrapper
├── frontend/
│   ├── views/elements_search.js               # 新:屏A 检索
│   ├── views/elements_stats.js                # 新:屏B 统计
│   ├── app.js                                 # 改:ROUTES +2
│   ├── index.html                             # 改:nav +2
│   └── styles.css                             # 改:+要素屏样式块
└── tests/
    ├── _element_fixtures.py                   # 新:registry/index 测试装置
    ├── test_language_gate.py                  # 新
    ├── test_elements_service.py               # 新
    └── test_api_elements.py                   # 新
```

**统一数据形状(所有任务必须一致):**

occurrence(`elements.json` 的一条):
```json
{
  "facet": "preparation",
  "surface": "ball milling",
  "quote": "The montmorillonite was ball-milled for 4 h at 400 rpm under N2.",
  "reading_block_id": "S09-RB-0042",
  "role": "used",
  "quote_verified": true,
  "digits_verified": true,
  "values": [{"raw": "4 h", "num": "4", "unit": "h"}],
  "canonical_id": null
}
```
`library/Sxx/elements.json` = `{"schema_version": "0.1.0", "paper_id": "S09", "occurrences": [...], "dropped": [{"surface": "...", "reason": "quote_not_found"}]}`

registry entry:
```json
{"id": "elem:preparation/ball-milling", "facet": "preparation", "display_name": "ball milling",
 "aliases": ["mechanical milling"], "redirect_to": null, "origin": "seed", "human_locked": false}
```
registry 文件 = `{"schema_version": "0.1.0", "facets": [...seeds 的 facets...], "entries": {id: entry}}`
log 事件(jsonl 一行)= `{"event": "create|alias|merge|rename", "element_id": "...", "detail": "...", "source": "seed|bootstrap|auto-stream|human", "ts": "<iso8601>"}`

---

### Task 0: 分支 + 引擎测试设施

**Files:**
- Create: `Document_Decomposer/tests/conftest.py`
- Create: `Document_Decomposer/tests/_fake_ai.py`
- Create: `Document_Decomposer/tests/_fixtures.py`

- [ ] **Step 1: 建分支**

```powershell
cd D:\Project\Vibe_coding\Auto_review
git checkout -b feature/element-index
```

- [ ] **Step 2: conftest(把引擎 src 放上 sys.path)**

`Document_Decomposer/tests/conftest.py`:
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
```

- [ ] **Step 3: fake AI 客户端(与桌面同款,引擎测试不跨仓引用)**

`Document_Decomposer/tests/_fake_ai.py`:
```python
from typing import Any


class SequencedFakeClient:
    """chat_json returns the next canned dict, in order."""

    def __init__(self, responses: list[dict[str, Any]]):
        self._responses = list(responses)
        self.calls: list[tuple[list[dict], str]] = []

    def chat_json(self, messages: list[dict[str, str]], response_schema_hint: str) -> dict[str, Any]:
        self.calls.append((messages, response_schema_hint))
        if not self._responses:
            raise AssertionError("SequencedFakeClient ran out of canned responses")
        return self._responses.pop(0)
```

- [ ] **Step 4: 最小论文装置**

`Document_Decomposer/tests/_fixtures.py`:
```python
import json
from pathlib import Path

DEFAULT_TEXTS = [
    ("The montmorillonite was ball-milled for 4 h at 400 rpm under N2.", "methods"),
    ("XRD patterns were recorded with CuKa radiation.", "methods"),
    ("Methane adsorption isotherms were measured at 333 K up to 25 MPa.", "results"),
]


def write_reading_blocks(library: Path, paper_id: str, blocks=None) -> Path:
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
```

- [ ] **Step 5: 空跑确认设施可用**

Run(在 `Document_Decomposer\`): `..\desktop_app\.venv\Scripts\python -m pytest tests -q`
Expected: `no tests ran`(exit code 5 正常,代表收集到 0 个测试、设施无报错)

- [ ] **Step 6: Commit**

```powershell
git add Document_Decomposer/tests
git commit -m "test(engine): pytest scaffolding for element-index work (conftest + fakes + fixtures)"
```

---

### Task 1: 引文核真 `element_quotes.py`

宽松档(只看字母,验「这句话真在这个 block 里」)+ 严格档(字母+数字,验「数字也没被改」);省略号拆段;两档都过才允许解析数值。

**Files:**
- Create: `Document_Decomposer/src/docdecomp/element_quotes.py`
- Test: `Document_Decomposer/tests/test_element_quotes.py`

- [ ] **Step 1: 写失败测试**

`tests/test_element_quotes.py`:
```python
from docdecomp.element_quotes import verify_quote

BLOCK = "The montmorillonite was ball-milled for 4 h at 400 rpm under N2 atmosphere."


def test_exact_quote_passes_both_levels():
    r = verify_quote("ball-milled for 4 h at 400 rpm", BLOCK)
    assert r["quote_verified"] is True
    assert r["digits_verified"] is True


def test_whitespace_and_case_tolerated():
    r = verify_quote("Ball-Milled   for 4 h\nat 400 rpm", BLOCK)
    assert r["quote_verified"] is True
    assert r["digits_verified"] is True


def test_changed_digit_fails_digits_but_passes_loose():
    r = verify_quote("ball-milled for 5 h at 400 rpm", BLOCK)
    assert r["quote_verified"] is True
    assert r["digits_verified"] is False


def test_fabricated_quote_fails():
    r = verify_quote("the sample was acid-washed in HCl overnight", BLOCK)
    assert r["quote_verified"] is False
    assert r["reason"] == "not_found"


def test_ellipsis_fragments_each_checked():
    r = verify_quote("The montmorillonite was ball-milled ... under N2 atmosphere", BLOCK)
    assert r["quote_verified"] is True


def test_too_short_rejected():
    r = verify_quote("4 h", BLOCK)
    assert r["quote_verified"] is False
    assert r["reason"] == "too_short"
```

- [ ] **Step 2: 跑测试确认失败**

Run(`Document_Decomposer\`): `..\desktop_app\.venv\Scripts\python -m pytest tests\test_element_quotes.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'docdecomp.element_quotes'`

- [ ] **Step 3: 实现**

`src/docdecomp/element_quotes.py`:
```python
"""Verbatim quote verification for research elements.

Two levels (both ellipsis-aware), in the spirit of scripts/audit/audit_card_grounding.py:
- loose  (letters only): proves the sentence exists in the cited block, immune to
  Docling stray digits / punctuation noise.
- tight  (letters+digits): proves digits were not altered; ONLY tight-verified
  quotes may feed numeric value parsing (元原则: 宁可漏, 不可编).
"""
from __future__ import annotations

MIN_FRAGMENT_CHARS = 12


def norm_loose(s: str) -> str:
    return "".join(ch.lower() for ch in s if ch.isalpha())


def norm_tight(s: str) -> str:
    return "".join(ch.lower() for ch in s if ch.isalnum())


def _fragments(quote: str) -> list[str]:
    return quote.replace("…", "...").split("...")


def verify_quote(quote: str, block_text: str) -> dict:
    frags = _fragments(quote)
    loose = [norm_loose(f) for f in frags]
    loose = [f for f in loose if len(f) >= MIN_FRAGMENT_CHARS]
    if not loose:
        return {"quote_verified": False, "digits_verified": False, "reason": "too_short"}
    block_loose = norm_loose(block_text)
    if not all(f in block_loose for f in loose):
        return {"quote_verified": False, "digits_verified": False, "reason": "not_found"}
    tight = [norm_tight(f) for f in frags]
    tight = [f for f in tight if len(f) >= MIN_FRAGMENT_CHARS]
    block_tight = norm_tight(block_text)
    digits_ok = bool(tight) and all(f in block_tight for f in tight)
    return {"quote_verified": True, "digits_verified": digits_ok, "reason": ""}
```

- [ ] **Step 4: 跑测试确认通过**

Run: 同上。Expected: 6 passed

- [ ] **Step 5: Commit**

```powershell
git add Document_Decomposer/src/docdecomp/element_quotes.py Document_Decomposer/tests/test_element_quotes.py
git commit -m "feat(engine): two-level verbatim quote verification for elements"
```

---

### Task 2: 条件数值解析 `element_values.py`

**Files:**
- Create: `Document_Decomposer/src/docdecomp/element_values.py`
- Test: `Document_Decomposer/tests/test_element_values.py`

- [ ] **Step 1: 写失败测试**

`tests/test_element_values.py`:
```python
from docdecomp.element_values import parse_values


def test_single_value_with_unit():
    vals = parse_values("measured at 333 K up to 25 MPa")
    assert {"raw": "333 K", "num": "333", "unit": "K"} in vals
    assert {"raw": "25 MPa", "num": "25", "unit": "MPa"} in vals


def test_range_value():
    vals = parse_values("pressures of 0.1-30 MPa were applied")
    assert vals[0]["num"] == "0.1-30"
    assert vals[0]["unit"] == "MPa"


def test_decimal_and_rpm_and_hours():
    vals = parse_values("ball-milled for 4 h at 400 rpm")
    units = {v["unit"] for v in vals}
    assert units == {"h", "rpm"}


def test_no_number_returns_empty():
    assert parse_values("under nitrogen atmosphere") == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `..\desktop_app\.venv\Scripts\python -m pytest tests\test_element_values.py -q`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: 实现**

`src/docdecomp/element_values.py`:
```python
"""Mechanical number+unit extraction from a digits-verified verbatim quote.

Never invents: only regex over the quote text. Ranges keep the raw span (0.1-30).
"""
from __future__ import annotations

import re

_NUM = r"\d+(?:\.\d+)?"
_RANGE = rf"{_NUM}(?:\s*[-–—~]\s*{_NUM})?"
_UNITS = (
    r"°C|K\b|MPa|GPa|kPa|bar\b|atm\b|psi\b|rpm\b|wt\.?%|vol\.?%|%|"
    r"nm\b|µm|μm|mm\b|cm³/g|cm3/g|mmol/g|mg/g|m²/g|m2/g|h\b|hr\b|hours?\b|min\b"
)
_PATTERN = re.compile(rf"(?P<num>{_RANGE})\s*(?P<unit>{_UNITS})")


def parse_values(quote: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for m in _PATTERN.finditer(quote):
        num = re.sub(r"\s*[-–—~]\s*", "-", m.group("num"))
        out.append({"raw": m.group(0).strip(), "num": num, "unit": m.group("unit")})
    return out
```

- [ ] **Step 4: 跑测试确认通过**

Run: 同上。Expected: 4 passed

- [ ] **Step 5: Commit**

```powershell
git add Document_Decomposer/src/docdecomp/element_values.py Document_Decomposer/tests/test_element_values.py
git commit -m "feat(engine): mechanical number+unit parsing for condition elements"
```

---

### Task 3: 种子文件 + 注册表基础 `element_registry.py`(上)

**Files:**
- Create: `Document_Decomposer/config/element_seeds.json`
- Create: `Document_Decomposer/src/docdecomp/element_registry.py`
- Test: `Document_Decomposer/tests/test_element_registry.py`

- [ ] **Step 1: 种子文件(真实起步包,可后续随时改)**

`config/element_seeds.json`:
```json
{
  "schema_version": "0.1.0",
  "facets": [
    {"id": "preparation", "name_zh": "制备/处理", "name_en": "sample preparation & treatment",
     "description": "How samples were made or treated: ball milling, acid washing, hydrothermal synthesis, drying, calcination, sieving."},
    {"id": "measurement", "name_zh": "测量方法", "name_en": "measurement techniques",
     "description": "How target quantities were measured: volumetric adsorption, gravimetric adsorption, breakthrough curves, pulse-decay permeability."},
    {"id": "characterization", "name_zh": "表征", "name_en": "characterization techniques",
     "description": "Instrumental characterization of samples: XRD, SEM, TEM, BET, FTIR, TGA, NMR, mercury intrusion porosimetry."},
    {"id": "simulation", "name_zh": "模拟/计算", "name_en": "computational methods",
     "description": "Simulation or computation methods: GCMC, MD, DFT, lattice Boltzmann, pore network modeling, machine learning models."},
    {"id": "analysis", "name_zh": "分析内容", "name_en": "analysis contents",
     "description": "What was quantified, fitted or analyzed: adsorption isotherm fitting, selectivity, diffusion coefficient, isosteric heat, pore size distribution."},
    {"id": "material", "name_zh": "材料/对象", "name_en": "materials & objects",
     "description": "Materials, minerals, fluids and systems studied: montmorillonite, kaolinite, illite, shale, kerogen, coal, CH4, CO2, H2O, slit pores."},
    {"id": "condition", "name_zh": "条件", "name_en": "experimental/simulation conditions",
     "description": "Numeric operating conditions: temperature, pressure range, moisture/water content, salinity, milling time, pore size. Quote must contain the numbers."}
  ],
  "synonyms": {
    "characterization": {
      "X-ray diffraction": ["XRD", "x ray diffraction"],
      "scanning electron microscopy": ["SEM"],
      "transmission electron microscopy": ["TEM"],
      "N2 adsorption (BET)": ["BET", "BET surface area analysis", "nitrogen adsorption"],
      "Fourier transform infrared spectroscopy": ["FTIR", "FT-IR"],
      "thermogravimetric analysis": ["TGA"],
      "nuclear magnetic resonance": ["NMR"],
      "mercury intrusion porosimetry": ["MIP", "mercury porosimetry"]
    },
    "simulation": {
      "grand canonical Monte Carlo": ["GCMC", "grand-canonical Monte Carlo"],
      "molecular dynamics": ["MD", "molecular dynamics simulation"],
      "density functional theory": ["DFT"],
      "lattice Boltzmann method": ["LBM", "lattice Boltzmann"]
    },
    "preparation": {
      "ball milling": ["mechanical milling", "ball-milling", "ball-milled"]
    },
    "measurement": {
      "volumetric adsorption measurement": ["volumetric method"],
      "gravimetric adsorption measurement": ["gravimetric method"]
    },
    "analysis": {
      "adsorption isotherm": ["adsorption isotherms", "excess adsorption isotherm"],
      "isosteric heat of adsorption": ["isosteric heat"],
      "pore size distribution": ["PSD"]
    },
    "material": {
      "montmorillonite": ["Na-montmorillonite", "Ca-montmorillonite", "MMT"],
      "methane": ["CH4", "CH₄"],
      "carbon dioxide": ["CO2", "CO₂"]
    },
    "condition": {}
  }
}
```

- [ ] **Step 2: 写失败测试(基础:加载/建表/ID/查找/持久化)**

`tests/test_element_registry.py`:
```python
import json
from pathlib import Path

from docdecomp.element_registry import (
    add_alias,
    create_entry,
    element_id,
    find_by_surface,
    load_registry,
    load_seeds,
    merge_entries,
    new_registry_from_seeds,
    norm_key,
    rename_entry,
    resolve_id,
    save_registry,
    slugify,
)

ENGINE_ROOT = Path(__file__).resolve().parents[1]


def _seeds():
    return load_seeds(ENGINE_ROOT / "config" / "element_seeds.json")


def test_slug_and_id():
    assert slugify("Grand canonical Monte Carlo!") == "grand-canonical-monte-carlo"
    assert element_id("simulation", "GCMC method") == "elem:simulation/gcmc-method"


def test_seeds_load_and_registry_init():
    seeds = _seeds()
    assert {f["id"] for f in seeds["facets"]} >= {"preparation", "characterization", "condition"}
    reg = new_registry_from_seeds(seeds)
    eid = "elem:characterization/x-ray-diffraction"
    assert eid in reg["entries"]
    assert "XRD" in reg["entries"][eid]["aliases"]
    assert reg["entries"][eid]["origin"] == "seed"


def test_find_by_surface_matches_display_and_alias_normalized():
    reg = new_registry_from_seeds(_seeds())
    eid = "elem:characterization/x-ray-diffraction"
    assert find_by_surface(reg, "characterization", "xrd") == eid
    assert find_by_surface(reg, "characterization", "X-ray  Diffraction") == eid
    assert find_by_surface(reg, "characterization", "neutron scattering") is None


def test_create_alias_merge_resolve_and_log(tmp_path: Path):
    log = tmp_path / "registry_log.jsonl"
    reg = new_registry_from_seeds(_seeds())
    a = create_entry(reg, "preparation", "acid washing", "auto-stream", log)
    b = create_entry(reg, "preparation", "acid treatment", "auto-stream", log)
    add_alias(reg, a, "HCl washing", "auto-stream", log)
    assert find_by_surface(reg, "preparation", "hcl washing") == a
    merge_entries(reg, b, a, "human", log)
    assert reg["entries"][b]["redirect_to"] == a
    assert resolve_id(reg, b) == a
    rename_entry(reg, a, "acid washing treatment", log)
    assert reg["entries"][a]["display_name"] == "acid washing treatment"
    assert reg["entries"][a]["human_locked"] is True
    events = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert [e["event"] for e in events] == ["create", "create", "alias", "merge", "alias", "rename"]


def test_create_entry_id_collision_gets_suffix(tmp_path: Path):
    log = tmp_path / "log.jsonl"
    reg = new_registry_from_seeds(_seeds())
    a = create_entry(reg, "material", "kerogen", "bootstrap", log)
    b = create_entry(reg, "material", "Kerogen", "bootstrap", log)
    assert a == "elem:material/kerogen"
    assert b == "elem:material/kerogen-2"


def test_save_and_load_roundtrip(tmp_path: Path):
    reg = new_registry_from_seeds(_seeds())
    p = tmp_path / "registry.json"
    save_registry(p, reg)
    assert load_registry(p) == reg


def test_norm_key():
    assert norm_key("  Ball-Milling ") == norm_key("ball milling")
```

- [ ] **Step 3: 跑测试确认失败**

Run: `..\desktop_app\.venv\Scripts\python -m pytest tests\test_element_registry.py -q`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 4: 实现**

`src/docdecomp/element_registry.py`:
```python
"""Element registry: canonical entries + aliases + append-only log.

Entries are append-only: IDs never change and are never reused; merge = redirect.
Human events (source=="human") are the durable curation layer (SP3 seed).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .io_utils import write_json

SCHEMA_VERSION = "0.1.0"


def slugify(name: str) -> str:
    s = "".join(ch.lower() if ch.isalnum() else "-" for ch in name.strip())
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "unnamed"


def element_id(facet: str, name: str) -> str:
    return f"elem:{facet}/{slugify(name)}"


def norm_key(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def load_seeds(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def new_registry_from_seeds(seeds: dict) -> dict:
    reg = {"schema_version": SCHEMA_VERSION, "facets": seeds["facets"], "entries": {}}
    for facet, families in (seeds.get("synonyms") or {}).items():
        for canonical, aliases in families.items():
            eid = element_id(facet, canonical)
            reg["entries"][eid] = {
                "id": eid,
                "facet": facet,
                "display_name": canonical,
                "aliases": list(aliases),
                "redirect_to": None,
                "origin": "seed",
                "human_locked": False,
            }
    return reg


def load_registry(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_registry(path: Path, registry: dict) -> None:
    write_json(Path(path), registry)


def append_log(log_path: Path, event: dict) -> None:
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    event = {**event, "ts": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def create_entry(registry: dict, facet: str, display_name: str, origin: str, log_path: Path) -> str:
    eid = element_id(facet, display_name)
    n = 2
    while eid in registry["entries"]:
        eid = f"{element_id(facet, display_name)}-{n}"
        n += 1
    registry["entries"][eid] = {
        "id": eid,
        "facet": facet,
        "display_name": display_name,
        "aliases": [],
        "redirect_to": None,
        "origin": origin,
        "human_locked": False,
    }
    append_log(log_path, {"event": "create", "element_id": eid, "detail": display_name, "source": origin})
    return eid


def add_alias(registry: dict, eid: str, alias: str, source: str, log_path: Path) -> None:
    entry = registry["entries"][eid]
    if norm_key(alias) == norm_key(entry["display_name"]):
        return
    if any(norm_key(alias) == norm_key(a) for a in entry["aliases"]):
        return
    entry["aliases"].append(alias)
    append_log(log_path, {"event": "alias", "element_id": eid, "detail": alias, "source": source})


def merge_entries(registry: dict, from_id: str, into_id: str, source: str, log_path: Path) -> None:
    registry["entries"][from_id]["redirect_to"] = into_id
    if source == "human":
        registry["entries"][into_id]["human_locked"] = True
    append_log(log_path, {"event": "merge", "element_id": from_id, "detail": into_id, "source": source})


def resolve_id(registry: dict, eid: str) -> str:
    seen = set()
    while eid in registry["entries"] and registry["entries"][eid].get("redirect_to"):
        if eid in seen:
            break
        seen.add(eid)
        eid = registry["entries"][eid]["redirect_to"]
    return eid


def rename_entry(registry: dict, eid: str, display_name: str, log_path: Path) -> None:
    entry = registry["entries"][eid]
    add_alias(registry, eid, entry["display_name"], "human", log_path)
    entry["display_name"] = display_name
    entry["human_locked"] = True
    append_log(log_path, {"event": "rename", "element_id": eid, "detail": display_name, "source": "human"})


def find_by_surface(registry: dict, facet: str, surface: str) -> str | None:
    key = norm_key(surface)
    for eid, entry in registry["entries"].items():
        if entry["facet"] != facet:
            continue
        if key == norm_key(entry["display_name"]) or any(key == norm_key(a) for a in entry["aliases"]):
            return resolve_id(registry, eid)
    return None
```

说明:`rename_entry` 先把旧显示名收进 aliases(老名字仍可搜到)再改名,所以 log 里 rename 之前会多一条 alias 事件——上面测试的期望序列已包含它。

- [ ] **Step 5: 跑测试确认通过**

Run: 同上。Expected: 7 passed

- [ ] **Step 6: Commit**

```powershell
git add Document_Decomposer/config/element_seeds.json Document_Decomposer/src/docdecomp/element_registry.py Document_Decomposer/tests/test_element_registry.py
git commit -m "feat(engine): element seeds + registry (stable IDs, aliases, redirects, append-only log)"
```

---

### Task 4: AI 抽取一篇 `element_extraction.py`

**Files:**
- Create: `Document_Decomposer/src/docdecomp/element_extraction.py`
- Test: `Document_Decomposer/tests/test_element_extraction.py`

- [ ] **Step 1: 写失败测试**

`tests/test_element_extraction.py`:
```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `..\desktop_app\.venv\Scripts\python -m pytest tests\test_element_extraction.py -q`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: 实现**

`src/docdecomp/element_extraction.py`:
```python
"""AI extraction of research elements from one paper's reading blocks.

Output: library/<Sxx>/elements.json. Every occurrence carries a verbatim quote
verified against its cited reading block (loose level mandatory); numeric values
are parsed only when the digits-verified level also passes. canonical_id is left
null here — matching/normalization is a separate step (element_matching).
"""
from __future__ import annotations

import json
from pathlib import Path

from .element_quotes import verify_quote
from .element_values import parse_values
from .io_utils import write_json

SCHEMA_VERSION = "0.1.0"
MAX_BLOCK_CHARS = 700
MAX_QUOTE_CHARS = 300

ELEMENTS_SCHEMA_HINT = (
    'Return only one JSON object: {"paper_id": str, "elements": [{"facet": str, '
    '"surface": str, "quote": str, "reading_block_id": str, "role": "used"|"mentioned", '
    '"proposed_facet": str (optional)}]}. Do not wrap the JSON in Markdown.'
)

_SYSTEM = (
    "You extract RESEARCH ELEMENTS from one paper's reading blocks: every concrete "
    "technique, method, material and condition the paper involves.\n"
    "Rules:\n"
    "1. role='used' ONLY for what THIS paper itself did/measured/simulated/analyzed. "
    "Things only cited from other papers or general background are role='mentioned'. "
    "In a review article almost everything is 'mentioned'.\n"
    "2. For EVERY element give one verbatim quote (<=300 chars) copied EXACTLY, "
    "character-for-character, from ONE reading block, and that block's reading_block_id. "
    "The quote must contain the element mention. For 'condition' elements the quote "
    "must include the numeric phrase. Never paraphrase inside the quote.\n"
    "3. surface = the element name as this paper writes it (short noun phrase).\n"
    "4. facet must be one of the listed facet ids. If none fits, use facet='other' "
    "and set proposed_facet to a short English category name.\n"
    "5. Be exhaustive on methods/characterization/simulation/conditions; list each "
    "distinct element once per role (pick its clearest quote).\n"
    "6. Output strictly the JSON schema; no Markdown."
)


def _blocks_for_prompt(reading: dict, max_block_chars: int) -> list[dict]:
    out = []
    for b in reading.get("reading_blocks") or []:
        if not b.get("include_in_reading", True):
            continue
        text = (b.get("text") or b.get("caption") or "").strip()
        if not text:
            continue
        out.append(
            {
                "reading_block_id": b["reading_block_id"],
                "section_kind": b.get("section_kind", ""),
                "text": text[:max_block_chars],
            }
        )
    return out


def build_elements_prompt(reading: dict, seeds: dict, max_block_chars: int = MAX_BLOCK_CHARS) -> list[dict]:
    payload = {
        "paper_id": reading.get("paper_id", ""),
        "facets": [{"id": f["id"], "description": f["description"]} for f in seeds["facets"]],
        "reading_blocks": _blocks_for_prompt(reading, max_block_chars),
    }
    user = (
        "Extract all research elements from this paper.\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    return [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}]


def parse_elements_response(raw: dict, reading: dict, seeds: dict) -> tuple[list[dict], list[dict]]:
    facet_ids = {f["id"] for f in seeds["facets"]}
    block_text = {
        b["reading_block_id"]: (b.get("text") or b.get("caption") or "")
        for b in reading.get("reading_blocks") or []
    }
    occurrences: list[dict] = []
    dropped: list[dict] = []
    for item in raw.get("elements") or []:
        surface = str(item.get("surface") or "").strip()
        facet = str(item.get("facet") or "").strip()
        quote = str(item.get("quote") or "").strip()[:MAX_QUOTE_CHARS]
        rb_id = str(item.get("reading_block_id") or "").strip()
        role = str(item.get("role") or "").strip()
        if facet == "other" and item.get("proposed_facet"):
            facet = "proposed:" + str(item["proposed_facet"]).strip()
        elif facet not in facet_ids:
            dropped.append({"surface": surface, "reason": "bad_facet"})
            continue
        if role not in ("used", "mentioned"):
            dropped.append({"surface": surface, "reason": "bad_role"})
            continue
        if rb_id not in block_text:
            dropped.append({"surface": surface, "reason": "unknown_block"})
            continue
        check = verify_quote(quote, block_text[rb_id])
        if not check["quote_verified"]:
            dropped.append({"surface": surface, "reason": "quote_not_found" if check["reason"] == "not_found" else check["reason"]})
            continue
        values = parse_values(quote) if facet == "condition" and check["digits_verified"] else []
        occurrences.append(
            {
                "facet": facet,
                "surface": surface,
                "quote": quote,
                "reading_block_id": rb_id,
                "role": role,
                "quote_verified": True,
                "digits_verified": check["digits_verified"],
                "values": values,
                "canonical_id": None,
            }
        )
    return occurrences, dropped


def run_element_extraction(paper_dir: Path, client, seeds: dict) -> dict:
    reading = json.loads((paper_dir / "reading_blocks.json").read_text(encoding="utf-8"))
    messages = build_elements_prompt(reading, seeds)
    raw = client.chat_json(messages, ELEMENTS_SCHEMA_HINT)
    occurrences, dropped = parse_elements_response(raw, reading, seeds)
    result = {
        "schema_version": SCHEMA_VERSION,
        "paper_id": reading.get("paper_id", paper_dir.name),
        "occurrences": occurrences,
        "dropped": dropped,
    }
    write_json(paper_dir / "elements.json", result)
    return result
```

- [ ] **Step 4: 跑测试确认通过**

Run: 同上。Expected: 2 passed

- [ ] **Step 5: Commit**

```powershell
git add Document_Decomposer/src/docdecomp/element_extraction.py Document_Decomposer/tests/test_element_extraction.py
git commit -m "feat(engine): AI element extraction with verbatim-anchor gate (drop on failed verify)"
```

---

### Task 5: 到货匹配 `element_matching.py`

**Files:**
- Create: `Document_Decomposer/src/docdecomp/element_matching.py`
- Test: `Document_Decomposer/tests/test_element_matching.py`

- [ ] **Step 1: 写失败测试**

`tests/test_element_matching.py`:
```python
import json
from pathlib import Path

from _fake_ai import SequencedFakeClient
from _fixtures import write_reading_blocks
from docdecomp.element_matching import match_paper_elements
from docdecomp.element_registry import load_seeds, new_registry_from_seeds

ENGINE_ROOT = Path(__file__).resolve().parents[1]
SEEDS = load_seeds(ENGINE_ROOT / "config" / "element_seeds.json")


def _write_elements(paper_dir: Path, occurrences):
    data = {"schema_version": "0.1.0", "paper_id": paper_dir.name,
            "occurrences": occurrences, "dropped": []}
    (paper_dir / "elements.json").write_text(json.dumps(data), encoding="utf-8")


def _occ(facet, surface):
    return {"facet": facet, "surface": surface, "quote": "q", "reading_block_id": "S90-RB-0001",
            "role": "used", "quote_verified": True, "digits_verified": False,
            "values": [], "canonical_id": None}


def test_exact_and_alias_resolve_without_ai(tmp_path: Path):
    paper_dir = write_reading_blocks(tmp_path, "S90")
    _write_elements(paper_dir, [_occ("characterization", "XRD"),
                                _occ("preparation", "ball-milled")])
    reg = new_registry_from_seeds(SEEDS)
    log = tmp_path / "log.jsonl"
    stats = match_paper_elements(paper_dir, reg, None, log)
    data = json.loads((paper_dir / "elements.json").read_text(encoding="utf-8"))
    ids = {o["surface"]: o["canonical_id"] for o in data["occurrences"]}
    assert ids["XRD"] == "elem:characterization/x-ray-diffraction"
    assert ids["ball-milled"] == "elem:preparation/ball-milling"
    assert stats["ai_calls"] == 0 and stats["created"] == 0


def test_unresolved_with_ai_match_and_create(tmp_path: Path):
    paper_dir = write_reading_blocks(tmp_path, "S90")
    _write_elements(paper_dir, [_occ("characterization", "powder X-ray diffraction"),
                                _occ("characterization", "neutron scattering")])
    reg = new_registry_from_seeds(SEEDS)
    log = tmp_path / "log.jsonl"
    client = SequencedFakeClient([
        {"matches": [
            {"surface": "powder X-ray diffraction", "element_id": "elem:characterization/x-ray-diffraction"},
            {"surface": "neutron scattering", "element_id": None},
        ]}
    ])
    stats = match_paper_elements(paper_dir, reg, client, log)
    data = json.loads((paper_dir / "elements.json").read_text(encoding="utf-8"))
    ids = {o["surface"]: o["canonical_id"] for o in data["occurrences"]}
    assert ids["powder X-ray diffraction"] == "elem:characterization/x-ray-diffraction"
    assert ids["neutron scattering"] == "elem:characterization/neutron-scattering"
    assert "powder X-ray diffraction" in reg["entries"]["elem:characterization/x-ray-diffraction"]["aliases"]
    assert stats["created"] == 1 and stats["ai_calls"] == 1


def test_no_client_creates_entries_directly(tmp_path: Path):
    paper_dir = write_reading_blocks(tmp_path, "S90")
    _write_elements(paper_dir, [_occ("material", "kerogen type II")])
    reg = new_registry_from_seeds(SEEDS)
    stats = match_paper_elements(paper_dir, reg, None, tmp_path / "log.jsonl")
    assert stats["created"] == 1
    data = json.loads((paper_dir / "elements.json").read_text(encoding="utf-8"))
    assert data["occurrences"][0]["canonical_id"] == "elem:material/kerogen-type-ii"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `..\desktop_app\.venv\Scripts\python -m pytest tests\test_element_matching.py -q`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: 实现**

`src/docdecomp/element_matching.py`:
```python
"""Streaming match of one paper's element surfaces against the registry.

Pass 1: exact/alias (normalized). Pass 2 (optional, batched per facet): AI maps
each unresolved surface to an existing entry or null. Null -> create a new entry
(never force-fit). Proposed facets ("proposed:<name>") always create new entries.
"""
from __future__ import annotations

import json
from pathlib import Path

from .element_registry import add_alias, create_entry, find_by_surface, resolve_id
from .io_utils import write_json

MATCH_SCHEMA_HINT = (
    'Return only one JSON object: {"matches": [{"surface": str, "element_id": str|null}]}. '
    "Do not wrap the JSON in Markdown."
)

_SYSTEM = (
    "You map raw research-element surface forms onto an existing registry of canonical "
    "elements for ONE facet. Map a surface to an element_id ONLY if they denote the same "
    "technique/material/quantity (abbreviation, spelling or wording variant). If it is a "
    "genuinely different element, return null for it. Never guess."
)


def build_match_prompt(facet: str, surfaces: list[str], candidates: list[dict]) -> list[dict]:
    payload = {
        "facet": facet,
        "unresolved_surfaces": surfaces,
        "registry_candidates": [
            {"element_id": c["id"], "display_name": c["display_name"], "aliases": c["aliases"]}
            for c in candidates
        ],
    }
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def match_paper_elements(paper_dir: Path, registry: dict, client, log_path: Path) -> dict:
    path = paper_dir / "elements.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    stats = {"resolved_exact": 0, "resolved_ai": 0, "created": 0, "ai_calls": 0}

    unresolved: dict[str, list[str]] = {}
    for occ in data["occurrences"]:
        facet, surface = occ["facet"], occ["surface"]
        if facet.startswith("proposed:"):
            continue  # handled below as create
        eid = find_by_surface(registry, facet, surface)
        if eid:
            occ["canonical_id"] = eid
            stats["resolved_exact"] += 1
        else:
            unresolved.setdefault(facet, [])
            if surface not in unresolved[facet]:
                unresolved[facet].append(surface)

    ai_matched: dict[tuple[str, str], str | None] = {}
    if client is not None:
        for facet, surfaces in unresolved.items():
            candidates = [
                e for e in registry["entries"].values()
                if e["facet"] == facet and not e.get("redirect_to")
            ]
            raw = client.chat_json(build_match_prompt(facet, surfaces, candidates), MATCH_SCHEMA_HINT)
            stats["ai_calls"] += 1
            for m in raw.get("matches") or []:
                ai_matched[(facet, str(m.get("surface")))] = m.get("element_id")

    for occ in data["occurrences"]:
        if occ["canonical_id"] is not None:
            continue
        facet, surface = occ["facet"], occ["surface"]
        eid = ai_matched.get((facet, surface))
        if eid and eid in registry["entries"]:
            eid = resolve_id(registry, eid)
            add_alias(registry, eid, surface, "auto-stream", log_path)
            occ["canonical_id"] = eid
            stats["resolved_ai"] += 1
        else:
            existing = find_by_surface(registry, facet, surface)
            if existing:
                occ["canonical_id"] = existing
                stats["resolved_exact"] += 1
            else:
                new_id = create_entry(registry, facet, surface, "auto-stream", log_path)
                occ["canonical_id"] = new_id
                stats["created"] += 1

    write_json(path, data)
    return stats
```

- [ ] **Step 4: 跑测试确认通过**

Run: 同上。Expected: 3 passed

- [ ] **Step 5: Commit**

```powershell
git add Document_Decomposer/src/docdecomp/element_matching.py Document_Decomposer/tests/test_element_matching.py
git commit -m "feat(engine): streaming surface->registry matching (exact/alias + batched AI, create-not-force)"
```

---

### Task 6: 引导期归并 `element_bootstrap.py`

**Files:**
- Create: `Document_Decomposer/src/docdecomp/element_bootstrap.py`
- Test: `Document_Decomposer/tests/test_element_bootstrap.py`

- [ ] **Step 1: 写失败测试**

`tests/test_element_bootstrap.py`:
```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `..\desktop_app\.venv\Scripts\python -m pytest tests\test_element_bootstrap.py -q`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: 实现**

`src/docdecomp/element_bootstrap.py`:
```python
"""One-time bootstrap consolidation: all extracted surfaces -> registry v1.

Per facet, surfaces (with counts) go to the AI in chunks; existing canonical names
(seeds + earlier chunks) are shown so later chunks attach instead of duplicating.
Anti-superbucket discipline (ISSUES I12): groups capped at 8 members in-prompt and
audited mechanically afterwards. Every surface MUST end up assigned: leftovers get
their own entries (never force-fit, never silently dropped). After consolidation,
all papers' occurrences are assigned via exact/alias matching only (no AI).
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .element_matching import match_paper_elements
from .element_registry import (
    add_alias,
    create_entry,
    find_by_surface,
    new_registry_from_seeds,
    save_registry,
)

CONSOLIDATE_SCHEMA_HINT = (
    'Return only one JSON object: {"groups": [{"canonical": str, "members": [str, ...]}]}. '
    "Do not wrap the JSON in Markdown."
)

_SYSTEM = (
    "You consolidate raw research-element surface forms into canonical groups for ONE facet.\n"
    "Rules:\n"
    "1. Group ONLY true same-thing variants (abbreviation, spelling, plural, word order). "
    "Different techniques/materials/quantities must stay separate.\n"
    "2. A group has at most 8 members. No catch-all groups like 'other methods'.\n"
    "3. canonical = the most common full English name. If a surface matches one of the "
    "existing canonical names provided, use exactly that existing name as the group's canonical.\n"
    "4. Every input surface must appear in exactly one group; a group of one is fine.\n"
    "5. Output strictly the JSON schema; no Markdown."
)

CHUNK_SIZE = 150


def collect_surfaces(library_dir: Path) -> dict[str, Counter]:
    counts: dict[str, Counter] = {}
    for elements_path in sorted(Path(library_dir).glob("*/elements.json")):
        data = json.loads(elements_path.read_text(encoding="utf-8"))
        for occ in data.get("occurrences") or []:
            counts.setdefault(occ["facet"], Counter())[occ["surface"]] += 1
    return counts


def build_consolidation_prompt(facet: str, surface_counts: list[tuple[str, int]],
                               existing_canonicals: list[str]) -> list[dict]:
    payload = {
        "facet": facet,
        "existing_canonical_names": existing_canonicals,
        "surfaces": [{"surface": s, "papers": n} for s, n in surface_counts],
    }
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def bootstrap_registry(library_dir: Path, seeds: dict, client, data_dir: Path,
                       chunk_size: int = CHUNK_SIZE, progress=lambda m: None) -> dict:
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    log_path = data_dir / "registry_log.jsonl"
    registry = new_registry_from_seeds(seeds)

    for facet, counter in sorted(collect_surfaces(library_dir).items()):
        surfaces = counter.most_common()
        for start in range(0, len(surfaces), chunk_size):
            chunk = surfaces[start:start + chunk_size]
            existing = sorted(
                e["display_name"] for e in registry["entries"].values()
                if e["facet"] == facet and not e.get("redirect_to")
            )
            progress(f"consolidating {facet}: {start + len(chunk)}/{len(surfaces)}")
            raw = client.chat_json(
                build_consolidation_prompt(facet, chunk, existing), CONSOLIDATE_SCHEMA_HINT
            )
            assigned: set[str] = set()
            for group in raw.get("groups") or []:
                canonical = str(group.get("canonical") or "").strip()
                members = [str(m).strip() for m in (group.get("members") or []) if str(m).strip()]
                if not canonical or not members:
                    continue
                eid = find_by_surface(registry, facet, canonical) or create_entry(
                    registry, facet, canonical, "bootstrap", log_path
                )
                for member in members[:8]:  # in-prompt cap, enforced mechanically too
                    add_alias(registry, eid, member, "bootstrap", log_path)
                    assigned.add(member)
            for surface, _ in chunk:  # leftovers: own entries, never dropped
                if surface not in assigned and not find_by_surface(registry, facet, surface):
                    create_entry(registry, facet, surface, "bootstrap", log_path)

    for elements_path in sorted(Path(library_dir).glob("*/elements.json")):
        match_paper_elements(elements_path.parent, registry, None, log_path)

    save_registry(data_dir / "registry.json", registry)
    return registry


def superbucket_report(registry: dict, max_aliases: int = 12) -> list[dict]:
    flagged = []
    for entry in registry["entries"].values():
        if len(entry.get("aliases") or []) > max_aliases:
            flagged.append({"id": entry["id"], "facet": entry["facet"],
                            "display_name": entry["display_name"],
                            "alias_count": len(entry["aliases"])})
    return sorted(flagged, key=lambda x: -x["alias_count"])
```

- [ ] **Step 4: 跑测试确认通过**

Run: 同上。Expected: 3 passed

- [ ] **Step 5: Commit**

```powershell
git add Document_Decomposer/src/docdecomp/element_bootstrap.py Document_Decomposer/tests/test_element_bootstrap.py
git commit -m "feat(engine): one-time bootstrap consolidation with anti-superbucket discipline"
```

---

### Task 7: SQLite 索引 `element_index.py`

**Files:**
- Create: `Document_Decomposer/src/docdecomp/element_index.py`
- Test: `Document_Decomposer/tests/test_element_index.py`

- [ ] **Step 1: 写失败测试**

`tests/test_element_index.py`:
```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `..\desktop_app\.venv\Scripts\python -m pytest tests\test_element_index.py -q`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: 实现**

`src/docdecomp/element_index.py`:
```python
"""Rebuildable SQLite index over per-paper elements.json + the registry.

Mirrors the desktop sqlite_index.py house style: CREATE IF NOT EXISTS once,
clear+reinsert in ONE transaction, short-lived connections, row_factory=Row.
Occurrences store the redirect-RESOLVED element_id, so all queries stay simple.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from .element_registry import resolve_id

_REINDEX_LOCK = threading.Lock()

_CREATE = """
CREATE TABLE IF NOT EXISTS elements (
    element_id TEXT PRIMARY KEY, facet TEXT, slug TEXT, display_name TEXT,
    aliases_json TEXT, human_locked INTEGER
);
CREATE TABLE IF NOT EXISTS occurrences (
    paper_id TEXT, element_id TEXT, facet TEXT, surface TEXT, quote TEXT,
    reading_block_id TEXT, role TEXT, digits_verified INTEGER, values_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_occ_elem ON occurrences(element_id);
CREATE INDEX IF NOT EXISTS idx_occ_paper ON occurrences(paper_id);
CREATE INDEX IF NOT EXISTS idx_occ_facet ON occurrences(facet);
"""


def _slug(element_id: str) -> str:
    return element_id.split("/", 1)[1] if "/" in element_id else element_id


def _facet_of(element_id: str) -> str:
    return element_id.split(":", 1)[1].split("/", 1)[0]


def build_index(library_dir: Path, registry: dict, db_path: Path) -> int:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    elem_rows = [
        (e["id"], e["facet"], _slug(e["id"]), e["display_name"],
         json.dumps(e.get("aliases") or [], ensure_ascii=False), int(e.get("human_locked", False)))
        for e in registry["entries"].values()
        if not e.get("redirect_to")
    ]
    occ_rows = []
    paper_ids = set()
    for elements_path in sorted(Path(library_dir).glob("*/elements.json")):
        data = json.loads(elements_path.read_text(encoding="utf-8"))
        paper_ids.add(data.get("paper_id") or elements_path.parent.name)
        for o in data.get("occurrences") or []:
            eid = o.get("canonical_id")
            if not eid:
                continue
            eid = resolve_id(registry, eid)
            occ_rows.append(
                (data.get("paper_id") or elements_path.parent.name, eid, _facet_of(eid),
                 o["surface"], o["quote"], o["reading_block_id"], o["role"],
                 int(o.get("digits_verified", False)),
                 json.dumps(o.get("values") or [], ensure_ascii=False))
            )
    with _REINDEX_LOCK:
        conn = sqlite3.connect(db_path)
        try:
            conn.executescript(_CREATE)
            with conn:
                conn.execute("DELETE FROM elements")
                conn.execute("DELETE FROM occurrences")
                conn.executemany("INSERT INTO elements VALUES (?,?,?,?,?,?)", elem_rows)
                conn.executemany("INSERT INTO occurrences VALUES (?,?,?,?,?,?,?,?,?)", occ_rows)
        finally:
            conn.close()
    return len(paper_ids)


def _conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _role_clause(role: str | None) -> tuple[str, list]:
    return ("AND o.role = ?", [role]) if role else ("", [])


def query_stats(db_path: Path, facet: str, role: str | None = "used") -> list[dict]:
    clause, args = _role_clause(role)
    conn = _conn(db_path)
    try:
        rows = conn.execute(
            f"""SELECT e.element_id AS id, e.slug, e.display_name,
                       COUNT(DISTINCT o.paper_id) AS papers
                FROM elements e JOIN occurrences o ON o.element_id = e.element_id
                WHERE e.facet = ? {clause}
                GROUP BY e.element_id ORDER BY papers DESC, e.display_name""",
            [facet, *args],
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def query_overview(db_path: Path, top_n: int = 5, role: str | None = "used") -> dict:
    conn = _conn(db_path)
    try:
        facets = [r["facet"] for r in conn.execute(
            "SELECT DISTINCT facet FROM elements ORDER BY facet").fetchall()]
        total_papers = conn.execute(
            "SELECT COUNT(DISTINCT paper_id) AS n FROM occurrences").fetchone()["n"]
    finally:
        conn.close()
    out = {"library_papers": total_papers, "facets": []}
    for facet in facets:
        items = query_stats(db_path, facet, role)
        out["facets"].append({"id": facet, "total_elements": len(items), "top": items[:top_n]})
    return out


def search_elements(db_path: Path, q: str, facet: str | None = None) -> list[dict]:
    like = f"%{q.lower()}%"
    conn = _conn(db_path)
    try:
        facet_clause = "AND e.facet = ?" if facet else ""
        args = [like, like] + ([facet] if facet else [])
        rows = conn.execute(
            f"""SELECT e.element_id AS id, e.facet, e.slug, e.display_name, e.aliases_json,
                       (SELECT COUNT(DISTINCT o.paper_id) FROM occurrences o
                        WHERE o.element_id = e.element_id AND o.role = 'used') AS papers
                FROM elements e
                WHERE (LOWER(e.display_name) LIKE ? OR LOWER(e.aliases_json) LIKE ?) {facet_clause}
                ORDER BY papers DESC LIMIT 50""",
            args,
        ).fetchall()
        return [{**dict(r), "aliases": json.loads(r["aliases_json"])} for r in rows]
    finally:
        conn.close()


def get_element(db_path: Path, facet: str, slug: str, role: str | None = "used") -> dict | None:
    conn = _conn(db_path)
    try:
        e = conn.execute(
            "SELECT * FROM elements WHERE facet = ? AND slug = ?", (facet, slug)
        ).fetchone()
        if e is None:
            return None
        clause, args = _role_clause(role)
        occ = conn.execute(
            f"SELECT * FROM occurrences o WHERE o.element_id = ? {clause} ORDER BY paper_id",
            [e["element_id"], *args],
        ).fetchall()
    finally:
        conn.close()
    papers: dict[str, list] = {}
    for o in occ:
        papers.setdefault(o["paper_id"], []).append(
            {"surface": o["surface"], "quote": o["quote"], "reading_block_id": o["reading_block_id"],
             "role": o["role"], "values": json.loads(o["values_json"])}
        )
    return {
        "id": e["element_id"], "facet": e["facet"], "slug": e["slug"],
        "display_name": e["display_name"], "aliases": json.loads(e["aliases_json"]),
        "human_locked": bool(e["human_locked"]),
        "paper_count": len(papers),
        "papers": [{"paper_id": pid, "quotes": qs} for pid, qs in sorted(papers.items())],
    }


def query_cooccurrence(db_path: Path, facet: str, slug: str, role: str = "used") -> dict:
    conn = _conn(db_path)
    try:
        e = conn.execute(
            "SELECT element_id FROM elements WHERE facet = ? AND slug = ?", (facet, slug)
        ).fetchone()
        if e is None:
            return {"anchor": None, "m": 0, "groups": []}
        anchor = e["element_id"]
        rows = conn.execute(
            """SELECT o.facet, o.element_id AS id, e.display_name,
                      COUNT(DISTINCT o.paper_id) AS n
               FROM occurrences o JOIN elements e ON e.element_id = o.element_id
               WHERE o.role = ? AND o.element_id != ?
                 AND o.paper_id IN (SELECT DISTINCT paper_id FROM occurrences
                                    WHERE element_id = ? AND role = ?)
               GROUP BY o.element_id ORDER BY n DESC""",
            (role, anchor, anchor, role),
        ).fetchall()
        m = conn.execute(
            "SELECT COUNT(DISTINCT paper_id) AS n FROM occurrences WHERE element_id = ? AND role = ?",
            (anchor, role),
        ).fetchone()["n"]
    finally:
        conn.close()
    groups: dict[str, list] = {}
    for r in rows:
        groups.setdefault(r["facet"], []).append(
            {"id": r["id"], "display_name": r["display_name"], "n": r["n"]}
        )
    return {"anchor": anchor, "m": m,
            "groups": [{"facet": f, "items": items} for f, items in sorted(groups.items())]}


def query_combination(db_path: Path, element_ids: list[str], role: str = "used") -> dict:
    if not element_ids:
        return {"papers": []}
    placeholders = ",".join("?" for _ in element_ids)
    conn = _conn(db_path)
    try:
        pids = [r["paper_id"] for r in conn.execute(
            f"""SELECT paper_id FROM occurrences
                WHERE element_id IN ({placeholders}) AND role = ?
                GROUP BY paper_id
                HAVING COUNT(DISTINCT element_id) = ?
                ORDER BY paper_id""",
            [*element_ids, role, len(element_ids)],
        ).fetchall()]
        papers = []
        for pid in pids:
            occ = conn.execute(
                f"""SELECT o.*, e.display_name FROM occurrences o
                    JOIN elements e ON e.element_id = o.element_id
                    WHERE o.paper_id = ? AND o.element_id IN ({placeholders}) AND o.role = ?""",
                [pid, *element_ids, role],
            ).fetchall()
            papers.append({
                "paper_id": pid,
                "matches": [{"element_id": o["element_id"], "display_name": o["display_name"],
                             "surface": o["surface"], "quote": o["quote"],
                             "reading_block_id": o["reading_block_id"],
                             "values": json.loads(o["values_json"])} for o in occ],
            })
    finally:
        conn.close()
    return {"papers": papers}


def paper_elements(db_path: Path, paper_id: str) -> dict:
    conn = _conn(db_path)
    try:
        rows = conn.execute(
            """SELECT o.*, e.display_name FROM occurrences o
               JOIN elements e ON e.element_id = o.element_id
               WHERE o.paper_id = ? ORDER BY o.facet, e.display_name""",
            (paper_id,),
        ).fetchall()
    finally:
        conn.close()
    groups: dict[str, list] = {}
    for o in rows:
        groups.setdefault(o["facet"], []).append(
            {"element_id": o["element_id"], "display_name": o["display_name"],
             "surface": o["surface"], "quote": o["quote"], "role": o["role"],
             "reading_block_id": o["reading_block_id"], "values": json.loads(o["values_json"])}
        )
    return {"paper_id": paper_id,
            "groups": [{"facet": f, "items": items} for f, items in sorted(groups.items())]}
```

- [ ] **Step 4: 跑测试确认通过**

Run: 同上。Expected: 8 passed

- [ ] **Step 5: 全引擎测试回归**

Run: `..\desktop_app\.venv\Scripts\python -m pytest tests -q`
Expected: 全部通过(约 33 个)

- [ ] **Step 6: Commit**

```powershell
git add Document_Decomposer/src/docdecomp/element_index.py Document_Decomposer/tests/test_element_index.py
git commit -m "feat(engine): rebuildable SQLite element index with stats/search/cooccurrence/combination queries"
```

---

### Task 8: 引擎 CLI 脚本(4 个薄壳)

脚本只做:解析参数 → 调模块 → 打印结果(沿 build_vocabulary.py 风格)。逻辑已全在模块里且有测试,脚本只验 `--help` 可跑。

**Files:**
- Create: `Document_Decomposer/scripts/elements/ai_extract_elements.py`
- Create: `Document_Decomposer/scripts/elements/bootstrap_element_registry.py`
- Create: `Document_Decomposer/scripts/elements/build_elements_index.py`
- Create: `Document_Decomposer/scripts/elements/audit_element_buckets.py`

- [ ] **Step 1: 抽取脚本**

`scripts/elements/ai_extract_elements.py`:
```python
"""Extract research elements for one paper or all papers missing elements.json."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from docdecomp.ai_client import OpenAICompatibleClient, load_ai_config  # noqa: E402
from docdecomp.element_extraction import run_element_extraction  # noqa: E402
from docdecomp.element_registry import load_seeds  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--library-dir", default=str(ROOT / "library"))
    ap.add_argument("--config", default=None)
    ap.add_argument("--paper", default=None, help="one paper id (e.g. S09); default: all missing")
    ap.add_argument("--force", action="store_true", help="re-extract even if elements.json exists")
    args = ap.parse_args()

    config = load_ai_config(ROOT, Path(args.config) if args.config else None)
    client = OpenAICompatibleClient(config)
    seeds = load_seeds(ROOT / "config" / "element_seeds.json")
    library = Path(args.library_dir)

    if args.paper:
        targets = [library / args.paper]
    else:
        targets = [p.parent for p in sorted(library.glob("*/reading_blocks.json"))
                   if args.force or not (p.parent / "elements.json").exists()]
    ok = failed = 0
    for paper_dir in targets:
        try:
            result = run_element_extraction(paper_dir, client, seeds)
            ok += 1
            print(f"[{paper_dir.name}] {len(result['occurrences'])} occurrences, "
                  f"{len(result['dropped'])} dropped", flush=True)
        except Exception as exc:  # noqa: BLE001 — batch keeps going, summary at end
            failed += 1
            print(f"[{paper_dir.name}] FAILED: {type(exc).__name__}: {exc}", flush=True)
    print(f"done: {ok} ok, {failed} failed of {len(targets)}", flush=True)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: 引导脚本**

`scripts/elements/bootstrap_element_registry.py`:
```python
"""One-time bootstrap: consolidate all extracted surfaces -> registry v1 + index.

Run ai_extract_elements.py first (this script consolidates, it does not extract).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from docdecomp.ai_client import OpenAICompatibleClient, load_ai_config  # noqa: E402
from docdecomp.element_bootstrap import bootstrap_registry, superbucket_report  # noqa: E402
from docdecomp.element_index import build_index  # noqa: E402
from docdecomp.element_registry import load_seeds  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--library-dir", default=str(ROOT / "library"))
    ap.add_argument("--config", default=None)
    ap.add_argument("--data-dir", default=str(ROOT / "data" / "elements"))
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    if (data_dir / "registry.json").exists():
        print("registry.json already exists; bootstrap is one-time. "
              "Delete it deliberately if you really mean to redo (human edits in the "
              "log are replayable, but think first).", flush=True)
        return 1
    config = load_ai_config(ROOT, Path(args.config) if args.config else None)
    client = OpenAICompatibleClient(config)
    seeds = load_seeds(ROOT / "config" / "element_seeds.json")
    registry = bootstrap_registry(Path(args.library_dir), seeds, client, data_dir,
                                  progress=lambda m: print(m, flush=True))
    n = build_index(Path(args.library_dir), registry, data_dir / "elements_index.sqlite")
    print(f"registry: {len(registry['entries'])} entries; index over {n} papers", flush=True)
    flagged = superbucket_report(registry)
    for f in flagged:
        print(f"[superbucket?] {f['id']} aliases={f['alias_count']}", flush=True)
    print(f"superbuckets flagged: {len(flagged)} (review manually if >0)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: 重建索引脚本 + 审计脚本**

`scripts/elements/build_elements_index.py`:
```python
"""Rebuild data/elements/elements_index.sqlite from elements.json files + registry."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from docdecomp.element_index import build_index  # noqa: E402
from docdecomp.element_registry import load_registry  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--library-dir", default=str(ROOT / "library"))
    ap.add_argument("--data-dir", default=str(ROOT / "data" / "elements"))
    args = ap.parse_args()
    data_dir = Path(args.data_dir)
    registry = load_registry(data_dir / "registry.json")
    n = build_index(Path(args.library_dir), registry, data_dir / "elements_index.sqlite")
    print(f"index rebuilt over {n} papers", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`scripts/elements/audit_element_buckets.py`:
```python
"""Report oversized registry entries (possible over-merge; see ISSUES I12)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from docdecomp.element_bootstrap import superbucket_report  # noqa: E402
from docdecomp.element_registry import load_registry  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", default=str(ROOT / "data" / "elements"))
    ap.add_argument("--max-aliases", type=int, default=12)
    args = ap.parse_args()
    registry = load_registry(Path(args.data_dir) / "registry.json")
    flagged = superbucket_report(registry, max_aliases=args.max_aliases)
    for f in flagged:
        print(f"{f['id']}  aliases={f['alias_count']}  ({f['display_name']})", flush=True)
    print(f"total flagged: {len(flagged)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 冒烟验证(--help 全部能跑)**

Run(`Document_Decomposer\`):
```powershell
..\desktop_app\.venv\Scripts\python scripts\elements\ai_extract_elements.py --help
..\desktop_app\.venv\Scripts\python scripts\elements\bootstrap_element_registry.py --help
..\desktop_app\.venv\Scripts\python scripts\elements\build_elements_index.py --help
..\desktop_app\.venv\Scripts\python scripts\elements\audit_element_buckets.py --help
```
Expected: 4 个都打印 usage,exit 0

- [ ] **Step 5: Commit**

```powershell
git add Document_Decomposer/scripts/elements
git commit -m "feat(engine): elements CLI wrappers (extract / bootstrap / reindex / bucket audit)"
```

---

### Task 9: 桌面 config 路径 + `elements/service.py`

**Files:**
- Modify: `desktop_app/src/autoreview_app/config.py`(在 `authors_db` property 之后追加)
- Create: `desktop_app/src/autoreview_app/elements/__init__.py`(空文件)
- Create: `desktop_app/src/autoreview_app/elements/service.py`
- Test: `desktop_app/tests/test_elements_service.py`
- Create: `desktop_app/tests/_element_fixtures.py`

- [ ] **Step 1: 写失败测试**

`tests/_element_fixtures.py`:
```python
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
```

`tests/test_elements_service.py`:
```python
import json
from pathlib import Path

from _element_fixtures import elements_ai_response, write_reading_blocks
from _fake_ai import SequencedFakeClient
from autoreview_app.config import AppConfig
from autoreview_app.elements import service


def test_config_elements_paths(tmp_path: Path):
    cfg = AppConfig(library_dir=tmp_path / "library")
    assert cfg.elements_data_dir == tmp_path / "data" / "elements"
    assert cfg.elements_db == tmp_path / "data" / "elements" / "elements_index.sqlite"
    assert cfg.elements_registry_path == tmp_path / "data" / "elements" / "registry.json"
    assert cfg.elements_log_path == tmp_path / "data" / "elements" / "registry_log.jsonl"


def test_run_elements_for_paper_extracts_matches_and_indexes(tmp_path: Path):
    library = tmp_path / "library"
    paper_dir = write_reading_blocks(library, "S90")
    cfg = AppConfig(library_dir=library)
    client = SequencedFakeClient([elements_ai_response("S90")])
    stats = service.run_elements_for_paper(paper_dir, client, cfg)
    data = json.loads((paper_dir / "elements.json").read_text(encoding="utf-8"))
    assert all(o["canonical_id"] for o in data["occurrences"])
    assert cfg.elements_db.exists()
    assert cfg.elements_registry_path.exists()
    assert stats["occurrences"] == 2


def test_coverage_counts(tmp_path: Path):
    library = tmp_path / "library"
    write_reading_blocks(library, "S90")
    paper91 = write_reading_blocks(library, "S91")
    cfg = AppConfig(library_dir=library)
    client = SequencedFakeClient([elements_ai_response("S91")])
    service.run_elements_for_paper(paper91, client, cfg)
    cov = service.coverage(cfg)
    assert cov["papers"] == 2 and cov["with_elements"] == 1
    assert cov["pending"] == ["S90"]


def test_bootstrap_second_run_skips_reconsolidation(tmp_path: Path):
    library = tmp_path / "library"
    cfg = AppConfig(library_dir=library)
    write_reading_blocks(library, "S90")
    client1 = SequencedFakeClient([
        elements_ai_response("S90"),
        {"groups": []},  # consolidation chunk: characterization(空组,机械兜底命中种子)
        {"groups": []},  # consolidation chunk: preparation
    ])
    service.run_bootstrap(cfg, client1, lambda m: None)
    assert cfg.elements_registry_path.exists()

    write_reading_blocks(library, "S91")
    client2 = SequencedFakeClient([elements_ai_response("S91")])
    summary = service.run_bootstrap(cfg, client2, lambda m: None)
    assert summary["papers_indexed"] == 2
    # 第二次只允许 1 次 AI 调用(S91 抽取);surfaces 全部 exact/alias 命中种子,
    # 不发生匹配 AI 调用,更绝不重新归并。
    assert client2.call_count == 1
```

- [ ] **Step 2: 跑测试确认失败**

Run(`desktop_app\`): `.venv\Scripts\python -m pytest tests\test_elements_service.py -q`
Expected: FAIL — AttributeError(elements_data_dir)/ModuleNotFoundError

- [ ] **Step 3: config.py 追加派生路径**

在 `AppConfig` 的 `authors_db` property 后追加(保持 frozen dataclass 不变):
```python
    @property
    def elements_data_dir(self) -> Path:
        """Element registry + index live under <root>/data/elements (long-lived state)."""
        return self.library_dir.parent / "data" / "elements"

    @property
    def elements_db(self) -> Path:
        return self.elements_data_dir / "elements_index.sqlite"

    @property
    def elements_registry_path(self) -> Path:
        return self.elements_data_dir / "registry.json"

    @property
    def elements_log_path(self) -> Path:
        return self.elements_data_dir / "registry_log.jsonl"
```

- [ ] **Step 4: service 实现**

`src/autoreview_app/elements/__init__.py` 留空。`src/autoreview_app/elements/service.py`:
```python
"""Desktop wrapper over the engine's element modules.

All engine logic stays in Document_Decomposer (docdecomp.element_*); this module
only wires paths/config and composes the per-paper and bootstrap flows.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .. import engine_bridge

engine_bridge.ensure_engine_scripts_on_path()

from docdecomp.element_bootstrap import bootstrap_registry, superbucket_report  # noqa: E402
from docdecomp.element_extraction import run_element_extraction  # noqa: E402
from docdecomp.element_index import build_index  # noqa: E402
from docdecomp.element_matching import match_paper_elements  # noqa: E402
from docdecomp.element_registry import (  # noqa: E402
    load_registry,
    load_seeds,
    new_registry_from_seeds,
    save_registry,
)

from ..config import AppConfig  # noqa: E402

Report = Callable[[str], None]


def engine_root() -> Path:
    return engine_bridge.ENGINE_SCRIPTS.parent


def seeds_path() -> Path:
    return engine_root() / "config" / "element_seeds.json"


def ensure_registry(config: AppConfig) -> dict:
    if config.elements_registry_path.exists():
        return load_registry(config.elements_registry_path)
    registry = new_registry_from_seeds(load_seeds(seeds_path()))
    config.elements_data_dir.mkdir(parents=True, exist_ok=True)
    save_registry(config.elements_registry_path, registry)
    return registry


def run_elements_for_paper(paper_dir: Path, client: Any, config: AppConfig,
                           report: Report = lambda m: None) -> dict:
    seeds = load_seeds(seeds_path())
    report("extracting elements")
    result = run_element_extraction(paper_dir, client, seeds)
    registry = ensure_registry(config)
    report("matching elements against registry")
    match_paper_elements(paper_dir, registry, client, config.elements_log_path)
    save_registry(config.elements_registry_path, registry)
    report("updating elements index")
    build_index(config.library_dir, registry, config.elements_db)
    return {"occurrences": len(result["occurrences"]), "dropped": len(result["dropped"])}


def list_paper_dirs(config: AppConfig) -> list[Path]:
    return [p.parent for p in sorted(config.library_dir.glob("*/reading_blocks.json"))]


def coverage(config: AppConfig) -> dict:
    papers = list_paper_dirs(config)
    pending = [p.name for p in papers if not (p / "elements.json").exists()]
    deferred = [p.parent.name for p in sorted(config.library_dir.glob("*/language_gate.json"))]
    return {"papers": len(papers), "with_elements": len(papers) - len(pending),
            "pending": pending, "deferred": deferred}


def run_bootstrap(config: AppConfig, client: Any, report: Report = lambda m: None) -> dict:
    """First run: extract missing -> ONE-TIME consolidation -> index.

    Later runs (registry already exists): extract missing + stream-match only —
    NEVER re-consolidates, so the registry stays frozen (anti-I12 drift). This
    also doubles as the "retry pending papers" action: re-clicking the build
    button tops up coverage incrementally.
    """
    seeds = load_seeds(seeds_path())
    papers = list_paper_dirs(config)
    extracted = failed = 0
    for paper_dir in papers:
        if (paper_dir / "elements.json").exists():
            continue
        try:
            report(f"extracting {paper_dir.name}")
            run_element_extraction(paper_dir, client, seeds)
            extracted += 1
        except Exception as exc:  # noqa: BLE001 — 单篇失败不挡全局, 留待补
            failed += 1
            report(f"{paper_dir.name} failed: {type(exc).__name__}")
    config.elements_data_dir.mkdir(parents=True, exist_ok=True)
    if config.elements_registry_path.exists():
        report("registry exists: stream-matching new papers (no re-consolidation)")
        registry = load_registry(config.elements_registry_path)
        for paper_dir in papers:
            if (paper_dir / "elements.json").exists():
                match_paper_elements(paper_dir, registry, client, config.elements_log_path)
        save_registry(config.elements_registry_path, registry)
    else:
        report("consolidating registry (one-time)")
        registry = bootstrap_registry(config.library_dir, seeds, client,
                                      config.elements_data_dir, progress=report)
    n = build_index(config.library_dir, registry, config.elements_db)
    flagged = superbucket_report(registry)
    report(f"done: index over {n} papers; {len(flagged)} superbucket flags")
    return {"papers_indexed": n, "extracted": extracted, "extract_failed": failed,
            "entries": len(registry["entries"]), "superbuckets": flagged}
```


- [ ] **Step 5: 跑测试确认通过 + 全量回归**

Run: `.venv\Scripts\python -m pytest tests\test_elements_service.py -q` → Expected: 4 passed
Run: `.venv\Scripts\python -m pytest -q` → Expected: 119 + 3 全绿

- [ ] **Step 6: Commit**

```powershell
git add desktop_app/src/autoreview_app/config.py desktop_app/src/autoreview_app/elements desktop_app/tests/_element_fixtures.py desktop_app/tests/test_elements_service.py
git commit -m "feat(desktop): elements service wrapping engine extraction/matching/index + config paths"
```

---

### Task 10: 语言闸 `language_gate.py` + importer 接线(根治 I17 新导入路径)

**Files:**
- Create: `desktop_app/src/autoreview_app/language_gate.py`
- Modify: `desktop_app/src/autoreview_app/importer.py`
- Test: `desktop_app/tests/test_language_gate.py`

- [ ] **Step 1: 写失败测试**

`tests/test_language_gate.py`:
```python
import json
from pathlib import Path

from autoreview_app.language_gate import check_package_language, cjk_ratio


def _package(tmp_path: Path, paper_id: str, texts: list[str]) -> Path:
    paper_dir = tmp_path / paper_id
    paper_dir.mkdir(parents=True)
    blocks = [{"block_id": f"{paper_id}-BLK-{i:04d}", "text": t} for i, t in enumerate(texts)]
    (paper_dir / "content_blocks.json").write_text(
        json.dumps({"paper_id": paper_id, "blocks": blocks}, ensure_ascii=False), encoding="utf-8")
    return paper_dir


def test_cjk_ratio():
    assert cjk_ratio("pure english text") == 0.0
    assert cjk_ratio("纯中文文本") == 1.0
    assert 0.4 < cjk_ratio("half 中文 half english 文本测试 here") < 0.6


def test_english_package_passes(tmp_path: Path):
    paper_dir = _package(tmp_path, "S90", ["Methane adsorption on clay.", "XRD was used."])
    gate = check_package_language(paper_dir)
    assert gate["deferred"] is False


def test_chinese_package_deferred(tmp_path: Path):
    paper_dir = _package(tmp_path, "S91", ["页岩气吸附机理研究", "蒙脱石的甲烷吸附等温线测定", "Abstract"])
    gate = check_package_language(paper_dir)
    assert gate["deferred"] is True
    assert gate["cjk_ratio"] > 0.15


def test_import_pdf_stops_before_ai_on_cjk(tmp_path: Path, monkeypatch):
    """import_pdf must write language_gate.json and skip AI stages for CJK papers."""
    from autoreview_app import importer

    def fake_build(pdf_path, library_dir, docling_json_dir, extractor):
        _package(library_dir, "S91", ["页岩气吸附机理研究综述,中文正文内容很长。" * 20])
        return "S91"

    monkeypatch.setattr(importer, "build_package_from_pdf", fake_build)

    def explode(*a, **k):
        raise AssertionError("AI pipeline must not run for deferred CJK paper")

    monkeypatch.setattr(importer, "run_ai_pipeline", explode)
    progress: list[str] = []
    paper_id = importer.import_pdf(Path("fake.pdf"), tmp_path, tmp_path / "docling",
                                   extractor=None, client_factory=lambda d: None,
                                   progress=progress.append)
    assert paper_id == "S91"
    assert (tmp_path / "S91" / "language_gate.json").exists()
    assert any("deferred" in m for m in progress)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv\Scripts\python -m pytest tests\test_language_gate.py -q`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: 实现 language_gate.py(纯 stdlib,不依赖引擎)**

`src/autoreview_app/language_gate.py`:
```python
"""CJK language gate: defer Chinese-body PDFs at import instead of crashing.

Fixes the new-import path of ISSUES I17 (PyMuPDF shreds CJK into thousands of
blocks -> sections stage output overflows -> AIClientError crash). Ratio rule
follows the I8 cleanup convention: >=15% CJK characters (vs CJK+ASCII letters).
"""
from __future__ import annotations

import json
from pathlib import Path

CJK_THRESHOLD = 0.15

_CJK_RANGES = ((0x4E00, 0x9FFF), (0x3400, 0x4DBF))


def _is_cjk(ch: str) -> bool:
    code = ord(ch)
    return any(lo <= code <= hi for lo, hi in _CJK_RANGES)


def cjk_ratio(text: str) -> float:
    cjk = sum(1 for ch in text if _is_cjk(ch))
    ascii_letters = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    denom = cjk + ascii_letters
    return (cjk / denom) if denom else 0.0


def check_package_language(paper_dir: Path) -> dict:
    content = json.loads((paper_dir / "content_blocks.json").read_text(encoding="utf-8"))
    text = "\n".join((b.get("text") or "") for b in content.get("blocks") or [])
    ratio = cjk_ratio(text)
    return {"status": "deferred_cjk" if ratio >= CJK_THRESHOLD else "ok",
            "cjk_ratio": round(ratio, 4), "deferred": ratio >= CJK_THRESHOLD}
```

- [ ] **Step 4: importer.py 接线**

`src/autoreview_app/importer.py` 全文改为(原逻辑保留,插入闸门;`run_ai_pipeline`/`build_package_from_pdf` 改为模块级名字以便测试 monkeypatch):
```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .ai.stages import run_ai_pipeline
from .engine_bridge import build_package_from_pdf
from .extract.base import PdfExtractor
from .language_gate import check_package_language


def import_pdf(
    pdf_path: Path,
    library_dir: Path,
    docling_json_dir: Path,
    extractor: PdfExtractor,
    client_factory: Callable[[Path], Any],
    progress: Callable[[str], None],
) -> str:
    """PDF -> clean package (M2a) -> language gate -> AI card (M2b). Returns the paper id.

    client_factory is given the paper dir and returns an AI client; this lets the
    real app build one client from config while tests inject a fake seeded from the
    just-built package.
    """
    progress("extracting pdf")
    paper_id = build_package_from_pdf(pdf_path, library_dir, docling_json_dir, extractor)
    paper_dir = library_dir / paper_id
    gate = check_package_language(paper_dir)
    if gate["deferred"]:
        (paper_dir / "language_gate.json").write_text(
            json.dumps(gate, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        progress("deferred: cjk content (中文文献暂不支持,已搁置)")
        return paper_id
    progress("running ai stages")
    client = client_factory(paper_dir)
    run_ai_pipeline(paper_dir, client)
    progress("done")
    return paper_id
```

- [ ] **Step 5: 跑测试确认通过 + 全量回归**

Run: `.venv\Scripts\python -m pytest tests\test_language_gate.py -q` → 4 passed
Run: `.venv\Scripts\python -m pytest -q` → 全绿(原 import 相关测试不该破:英文包 gate 直接放行)

- [ ] **Step 6: Commit**

```powershell
git add desktop_app/src/autoreview_app/language_gate.py desktop_app/src/autoreview_app/importer.py desktop_app/tests/test_language_gate.py
git commit -m "feat(desktop): CJK language gate at import (defer, do not crash) — fixes new-import path of ISSUES I17"
```

---

### Task 11: API 端点(查询组 + bootstrap job + 人工操作 + import 接 elements)

**Files:**
- Modify: `desktop_app/src/autoreview_app/api.py`
- Test: `desktop_app/tests/test_api_elements.py`

- [ ] **Step 1: 写失败测试**

`tests/test_api_elements.py`:
```python
import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from _element_fixtures import elements_ai_response, write_reading_blocks
from _fake_ai import SequencedFakeClient
from autoreview_app.api import create_app
from autoreview_app.config import AppConfig
from autoreview_app.elements import service


def _built_library(tmp_path: Path) -> AppConfig:
    library = tmp_path / "library"
    cfg = AppConfig(library_dir=library)
    for pid in ("S90", "S91"):
        paper_dir = write_reading_blocks(library, pid)
        client = SequencedFakeClient([elements_ai_response(pid)])
        service.run_elements_for_paper(paper_dir, client, cfg)
    return cfg


def _client(cfg: AppConfig, **kw) -> TestClient:
    return TestClient(create_app(cfg, **kw))


def test_elements_endpoints_503_before_build(tmp_path: Path):
    cfg = AppConfig(library_dir=tmp_path / "library")
    (tmp_path / "library").mkdir()
    c = _client(cfg)
    assert c.get("/elements/overview").status_code == 503
    assert c.get("/elements/stats?facet=characterization").status_code == 503


def test_overview_stats_search_detail_cooccurrence(tmp_path: Path):
    cfg = _built_library(tmp_path)
    c = _client(cfg)
    ov = c.get("/elements/overview").json()
    assert ov["library_papers"] == 2
    stats = c.get("/elements/stats?facet=characterization").json()
    assert stats["items"][0]["papers"] == 2
    hits = c.get("/elements?q=xrd").json()["elements"]
    assert hits and hits[0]["facet"] == "characterization"
    detail = c.get("/elements/characterization/x-ray-diffraction").json()
    assert detail["paper_count"] == 2 and detail["papers"][0]["quotes"]
    co = c.get("/elements/preparation/ball-milling/cooccurrence").json()
    assert co["m"] == 2
    assert c.get("/elements/characterization/nope").status_code == 404


def test_combination_query_and_paper_elements(tmp_path: Path):
    cfg = _built_library(tmp_path)
    c = _client(cfg)
    res = c.post("/elements/query", json={"element_ids": [
        "elem:characterization/x-ray-diffraction", "elem:preparation/ball-milling"]}).json()
    assert {p["paper_id"] for p in res["papers"]} == {"S90", "S91"}
    pe = c.get("/papers/S90/elements").json()
    assert {g["facet"] for g in pe["groups"]} == {"characterization", "preparation"}


def test_put_rename_and_merge_rebuilds_index(tmp_path: Path):
    cfg = _built_library(tmp_path)
    c = _client(cfg)
    r = c.put("/elements/characterization/x-ray-diffraction",
              json={"display_name": "X 射线衍射"})
    assert r.status_code == 200 and r.json()["entry"]["display_name"] == "X 射线衍射"
    stats = c.get("/elements/stats?facet=characterization").json()
    assert stats["items"][0]["display_name"] == "X 射线衍射"
    log = cfg.elements_log_path.read_text(encoding="utf-8")
    assert '"rename"' in log and '"human"' in log


def test_coverage_and_bootstrap_job(tmp_path: Path):
    library = tmp_path / "library"
    cfg = AppConfig(library_dir=library)
    write_reading_blocks(library, "S90")

    def fake_bootstrap(report):
        report("bootstrapping")
        return {"papers_indexed": 1}

    c = _client(cfg, elements_bootstrap_runner=fake_bootstrap)
    cov = c.get("/elements/coverage").json()
    assert cov["papers"] == 1 and cov["pending"] == ["S90"]
    job_id = c.post("/elements/bootstrap").json()["job_id"]
    for _ in range(50):
        status = c.get(f"/jobs/{job_id}").json()
        if status["status"] != "running":
            break
        time.sleep(0.05)
    assert status["status"] == "succeeded"
    assert status["result"]["papers_indexed"] == 1
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv\Scripts\python -m pytest tests\test_api_elements.py -q`
Expected: FAIL — 404/TypeError(端点与参数不存在)

- [ ] **Step 3: api.py 增量实现**

在 `api.py` 顶部 imports 区追加:
```python
from .elements import service as elements_service
from docdecomp.element_index import (
    get_element,
    paper_elements,
    query_combination,
    query_cooccurrence,
    query_overview,
    query_stats,
    search_elements,
)
from docdecomp.element_registry import (
    add_alias as registry_add_alias,
    load_registry,
    merge_entries,
    rename_entry,
    save_registry,
)
```
(`docdecomp` 已可导入:`elements_service` 模块 import 时执行了 `ensure_engine_scripts_on_path()`,保持 `from .elements import ...` 在 docdecomp imports **之前**。)

类型别名区追加:
```python
BootstrapRunner = Callable[[Callable[[str], None]], dict[str, Any]]
```

Pydantic 模型区追加:
```python
class ElementsQuery(BaseModel):
    element_ids: list[str]
    role: str = "used"


class ElementUpdate(BaseModel):
    display_name: str | None = None
    add_alias: str | None = None
    merge_into: str | None = None
```

`create_app` 签名追加参数 `elements_bootstrap_runner: BootstrapRunner | None = None`。

路由(**注意:静态路径必须先于 `/elements/{facet}/{slug}` 声明**;放在现有路由同一函数体内):
```python
    def _elements_db_or_503() -> Path:
        if not config.elements_db.exists():
            raise HTTPException(status_code=503, detail="elements index not built")
        return config.elements_db

    def _role(role: str) -> str | None:
        # query param convention: "used"(默认) / "mentioned" / "all"(=不过滤)
        return None if role == "all" else role

    @app.get("/elements/overview")
    def elements_overview(top_n: int = 5, role: str = "used") -> dict:
        return query_overview(_elements_db_or_503(), top_n=top_n, role=_role(role))

    @app.get("/elements/coverage")
    def elements_coverage() -> dict:
        return elements_service.coverage(config)

    @app.get("/elements/stats")
    def elements_stats(facet: str, role: str = "used") -> dict:
        return {"facet": facet, "items": query_stats(_elements_db_or_503(), facet, _role(role))}

    @app.get("/elements")
    def elements_search(q: str = "", facet: str | None = None) -> dict:
        return {"elements": search_elements(_elements_db_or_503(), q, facet)}

    @app.post("/elements/query")
    def elements_query(req: ElementsQuery) -> dict:
        return query_combination(_elements_db_or_503(), req.element_ids, req.role)

    @app.post("/elements/bootstrap")
    def elements_bootstrap() -> dict:
        runner = elements_bootstrap_runner or _default_bootstrap_runner(config)
        return {"job_id": jobs.submit(runner)}

    @app.get("/elements/{facet}/{slug}/cooccurrence")
    def element_cooccurrence(facet: str, slug: str, role: str = "used") -> dict:
        return query_cooccurrence(_elements_db_or_503(), facet, slug, role)

    @app.get("/elements/{facet}/{slug}")
    def element_detail(facet: str, slug: str, role: str = "all") -> dict:
        detail = get_element(_elements_db_or_503(), facet, slug, role=_role(role))
        if detail is None:
            raise HTTPException(status_code=404, detail="unknown element")
        return detail

    @app.put("/elements/{facet}/{slug}")
    def element_update(facet: str, slug: str, req: ElementUpdate) -> dict:
        registry = load_registry(config.elements_registry_path)
        eid = f"elem:{facet}/{slug}"
        if eid not in registry["entries"]:
            raise HTTPException(status_code=404, detail="unknown element")
        if req.display_name:
            rename_entry(registry, eid, req.display_name, config.elements_log_path)
        if req.add_alias:
            registry_add_alias(registry, eid, req.add_alias, "human", config.elements_log_path)
        if req.merge_into:
            if req.merge_into not in registry["entries"]:
                raise HTTPException(status_code=400, detail="merge target unknown")
            merge_entries(registry, eid, req.merge_into, "human", config.elements_log_path)
        save_registry(config.elements_registry_path, registry)
        from docdecomp.element_index import build_index
        build_index(config.library_dir, registry, config.elements_db)
        return {"entry": registry["entries"][eid]}

    @app.get("/papers/{paper_id}/elements")
    def paper_elements_route(paper_id: str) -> dict:
        return paper_elements(_elements_db_or_503(), paper_id)
```

默认 bootstrap runner(放在 api.py 模块级,挨着其它 default runner;与现有真实 AI 客户端构建方式一致 —— 参考本文件中 `/papers/import` 默认 runner 如何调 `build_ai_client`,用同一来源):
```python
def _default_bootstrap_runner(config: AppConfig) -> BootstrapRunner:
    def run(report: Callable[[str], None]) -> dict[str, Any]:
        from .ai.client import build_ai_client
        client = build_ai_client(elements_service.engine_root())
        return elements_service.run_bootstrap(config, client, report)
    return run
```

最后,把**默认 import runner**(仅当 `import_runner is None` 走默认路径时)包一层 elements 阶段——在 create_app 内找到现有 import runner 的选择处(`/papers/import` 路由上方、形如 `runner = import_runner or ...` 的那行),紧随其后加:
```python
    if import_runner is None:
        runner = _wrap_import_with_elements(runner, config)
```
模块级 wrapper:
```python
def _wrap_import_with_elements(base: ImportRunner, config: AppConfig) -> ImportRunner:
    """After a successful default import, extract+index elements. Failures mark
    the paper pending (elements_pending.json) instead of failing the job (P0)."""
    def run(pdf_path: Path, report: Callable[[str], None]) -> str:
        paper_id = base(pdf_path, report)
        paper_dir = config.library_dir / paper_id
        if (paper_dir / "language_gate.json").exists():
            return paper_id
        try:
            from .ai.client import build_ai_client
            client = build_ai_client(elements_service.engine_root())
            elements_service.run_elements_for_paper(paper_dir, client, config, report)
        except Exception as exc:  # noqa: BLE001 — graceful: paper stays usable
            report(f"elements pending: {type(exc).__name__}")
            (paper_dir / "elements_pending.json").write_text(
                json.dumps({"error": str(exc)}, ensure_ascii=False), encoding="utf-8")
        return paper_id
    return run
```
(api.py 若未 import `json` 则补上。)

- [ ] **Step 4: 跑测试确认通过 + 全量回归**

Run: `.venv\Scripts\python -m pytest tests\test_api_elements.py -q` → 5 passed
Run: `.venv\Scripts\python -m pytest -q` → 全绿(注入了 import_runner 的旧测试不受 wrapper 影响)

- [ ] **Step 5: Commit**

```powershell
git add desktop_app/src/autoreview_app/api.py desktop_app/tests/test_api_elements.py
git commit -m "feat(desktop): elements API (overview/stats/search/detail/cooccur/query/curate/bootstrap/coverage) + import wiring"
```

---

### Task 12: 前端屏A 检索 `views/elements_search.js` + 路由/导航/样式

**Files:**
- Create: `desktop_app/frontend/views/elements_search.js`
- Modify: `desktop_app/frontend/app.js`(ROUTES 加 `elements`)
- Modify: `desktop_app/frontend/index.html`(nav 加链接)
- Modify: `desktop_app/frontend/styles.css`(追加要素屏样式块)

- [ ] **Step 1: 路由与导航**

`app.js` 的 `ROUTES` 加两行(stats 留给 Task 13,一起加省一次改动):
```javascript
  elements: () => import("/assets/views/elements_search.js"),
  stats: () => import("/assets/views/elements_stats.js"),
```
`index.html` nav 里(现有链接旁)加:
```html
      <a href="#/elements">要素检索</a>
      <a href="#/stats">全库统计</a>
```

- [ ] **Step 2: styles.css 追加(文件末尾)**

```css
/* ---- 研究要素屏(elements_search / elements_stats) ---- */
.elements-layout { display: flex; gap: 12px; align-items: flex-start; }
.facet-tree { flex: 0 0 220px; max-height: 70vh; overflow-y: auto; }
.facet-tree h4 { margin: 10px 0 4px; }
.facet-tree label { display: block; padding: 2px 4px; cursor: pointer; }
.facet-tree label:hover { background: #eef1f6; }
.elements-results { flex: 1 1 auto; min-width: 0; }
.elements-detail { flex: 0 0 320px; max-height: 70vh; overflow-y: auto; }
.chip { display: inline-block; border: 1px solid var(--accent); border-radius: 12px;
        padding: 1px 10px; margin: 0 6px 6px 0; cursor: pointer; background: #eef1f6; }
.chip .x { margin-left: 6px; color: #888; }
.quote-box { border-left: 3px solid var(--accent); padding: 4px 8px; margin: 6px 0;
             background: #fafaf8; font-size: 0.92em; }
.bar-row { display: flex; align-items: center; gap: 8px; margin: 3px 0; cursor: pointer; }
.bar-label { flex: 0 0 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bar-track { flex: 1 1 auto; }
.bar-fill { height: 13px; background: var(--accent); border-radius: 3px; min-width: 2px; }
.bar-count { flex: 0 0 50px; color: #666; }
.stats-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; }
.elements-table { border-collapse: collapse; width: 100%; }
.elements-table th, .elements-table td { border: 1px solid #ddd; padding: 4px 8px; text-align: left; }
```

- [ ] **Step 3: 视图实现**

`frontend/views/elements_search.js`:
```javascript
import { getJSON, postJSON } from "/assets/api.js";
import { el, clear, empty, errorState, loading } from "/assets/ui.js";

// 屏A 检索 = 三栏工作台 + 搜索顶栏 + 列表⇄表格切换(spec §8)。
// 状态:selected = 已选要素 chip;mode = "list"|"table"。
let selected = [];
let mode = "list";

export async function render(view, params) {
  loading(view);
  let facets, titles;
  try {
    const [ov, lib] = await Promise.all([
      getJSON("/elements/overview?top_n=9999"),
      getJSON("/library/papers"),
    ]);
    facets = ov.facets;
    titles = Object.fromEntries((lib.papers || []).map((p) => [p.paper_id, p.title || ""]));
  } catch (err) {
    if (err.code === 503) return empty(view, "尚未构建要素索引 — 到「全库统计」页点一次「构建要素索引」。");
    return errorState(view, err.message, () => render(view, params));
  }

  clear(view);
  view.append(el("h2", { text: "要素检索" }));
  const searchBox = el("input", { class: "search", placeholder: "搜要素:球磨 / XRD / GCMC …(回车选第一个命中)" });
  const chipsRow = el("div");
  const layout = el("div", { class: "elements-layout" });
  const tree = el("div", { class: "facet-tree card-box" });
  const results = el("div", { class: "elements-results" });
  const detail = el("div", { class: "elements-detail card-box" });
  layout.append(tree, results, detail);
  view.append(searchBox, chipsRow, layout);
  empty(detail, "点结果里的论文,看命中要素的逐字原文。");

  await drawTree();
  drawChips();
  await runQuery();

  searchBox.addEventListener("keydown", async (e) => {
    if (e.key !== "Enter" || !searchBox.value.trim()) return;
    try {
      const hits = (await getJSON(`/elements?q=${encodeURIComponent(searchBox.value.trim())}`)).elements;
      if (hits.length) { toggle(hits[0]); searchBox.value = ""; }
    } catch (err) { errorState(detail, err.message); }
  });

  function toggle(elem) {
    const i = selected.findIndex((s) => s.id === elem.id);
    if (i >= 0) selected.splice(i, 1);
    else selected.push({ id: elem.id, facet: elem.facet, slug: elem.slug, name: elem.display_name });
    drawChips(); drawTree(); runQuery();
  }

  function drawChips() {
    clear(chipsRow);
    for (const s of selected) {
      const chip = el("span", { class: "chip" }, [s.name, el("span", { class: "x", text: "×" })]);
      chip.addEventListener("click", () => toggle(s));
      chipsRow.append(chip);
    }
    const toggleBtn = el("button", { text: mode === "list" ? "表格模式" : "列表模式" });
    toggleBtn.addEventListener("click", () => { mode = mode === "list" ? "table" : "list"; runQuery(); });
    if (selected.length) chipsRow.append(toggleBtn);
  }

  async function drawTree() {
    clear(tree);
    for (const f of facets) {
      tree.append(el("h4", { text: `${f.id}(${f.total_elements})` }));
      for (const item of f.top) {
        const on = selected.some((s) => s.id === item.id);
        const label = el("label", { text: `${on ? "☑" : "☐"} ${item.display_name} (${item.papers})` });
        label.addEventListener("click", () => toggle({ ...item, facet: f.id, slug: item.slug || item.id.split("/")[1] }));
        tree.append(label);
      }
    }
  }

  async function runQuery() {
    if (!selected.length) return empty(results, "从左栏勾选要素,或在上方搜索 — 命中论文会列在这里。");
    loading(results);
    let data;
    try {
      data = await postJSON("/elements/query", { element_ids: selected.map((s) => s.id) });
    } catch (err) { return errorState(results, err.message, runQuery); }
    clear(results);
    results.append(el("p", { class: "muted", text: `命中 ${data.papers.length} 篇(AND 组合)` }));
    if (mode === "table") return drawTable(data);
    for (const p of data.papers) {
      const row = el("div", { class: "paper-row" }, [
        el("b", { text: p.paper_id }), " ", titles[p.paper_id] || "",
      ]);
      row.addEventListener("click", () => drawDetail(p));
      results.append(row);
    }
  }

  function drawTable(data) {
    const head = el("tr", {}, [el("th", { text: "论文" }), el("th", { text: "标题" }),
      ...selected.map((s) => el("th", { text: s.name }))]);
    const table = el("table", { class: "elements-table" }, [head]);
    for (const p of data.papers) {
      const cells = selected.map((s) => {
        const m = p.matches.find((x) => x.element_id === s.id);
        const valueText = m && m.values.length ? m.values.map((v) => v.raw).join(", ") : (m ? m.surface : "—");
        return el("td", { text: valueText });
      });
      const tr = el("tr", {}, [el("td", { text: p.paper_id }),
        el("td", { text: (titles[p.paper_id] || "").slice(0, 60) }), ...cells]);
      tr.addEventListener("click", () => drawDetail(p));
      table.append(tr);
    }
    const exportBtn = el("button", { text: "导出 CSV" });
    exportBtn.addEventListener("click", () => exportCSV(data));
    results.append(table, exportBtn);
  }

  function exportCSV(data) {
    const header = ["paper_id", "title", ...selected.map((s) => s.name)];
    const lines = [header.join(",")];
    for (const p of data.papers) {
      const cells = selected.map((s) => {
        const m = p.matches.find((x) => x.element_id === s.id);
        const t = m && m.values.length ? m.values.map((v) => v.raw).join("; ") : (m ? m.surface : "");
        return '"' + t.replaceAll('"', '""') + '"';
      });
      lines.push([p.paper_id, '"' + (titles[p.paper_id] || "").replaceAll('"', '""') + '"', ...cells].join(","));
    }
    const blob = new Blob(["﻿" + lines.join("\n")], { type: "text/csv" });
    const a = el("a", { href: URL.createObjectURL(blob), download: "elements_query.csv" });
    a.click();
  }

  function drawDetail(p) {
    clear(detail);
    detail.append(el("h3", { text: `${p.paper_id} 命中要素` }));
    for (const m of p.matches) {
      detail.append(
        el("div", {}, [el("span", { class: "tag", text: m.display_name }), ` ${m.surface}`]),
        el("div", { class: "quote-box", text: `“${m.quote}”` }),
        el("a", { href: `#/papers/${p.paper_id}/decompose`, text: `原文段 ${m.reading_block_id} ↗` }),
      );
    }
  }
}
```

- [ ] **Step 4: 后端起服务人工冒烟**

Run(仓库根): `python _serve_fixed.py`(desktop venv 环境;或 `desktop_app\.venv\Scripts\python _serve_fixed.py`)
浏览器开 `http://127.0.0.1:8000/#/elements`。
Expected: 无索引时显示「尚未构建要素索引…」的友好提示(不是报错栈);nav 出现「要素检索/全库统计」两项。Ctrl+C 停服务。

- [ ] **Step 5: 全量回归(确认 JS 改动没碰后端)**

Run(`desktop_app\`): `.venv\Scripts\python -m pytest -q` → 全绿

- [ ] **Step 6: Commit**

```powershell
git add desktop_app/frontend/views/elements_search.js desktop_app/frontend/app.js desktop_app/frontend/index.html desktop_app/frontend/styles.css
git commit -m "feat(frontend): elements search screen (3-pane workbench, chips, list/table toggle, CSV export)"
```

---

### Task 13: 前端屏B 统计 `views/elements_stats.js`

**Files:**
- Create: `desktop_app/frontend/views/elements_stats.js`
(路由/导航/样式已在 Task 12 加好)

- [ ] **Step 1: 视图实现**

`frontend/views/elements_stats.js`:
```javascript
import { getJSON, postJSON } from "/assets/api.js";
import { el, clear, empty, errorState, loading } from "/assets/ui.js";

// 屏B 统计 = 分层:总览仪表盘 -> 单 facet 大图 -> 抽屉(论文+引文+共现)。
// 路由: #/stats(总览) #/stats/<facet>(大图)。role 开关控制是否含 mentioned。
let includeMentioned = false;

export async function render(view, params) {
  if (params.length >= 1) return renderFacet(view, params[0]);
  return renderOverview(view);
}

function roleParam() { return includeMentioned ? "&role=all" : "&role=used"; }

async function renderOverview(view) {
  loading(view);
  let ov;
  try {
    ov = await getJSON(`/elements/overview?top_n=5${roleParam()}`);
  } catch (err) {
    if (err.code === 503) return renderBuildOffer(view);
    return errorState(view, err.message, () => renderOverview(view));
  }
  clear(view);
  view.append(el("h2", { text: `全库统计(${ov.library_papers} 篇有要素)` }), roleToggle(() => renderOverview(view)));
  const grid = el("div", { class: "stats-grid" });
  for (const f of ov.facets) {
    const box = el("div", { class: "card-box" });
    box.append(el("h3", { text: `${f.id}(${f.total_elements} 项)` }));
    const max = f.top.length ? f.top[0].papers : 1;
    for (const item of f.top) box.append(bar(item, max, () => location.hash = `#/stats/${f.id}`));
    const more = el("a", { href: `#/stats/${f.id}`, text: "看全部 →" });
    box.append(more);
    grid.append(box);
  }
  view.append(grid);
}

async function renderFacet(view, facet) {
  loading(view);
  let stats;
  try {
    stats = await getJSON(`/elements/stats?facet=${encodeURIComponent(facet)}${roleParam()}`);
  } catch (err) {
    if (err.code === 503) return renderBuildOffer(view);
    return errorState(view, err.message, () => renderFacet(view, facet));
  }
  clear(view);
  view.append(
    el("p", {}, [el("a", { href: "#/stats", text: "← 总览" })]),
    el("h2", { text: `${facet} 分布(${stats.items.length} 项)` }),
    roleToggle(() => renderFacet(view, facet)),
  );
  const layout = el("div", { class: "elements-layout" });
  const chart = el("div", { class: "elements-results" });
  const drawer = el("div", { class: "elements-detail card-box" });
  empty(drawer, "点左边任何一条,看论文、原文和「配套要素」。");
  layout.append(chart, drawer);
  view.append(layout);
  const max = stats.items.length ? stats.items[0].papers : 1;
  for (const item of stats.items) {
    chart.append(bar(item, max, () => drawDrawer(drawer, facet, item)));
  }
}

async function drawDrawer(drawer, facet, item) {
  loading(drawer);
  const slug = item.slug || item.id.split("/")[1];
  let detail, co, titles = {};
  try {
    [detail, co] = await Promise.all([
      getJSON(`/elements/${facet}/${slug}`),
      getJSON(`/elements/${facet}/${slug}/cooccurrence`),
    ]);
    const lib = await getJSON("/library/papers");
    titles = Object.fromEntries((lib.papers || []).map((p) => [p.paper_id, p.title || ""]));
  } catch (err) { return errorState(drawer, err.message); }
  clear(drawer);
  drawer.append(el("h3", { text: `${detail.display_name}(${detail.paper_count} 篇)` }));
  if (detail.aliases.length) drawer.append(el("p", { class: "muted", text: "同义词:" + detail.aliases.join(" / ") }));

  drawer.append(el("h4", { text: `配套要素(这 ${co.m} 篇里还出现)` }));
  for (const g of co.groups) {
    drawer.append(el("p", { class: "muted", text: g.facet }));
    for (const x of g.items.slice(0, 5)) {
      drawer.append(el("div", { class: "bar-row" }, [
        el("span", { class: "bar-label", text: x.display_name }),
        el("span", { class: "bar-count", text: `${x.n}/${co.m}` }),
      ]));
    }
  }

  drawer.append(el("h4", { text: "论文与原文" }));
  for (const p of detail.papers) {
    drawer.append(el("div", { class: "paper-row" }, [
      el("b", { text: p.paper_id }), " ", (titles[p.paper_id] || "").slice(0, 50),
    ]));
    for (const q of p.quotes) {
      drawer.append(
        el("div", { class: "quote-box", text: `“${q.quote}”` }),
        el("a", { href: `#/papers/${p.paper_id}/decompose`, text: `原文段 ${q.reading_block_id} ↗` }),
      );
    }
  }
}

function bar(item, max, onClick) {
  const row = el("div", { class: "bar-row" }, [
    el("span", { class: "bar-label", text: item.display_name }),
    el("span", { class: "bar-track" }, [
      el("span", { class: "bar-fill", style: `display:block;width:${Math.max(2, Math.round(100 * item.papers / max))}%` }),
    ]),
    el("span", { class: "bar-count", text: String(item.papers) }),
  ]);
  row.addEventListener("click", onClick);
  return row;
}

function roleToggle(redraw) {
  const label = el("label", {}, [
    Object.assign(el("input", { type: "checkbox" }), { checked: includeMentioned }),
    " 包含 mentioned(综述等仅提及)",
  ]);
  label.querySelector("input").addEventListener("change", (e) => {
    includeMentioned = e.target.checked; redraw();
  });
  return label;
}

function renderBuildOffer(view) {
  clear(view);
  view.append(
    el("h2", { text: "全库统计" }),
    el("p", { text: "还没有要素索引。点下面按钮做一次全库构建(后台运行,需要 AI,约数小时;费用约几十元)。" }),
  );
  const btn = el("button", { text: "构建要素索引(全库)" });
  const log = el("pre", { class: "muted" });
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    try {
      const { job_id } = await postJSON("/elements/bootstrap", {});
      const timer = setInterval(async () => {
        const s = await getJSON(`/jobs/${job_id}`);
        log.textContent = s.progress.slice(-8).join("\n");
        if (s.status !== "running") {
          clearInterval(timer);
          if (s.status === "succeeded") renderOverview(view);
          else errorState(view, "构建失败:" + s.error, () => renderBuildOffer(view));
        }
      }, 2000);
    } catch (err) { errorState(view, err.message, () => renderBuildOffer(view)); }
  });
  view.append(btn, log);
}
```

- [ ] **Step 2: 人工冒烟**

Run(仓库根): `desktop_app\.venv\Scripts\python _serve_fixed.py`,浏览器开 `http://127.0.0.1:8000/#/stats`。
Expected: 无索引 → 显示「构建要素索引」按钮与说明(真实构建是付费长任务,**此处不点**;真库构建见文末运营清单)。Ctrl+C 停服务。

- [ ] **Step 3: 全量回归**

Run(`desktop_app\`): `.venv\Scripts\python -m pytest -q` → 全绿

- [ ] **Step 4: Commit**

```powershell
git add desktop_app/frontend/views/elements_stats.js
git commit -m "feat(frontend): library stats screen (overview dashboard -> facet chart -> drawer with cooccurrence)"
```

---

### Task 14: 文档同步 + 终验

**Files:**
- Modify: `Document_Decomposer/scripts/README.md`(新增 elements/ 小节)
- Modify: `desktop_app/README.md`(API 表 + 状态行)
- Modify: `Document_Decomposer/HANDOFF.md`(一行指针)

- [ ] **Step 1: scripts/README.md 在 `## audit/` 小节前插入**

```markdown
## elements/ —— 研究要素索引(SP1;设计见 docs/superpowers/specs/2026-06-09-element-index-design.md)
- `ai_extract_elements.py` — AI 抽取每篇用过的 方法/表征/模拟/分析/材料/条件 要素;逐字引文双档核真(存在性+数字保真),核不过即丢。
- `bootstrap_element_registry.py` — 一次性引导:全库 surface 归并 → `data/elements/registry.json` + SQLite 索引;防大杂烩桶(I12 纪律)。
- `build_elements_index.py` — 从 elements.json + registry 重建 `data/elements/elements_index.sqlite`(随时可重建)。
- `audit_element_buckets.py` — 列出别名数超限的条目(疑似过度合并,人工复查)。
```

- [ ] **Step 2: desktop README API 表追加一行**

在 API 表 `| Writing |` 行后加:
```markdown
| Elements | `GET /elements/overview`, `GET /elements/stats`, `GET /elements`, `GET /elements/{facet}/{slug}` (+`/cooccurrence`), `POST /elements/query`, `PUT /elements/{facet}/{slug}`, `POST /elements/bootstrap`, `GET /elements/coverage`, `GET /papers/{id}/elements` |
```
并在 Status 段末尾追加一句(写实,不夸大):
```markdown
Element-index layer (SP1+SP2) implemented with offline tests; the real-library
bootstrap run + 20-paper sampling audit have NOT been executed yet (see
docs/superpowers/specs/2026-06-09-element-index-design.md §9).
```

- [ ] **Step 3: HANDOFF.md「主要文件」段末尾加一行**

```markdown
研究要素索引(要素抽取/注册表/SQLite 索引,SP1):`src/docdecomp/element_*.py` + `scripts/elements/`,
桌面两屏(要素检索/全库统计)在 desktop_app;设计与状态见 `docs/superpowers/specs/2026-06-09-element-index-design.md`。
```

- [ ] **Step 4: 终验(两侧全量)**

Run(`Document_Decomposer\`): `..\desktop_app\.venv\Scripts\python -m pytest tests -q` → 引擎全部通过
Run(`desktop_app\`): `.venv\Scripts\python -m pytest -q` → 119 + 新增全部通过

- [ ] **Step 5: Commit**

```powershell
git add Document_Decomposer/scripts/README.md desktop_app/README.md Document_Decomposer/HANDOFF.md
git commit -m "docs: register element-index layer (engine scripts map, desktop API table, handoff pointer)"
```

---

## 有意延后(本计划不做,记录在案防止误当遗漏)

- **展示名随使用频次自动切换**:引导期归并规则已要求 canonical 取最常用全称,覆盖主要场景;后续漂移用 PUT 改名(human,永久)兜底。
- **语义向量(embedding)匹配/检索层**:spec 预留;matching 的「AI 对照候选判定」即未来插槽,注册表大了再加。
- **「重试待补」无独立按钮**:再点一次「构建要素索引」即增量补漏(registry 已存在时只抽缺+流式匹配,绝不重新归并——见 service.run_bootstrap docstring 与对应测试)。

## 运营清单(代码完成后,由用户决定执行;不属于本计划的自动步骤)

1. **真库引导**(付费、数小时;约 261 篇 × ~¥0.2 + 归并调用):桌面「全库统计」页点「构建要素索引」,或 CLI:
   先 `python scripts\elements\ai_extract_elements.py --config config\ai.local.json`,
   再 `python scripts\elements\bootstrap_element_registry.py --config config\ai.local.json`。
2. **超大桶审计**:`python scripts\elements\audit_element_buckets.py`;flag>0 时人工看一遍,误并的用 PUT 接口拆(改名/合并)。
3. **抽样质量审计(spec §9,做完才许写"已验证")**:抽 20 篇人工对照方法章节,统计漏报/误报,登记进 `ISSUES.md` 新条目(含证据+方法+范围)。
4. 合并分支:用户 review `feature/element-index` 后决定。
