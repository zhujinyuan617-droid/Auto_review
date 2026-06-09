# Frontend Batch 2 — Remaining Screens (Import / Settings / Network / Writing) + config wire — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Build the remaining live/config-ready screens (Import, Settings, Network, Writing[check+angles]) as view modules registered in the router, plus a ~10-line backend wire that points the app at the existing connection artifacts so Network and Writing-angles show real data.

**Architecture:** Same no-build static SPA as Batch 1. Each screen is a `views/*.js` module exporting `render(view, params)`, registered in `app.js`'s `ROUTES`. A new `with_connection_paths()` helper in `main.py` sets `config.edges_path` / `config.concept_index_path` to `Document_Decomposer/reports/connection/{edges,concept_index}.json` at launch. The 🔴 screens (Groups, live search, draft generation) are NOT in this batch — Import shows search as "未接通", Writing shows draft as "未接通".

**Tech Stack:** Browser-native ES Modules; FastAPI; pytest for the backend wire.

**Repo rule on commits:** Commit ONLY when the user says "提交". `git commit` steps are checkpoints; stage the listed files and hold unless authorized.

**Endpoint contracts consumed (already implemented + tested):**
- `POST /papers/import {pdf_path}` → `{job_id}`; `GET /jobs/{id}` → `{status: "running"|"succeeded"|"failed", progress: [str], result: <paper_id>, error: str|null}`
- `POST /discovery/import-ris {text}` → `{records: [{title, doi, year, journal, authors[], pdf_url}]}`
- `POST /discovery/search {query}` → 503 (not configured this batch)
- `POST /writing/check {draft}` → `{citation: {passed: bool, ...}, style: {warnings: [str], ...}}`
- `GET /writing/angles` → `{tension: [edge-like], gaps: [{concept, ...}], synthesis: [edge-like]}` (empty dict-of-lists if unconfigured)
- `GET /writing/draft` is POST-only and 503 this batch.
- `GET /settings/apikey` → `{configured: bool}`; `POST {api_key}` → `{configured: bool}` (400 if blank); `DELETE` → `{configured: false}`; `GET /settings/setup-manifest` → `{consent_required, will_install: [{name, purpose}], optional_later, note}`
- `GET /network` → `{edges: [{a, b, relation, direction, shared, candidate_score, rationale, model}], relation_counts: {<relation>: int}, n_edges}` (empty graph if `edges_path` unset)

---

## File structure (this batch)

```
desktop_app/
  src/autoreview_app/main.py        # MODIFY: with_connection_paths() + use it in main()
  frontend/app.js                   # MODIFY: register import/network/writing/settings routes
  frontend/api.js                   # MODIFY: add delJSON for the settings DELETE
  frontend/views/import.js          # CREATE
  frontend/views/settings.js        # CREATE
  frontend/views/network.js         # CREATE
  frontend/views/writing.js         # CREATE
  tests/test_config_connection.py   # CREATE: with_connection_paths() unit test
  tests/test_static_assets.py       # MODIFY: assert the 4 new view modules serve
```

---

## Task 1: Backend wire — point config at the connection artifacts

**Files:**
- Modify: `desktop_app/src/autoreview_app/main.py`
- Test: `desktop_app/tests/test_config_connection.py`

- [ ] **Step 1: Write the failing test**

Create `desktop_app/tests/test_config_connection.py`:

```python
from pathlib import Path

from autoreview_app.config import AppConfig
from autoreview_app.main import with_connection_paths


def test_sets_paths_when_files_exist(tmp_path: Path):
    conn = tmp_path / "connection"
    conn.mkdir()
    (conn / "edges.json").write_text("{}", encoding="utf-8")
    (conn / "concept_index.json").write_text("{}", encoding="utf-8")
    cfg = with_connection_paths(AppConfig(library_dir=tmp_path / "library"), conn)
    assert cfg.edges_path == conn / "edges.json"
    assert cfg.concept_index_path == conn / "concept_index.json"


def test_leaves_paths_none_when_files_missing(tmp_path: Path):
    conn = tmp_path / "connection"  # does not exist
    cfg = with_connection_paths(AppConfig(library_dir=tmp_path / "library"), conn)
    assert cfg.edges_path is None
    assert cfg.concept_index_path is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `desktop_app\.venv\Scripts\python.exe -m pytest desktop_app/tests/test_config_connection.py -v`
Expected: FAIL — `ImportError: cannot import name 'with_connection_paths'`.

- [ ] **Step 3: Implement the helper and use it in main()**

In `desktop_app/src/autoreview_app/main.py`, add imports at the top (after `import threading`):

```python
import dataclasses
from pathlib import Path
```

Add this function above `main()`:

```python
def with_connection_paths(config: AppConfig, connection_dir: Path) -> AppConfig:
    """Point the config at the engine's connection artifacts when they exist.

    The connection layer's edges.json / concept_index.json live in the engine's
    reports dir, not beside the library. Wiring them here lets the network and
    writing-angles screens show real data without changing the engine.
    """
    edges = connection_dir / "edges.json"
    cidx = connection_dir / "concept_index.json"
    return dataclasses.replace(
        config,
        edges_path=edges if edges.is_file() else config.edges_path,
        concept_index_path=cidx if cidx.is_file() else config.concept_index_path,
    )
```

Then change the first line of `main()` from:

```python
    config = AppConfig.from_env()
```

to:

```python
    connection_dir = Path(__file__).resolve().parents[3] / "Document_Decomposer" / "reports" / "connection"
    config = with_connection_paths(AppConfig.from_env(), connection_dir)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `desktop_app\.venv\Scripts\python.exe -m pytest desktop_app/tests/test_config_connection.py -v`
Expected: PASS (both).

- [ ] **Step 5: Full suite**

Run: `desktop_app\.venv\Scripts\python.exe -m pytest desktop_app -q`
Expected: 125 passed (123 + 2), 1 warning.

- [ ] **Step 6: Commit (per repo rule)**

```bash
git add desktop_app/src/autoreview_app/main.py desktop_app/tests/test_config_connection.py
git commit -m "feat(frontend): wire config to connection artifacts for network/angles"
```

---

## Task 2: `delJSON` helper + register routes

**Files:**
- Modify: `desktop_app/frontend/api.js`
- Modify: `desktop_app/frontend/app.js`

- [ ] **Step 1: Add `delJSON` to api.js**

Append to `desktop_app/frontend/api.js`:

```javascript
export async function delJSON(path) {
  const res = await fetch(path, { method: "DELETE" });
  if (!res.ok) {
    const err = new Error("HTTP " + res.status);
    err.code = res.status;
    throw err;
  }
  return res.json();
}
```

- [ ] **Step 2: Register the four new routes in app.js**

In `desktop_app/frontend/app.js`, replace the `ROUTES` object:

```javascript
const ROUTES = {
  papers: () => import("/assets/views/papers.js"),
};
```

with:

```javascript
const ROUTES = {
  papers: () => import("/assets/views/papers.js"),
  import: () => import("/assets/views/import.js"),
  network: () => import("/assets/views/network.js"),
  writing: () => import("/assets/views/writing.js"),
  settings: () => import("/assets/views/settings.js"),
};
```

(`groups` is intentionally left out — it stays a "(开发中)" placeholder until Batch 3.)

- [ ] **Step 3: Verify static still serves + suite green**

Run: `desktop_app\.venv\Scripts\python.exe -m pytest desktop_app/tests/test_static_assets.py desktop_app/tests/test_api.py -q`
Expected: PASS. (No new view files yet — the dynamic imports only evaluate at runtime when a route is hit; tests don't hit them.)

- [ ] **Step 4: Commit (per repo rule)**

```bash
git add desktop_app/frontend/api.js desktop_app/frontend/app.js
git commit -m "feat(frontend): delJSON helper + register import/network/writing/settings routes"
```

---

## Task 3: Settings screen

**Files:**
- Create: `desktop_app/frontend/views/settings.js`
- Modify: `desktop_app/tests/test_static_assets.py`

- [ ] **Step 1: Create settings.js**

Create `desktop_app/frontend/views/settings.js`:

```javascript
import { getJSON, postJSON, delJSON } from "/assets/api.js";
import { el, clear, loading, errorState } from "/assets/ui.js";

export async function render(view) {
  loading(view);
  let state;
  let manifest;
  try {
    state = await getJSON("/settings/apikey");
    manifest = await getJSON("/settings/setup-manifest");
  } catch (err) {
    return errorState(view, err.message, () => render(view));
  }
  clear(view);
  view.append(el("h2", { text: "设置" }));
  view.append(apiKeySection(view, state.configured));
  view.append(manifestSection(manifest));
}

function apiKeySection(view, configured) {
  const box = el("div", { class: "card-box section" }, [el("h3", { text: "API Key" })]);
  const status = el("p", { class: "muted", text: configured ? "已配置(已存入系统钥匙串)" : "未配置" });
  box.append(status);
  box.append(el("p", { class: "muted", text: "注意:当前引擎仍读 ai.local.json,此处的 key 暂未接到引擎(ISSUES 待接线)。" }));

  const input = el("input", { class: "search", type: "password", placeholder: "粘贴 DeepSeek API key…" });
  const saveBtn = el("button", { text: "保存" });
  saveBtn.addEventListener("click", async () => {
    const key = input.value.trim();
    if (!key) { status.textContent = "key 不能为空"; return; }
    try {
      await postJSON("/settings/apikey", { api_key: key });
      input.value = "";
      render(view);  // re-render to reflect configured state
    } catch (err) {
      status.className = "error";
      status.textContent = err.code === 400 ? "key 无效(空白)" : "保存失败:" + err.message;
    }
  });

  const delBtn = el("button", { text: "删除" });
  delBtn.addEventListener("click", async () => {
    try {
      await delJSON("/settings/apikey");
      render(view);
    } catch (err) {
      status.className = "error";
      status.textContent = "删除失败:" + err.message;
    }
  });

  box.append(el("div", { class: "section" }, [input]), saveBtn, " ", delBtn);
  return box;
}

function manifestSection(manifest) {
  const box = el("div", { class: "card-box section" }, [el("h3", { text: "安装清单" })]);
  const items = manifest.will_install || [];
  const ul = el("ul");
  for (const it of items) ul.append(el("li", { text: `${it.name} —— ${it.purpose}` }));
  box.append(ul);
  if (manifest.optional_later) box.append(el("p", { class: "muted", text: manifest.optional_later }));
  if (manifest.note) box.append(el("p", { class: "muted", text: manifest.note }));
  return box;
}
```

- [ ] **Step 2: Asset test**

Append to `desktop_app/tests/test_static_assets.py`:

```python
def test_settings_view_served(tmp_path: Path):
    response = _client(tmp_path).get("/assets/views/settings.js")
    assert response.status_code == 200
    assert "apiKeySection" in response.text
```

- [ ] **Step 3: Run tests**

Run: `desktop_app\.venv\Scripts\python.exe -m pytest desktop_app/tests/test_static_assets.py desktop_app/tests/test_api_settings.py -q`
Expected: PASS.

- [ ] **Step 4: Commit (per repo rule)**

```bash
git add desktop_app/frontend/views/settings.js desktop_app/tests/test_static_assets.py
git commit -m "feat(frontend): settings screen (api key + install manifest)"
```

---

## Task 4: Network screen

**Files:**
- Create: `desktop_app/frontend/views/network.js`
- Modify: `desktop_app/tests/test_static_assets.py`

- [ ] **Step 1: Create network.js**

Create `desktop_app/frontend/views/network.js`:

```javascript
import { getJSON } from "/assets/api.js";
import { el, clear, loading, empty, errorState } from "/assets/ui.js";

export async function render(view) {
  loading(view);
  let data;
  try {
    data = await getJSON("/network");
  } catch (err) {
    return errorState(view, err.message, () => render(view));
  }
  const edges = data.edges || [];
  clear(view);
  view.append(el("h2", { text: `关系网 (${data.n_edges || edges.length} 条边)` }));

  if (edges.length === 0) {
    return empty(view, "关系数据未配置 —— 启动时未找到 edges.json(见设计文档配置接线)。");
  }

  const counts = data.relation_counts || {};
  const types = Object.keys(counts);
  const summary = el("p", { class: "muted", text: types.map((t) => `${t}:${counts[t]}`).join("  ·  ") });
  view.append(summary);

  const select = el("select", { class: "search" });
  select.append(el("option", { value: "" }, "全部关系"));
  for (const t of types) select.append(el("option", { value: t }, t));

  const list = el("div", { class: "paper-list" });
  function draw(filter) {
    clear(list);
    const rows = edges.filter((e) => !filter || e.relation === filter);
    if (rows.length === 0) { list.append(el("p", { class: "muted", text: "无匹配" })); return; }
    for (const e of rows.slice(0, 500)) {
      list.append(
        el("div", { class: "atom" }, [
          el("div", {}, [
            el("a", { href: "#/papers/" + e.a }, e.a), " — ",
            el("strong", { text: e.relation || "?" }), " — ",
            el("a", { href: "#/papers/" + e.b }, e.b),
          ]),
          e.rationale ? el("div", { class: "quote", text: e.rationale }) : null,
        ])
      );
    }
    if (rows.length > 500) list.append(el("p", { class: "muted", text: `仅显示前 500 / 共 ${rows.length} 条` }));
  }
  select.addEventListener("change", () => draw(select.value));
  view.append(select, list);
  draw("");
}
```

- [ ] **Step 2: Asset test**

Append to `desktop_app/tests/test_static_assets.py`:

```python
def test_network_view_served(tmp_path: Path):
    response = _client(tmp_path).get("/assets/views/network.js")
    assert response.status_code == 200
    assert "关系网" in response.text
```

- [ ] **Step 3: Run tests**

Run: `desktop_app\.venv\Scripts\python.exe -m pytest desktop_app/tests/test_static_assets.py desktop_app/tests/test_edges.py -q`
Expected: PASS.

- [ ] **Step 4: Commit (per repo rule)**

```bash
git add desktop_app/frontend/views/network.js desktop_app/tests/test_static_assets.py
git commit -m "feat(frontend): network screen (edge list + relation filter)"
```

---

## Task 5: Writing screen (mechanical check + candidate angles)

**Files:**
- Create: `desktop_app/frontend/views/writing.js`
- Modify: `desktop_app/tests/test_static_assets.py`

- [ ] **Step 1: Create writing.js**

Create `desktop_app/frontend/views/writing.js`:

```javascript
import { getJSON, postJSON } from "/assets/api.js";
import { el, clear, loading, errorState } from "/assets/ui.js";

export async function render(view) {
  clear(view);
  view.append(el("h2", { text: "写作" }));
  view.append(checkSection());
  const angles = el("div", { class: "section" }, [el("h3", { text: "候选角度" }), el("p", { class: "muted", text: "加载中…" })]);
  view.append(angles);
  loadAngles(angles);
  view.append(draftSection());
}

function checkSection() {
  const box = el("div", { class: "card-box section" }, [el("h3", { text: "草稿机械闸(引用 + 风格)" })]);
  const ta = el("textarea", { class: "search", rows: "5", placeholder: "粘贴草稿,检查引用格式和风格…" });
  const out = el("div", { class: "section" });
  const btn = el("button", { text: "检查" });
  btn.addEventListener("click", async () => {
    clear(out);
    try {
      const r = await postJSON("/writing/check", { draft: ta.value });
      const passed = r.citation && r.citation.passed;
      out.append(el("p", { class: passed ? "muted" : "error", text: "引用闸:" + (passed ? "通过" : "未通过") }));
      const warnings = (r.style && r.style.warnings) || [];
      if (warnings.length === 0) {
        out.append(el("p", { class: "muted", text: "风格:无告警" }));
      } else {
        const ul = el("ul");
        for (const w of warnings) ul.append(el("li", { text: typeof w === "string" ? w : JSON.stringify(w) }));
        out.append(el("p", { text: "风格告警:" }), ul);
      }
    } catch (err) { errorState(out, err.message, null); }
  });
  box.append(ta, btn, out);
  return box;
}

async function loadAngles(container) {
  let a;
  try { a = await getJSON("/writing/angles"); }
  catch (err) { return errorState(container, err.message, () => loadAngles(container)); }
  clear(container);
  container.append(el("h3", { text: "候选角度" }));
  const tension = a.tension || [];
  const gaps = a.gaps || [];
  const synthesis = a.synthesis || [];
  if (tension.length + gaps.length + synthesis.length === 0) {
    container.append(el("p", { class: "muted", text: "无候选 —— 关系/概念数据未配置或为空。" }));
    return;
  }
  container.append(angleGroup("张力(可能的矛盾)", tension, (t) => `${t.a || ""} ↔ ${t.b || ""} : ${t.rationale || t.relation || ""}`));
  container.append(angleGroup("空白(概念覆盖薄)", gaps, (g) => `${g.concept || ""}(gap ${g.gap_score != null ? g.gap_score : "?"})`));
  container.append(angleGroup("综合(可整合)", synthesis, (s) => `${s.a || ""} + ${s.b || ""} : ${s.rationale || s.relation || ""}`));
}

function angleGroup(title, items, fmt) {
  const sec = el("div", { class: "section" }, [el("h3", { text: `${title} (${items.length})` })]);
  if (items.length === 0) { sec.append(el("p", { class: "muted", text: "无" })); return sec; }
  for (const it of items.slice(0, 50)) sec.append(el("div", { class: "atom", text: fmt(it) }));
  return sec;
}

function draftSection() {
  const box = el("div", { class: "card-box section" }, [el("h3", { text: "出稿" })]);
  box.append(el("p", { class: "muted", text: "未接通 —— 出稿需真实写作 brief + AI 客户端(Batch 3)。" }));
  return box;
}
```

- [ ] **Step 2: Asset test**

Append to `desktop_app/tests/test_static_assets.py`:

```python
def test_writing_view_served(tmp_path: Path):
    response = _client(tmp_path).get("/assets/views/writing.js")
    assert response.status_code == 200
    assert "checkSection" in response.text
```

- [ ] **Step 3: Run tests**

Run: `desktop_app\.venv\Scripts\python.exe -m pytest desktop_app/tests/test_static_assets.py desktop_app/tests/test_api_writing_check.py desktop_app/tests/test_api_angles.py -q`
Expected: PASS.

- [ ] **Step 4: Commit (per repo rule)**

```bash
git add desktop_app/frontend/views/writing.js desktop_app/tests/test_static_assets.py
git commit -m "feat(frontend): writing screen (mechanical check + candidate angles)"
```

---

## Task 6: Import screen

**Files:**
- Create: `desktop_app/frontend/views/import.js`
- Modify: `desktop_app/tests/test_static_assets.py`

- [ ] **Step 1: Create import.js**

Create `desktop_app/frontend/views/import.js`:

```javascript
import { getJSON, postJSON } from "/assets/api.js";
import { el, clear, errorState } from "/assets/ui.js";

export async function render(view) {
  clear(view);
  view.append(el("h2", { text: "导入" }));
  view.append(pdfSection());
  view.append(risSection());
}

function sleep(ms) { return new Promise((resolve) => setTimeout(resolve, ms)); }

function pdfSection() {
  const box = el("div", { class: "card-box section" }, [el("h3", { text: "导入 PDF" })]);
  box.append(el("p", { class: "muted", text: "暂不支持中文 PDF —— 会导入失败(ISSUES I17)。" }));
  const input = el("input", { class: "search", placeholder: "PDF 完整路径,如 D:\\\\papers\\\\x.pdf" });
  const status = el("div", { class: "section" });
  const btn = el("button", { text: "开始导入" });
  btn.addEventListener("click", async () => {
    const path = input.value.trim();
    if (!path) { clear(status); status.append(el("p", { class: "error", text: "请先填 PDF 路径" })); return; }
    btn.disabled = true;
    clear(status);
    status.append(el("p", { class: "muted", text: "提交中…" }));
    try {
      const { job_id } = await postJSON("/papers/import", { pdf_path: path });
      await pollJob(job_id, status);
    } catch (err) {
      errorState(status, err.message, null);
    } finally {
      btn.disabled = false;
    }
  });
  box.append(input, btn, status);
  return box;
}

async function pollJob(jobId, status) {
  for (let i = 0; i < 600; i++) {
    const job = await getJSON("/jobs/" + jobId);
    clear(status);
    status.append(el("p", { class: "muted", text: (job.progress || []).join(" → ") || "运行中…" }));
    if (job.status === "succeeded") {
      status.append(el("p", {}, ["完成,论文号 ", el("strong", { text: String(job.result) }), " ",
        el("a", { href: "#/papers/" + job.result }, "查看")]));
      return;
    }
    if (job.status === "failed") {
      status.append(el("p", { class: "error", text: "失败:" + (job.error || "未知错误") }));
      return;
    }
    await sleep(1000);
  }
  status.append(el("p", { class: "error", text: "超时,仍在运行 —— 稍后到藏书查看。" }));
}

function risSection() {
  const box = el("div", { class: "card-box section" }, [el("h3", { text: "粘贴 RIS(取 DOI)" })]);
  const ta = el("textarea", { class: "search", rows: "6", placeholder: "粘贴 .ris 文本…" });
  const out = el("div", { class: "section" });
  const btn = el("button", { text: "解析" });
  btn.addEventListener("click", async () => {
    clear(out);
    try {
      const { records } = await postJSON("/discovery/import-ris", { text: ta.value });
      if (!records.length) { out.append(el("p", { class: "muted", text: "没解析到条目" })); return; }
      out.append(el("p", { class: "muted", text: `解析到 ${records.length} 条` }));
      for (const r of records) {
        out.append(el("div", { class: "atom" }, [
          el("div", { text: r.title || "(无标题)" }),
          el("div", { class: "quote", text: [r.year, r.journal, r.doi].filter(Boolean).join(" · ") }),
        ]));
      }
    } catch (err) { errorState(out, err.message, null); }
  });
  box.append(ta, btn, out);
  return box;
}
```

- [ ] **Step 2: Asset test**

Append to `desktop_app/tests/test_static_assets.py`:

```python
def test_import_view_served(tmp_path: Path):
    response = _client(tmp_path).get("/assets/views/import.js")
    assert response.status_code == 200
    assert "pollJob" in response.text
```

- [ ] **Step 3: Run tests + full suite**

Run: `desktop_app\.venv\Scripts\python.exe -m pytest desktop_app/tests/test_static_assets.py desktop_app/tests/test_api_discovery.py -q`
Then: `desktop_app\.venv\Scripts\python.exe -m pytest desktop_app -q`
Expected: all pass (≈130 passed), 1 warning.

- [ ] **Step 4: Commit (per repo rule)**

```bash
git add desktop_app/frontend/views/import.js desktop_app/tests/test_static_assets.py
git commit -m "feat(frontend): import screen (PDF job + RIS parse)"
```

---

## Task 7: Real-machine smoke (manual)

**Files:** none.

- [ ] **Step 1: Full suite green** — `desktop_app\.venv\Scripts\python.exe -m pytest desktop_app -q` (expect ≈130 passed, 1 warning).

- [ ] **Step 2: Launch** (PowerShell, repo root):

```powershell
$env:AUTOREVIEW_LIBRARY_DIR = (Resolve-Path .\Document_Decomposer\library).Path
.\desktop_app\.venv\Scripts\python -m autoreview_app.main
```

- [ ] **Step 3: Click through and confirm**
- 设置: shows "已配置" or "未配置"; the install manifest lists fastapi/uvicorn/pywebview/pymupdf/keyring.
- 关系网: shows "关系网 (N 条边)" with N>0 (the config wire found edges.json) + relation-type filter; rows link to papers.
- 写作: 草稿机械闸 — paste `Adsorption rises [S09].` → 引用闸 通过; paste `Adsorption rises S09.` → 未通过. 候选角度 shows tension/gaps/synthesis groups. 出稿 shows "未接通".
- 导入: RIS paste shows parsed records; PDF path of an English paper runs a job to done (optional — real AI call). 课题组 still "(开发中)".

- [ ] **Step 4: Record** — note any screen that fails to render; otherwise update `desktop_app/README.md` Status (show wording before writing per repo rule).

---

## Self-review checklist (plan author)

- **Spec coverage:** Import (PDF job + RIS) ✓; Settings (key get/set/delete + manifest) ✓; Network (edge list + filter + empty state) ✓; Writing (check + angles + draft-not-configured) ✓; config wire for network/angles ✓. Groups + live search + draft generation correctly deferred to Batch 3 (placeholders/未接通).
- **Placeholder scan:** No TBD/vague steps; every view has complete code.
- **Type/name consistency:** `getJSON/postJSON/delJSON` (api.js) used as added; `el/clear/loading/empty/errorState` (ui.js) match call sites; `render(view)` matches router contract; `with_connection_paths(config, connection_dir)` signature matches test and main() call. Field names match endpoints: job `{status,progress,result,error}`, check `{citation.passed, style.warnings}`, manifest `{will_install:[{name,purpose}], optional_later, note}`, edge `{a,b,relation,rationale}` + `relation_counts`, angles `{tension,gaps[].concept,synthesis}`, RIS record `{title,year,journal,doi}`.
- **Route registration:** import/network/writing/settings added to ROUTES (Task 2); groups left as placeholder by design.
```
