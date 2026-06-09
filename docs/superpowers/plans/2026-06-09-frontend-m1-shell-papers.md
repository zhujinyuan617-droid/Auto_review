# Frontend Batch 1 — Shell + Papers Screen — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the stub `frontend/index.html` with a no-build single-page app shell (hash router + per-screen view modules) and a fully working Papers screen (list → detail → decomposition) over the live engine library.

**Architecture:** FastAPI serves `frontend/` as static assets under `/assets`. `index.html` is the shell (header + left nav + `<main id="view">`). `app.js` is a hash router that dynamically imports a view module and calls its `render(container, params)`. `views/papers.js` is the first view; other nav links fall to an in-shell "(开发中)" placeholder until later batches register them.

**Tech Stack:** Python 3.12 / FastAPI / Starlette `StaticFiles`; browser-native ES Modules, no build step, no JS test framework. Backend changes use pytest in the existing `desktop_app/tests/` style.

**Repo rule on commits:** Per `Auto_review/CLAUDE.md`, commit ONLY when the user explicitly says "提交". The `git commit` steps below mark logical checkpoints — when executing, stage exactly the listed files; commit only if the user has authorized, otherwise hold the staged checkpoint and continue.

**TDD note:** The one backend change (static mount) gets a real failing-test-first cycle. The JS view modules have no unit-test framework (spec decision, YAGNI); their data contracts are already guarded by existing pytest (`test_api_browse.py`, `test_api_decomposition.py`), and their rendering is verified by the manual window smoke in the final task. Render functions are written as pure `data → DOM` so the risky logic stays inspectable.

---

## File structure (this batch)

```
desktop_app/
  src/autoreview_app/api.py        # MODIFY: mount StaticFiles at /assets
  frontend/
    index.html                     # REPLACE stub with the shell
    styles.css                     # CREATE: one light theme
    api.js                         # CREATE: fetch wrapper (getJSON/postJSON)
    ui.js                          # CREATE: el()/clear()/loading()/empty()/errorState()/placeholder()
    app.js                         # CREATE: hash router
    views/papers.js                # CREATE: list + detail + decomposition
  tests/test_static_assets.py      # CREATE: assert /assets/app.js is served
```

Endpoint contracts this batch consumes (already implemented + tested):
- `GET /library/papers` → `{papers: [{paper_id, has_card, title, year, journal, doi, paper_type, objective, research_objects[], methods[], domain_tags[], main_findings[]}]}`
- `GET /papers/{id}` → one such row (404 if unknown)
- `GET /papers/{id}/decomposition` → `{paper_id, card:{title,year,journal,objective,main_findings[]}, abstract_blocks:[{reading_block_id,text}], intro_blocks:[...], glossary:[...], analyses:[{evidence_atom_id,atom_type,minimal_claim,quote,reading_block_id,confidence}], results:[same], result_relations:[{synthesis_id,synthesis_type,claim,supporting_evidence_atom_ids[]}]}`

---

## Task 1: Serve frontend assets under `/assets`

**Files:**
- Modify: `desktop_app/src/autoreview_app/api.py`
- Test: `desktop_app/tests/test_static_assets.py`

- [ ] **Step 1: Write the failing test**

Create `desktop_app/tests/test_static_assets.py`:

```python
from pathlib import Path

from fastapi.testclient import TestClient

from autoreview_app.api import create_app
from autoreview_app.config import AppConfig


def _client(library_dir: Path) -> TestClient:
    return TestClient(create_app(AppConfig(library_dir=library_dir)))


def test_app_js_served(tmp_path: Path):
    # app.js lives in the real repo frontend dir, independent of library_dir.
    response = _client(tmp_path).get("/assets/app.js")
    assert response.status_code == 200
    assert "render" in response.text  # the router calls each view's render()


def test_styles_served(tmp_path: Path):
    response = _client(tmp_path).get("/assets/styles.css")
    assert response.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd desktop_app; .venv\Scripts\python -m pytest tests/test_static_assets.py -v`
Expected: FAIL — `/assets/app.js` returns 404 (no mount yet; files not created yet).

- [ ] **Step 3: Add the static mount**

In `desktop_app/src/autoreview_app/api.py`, add the import near the other FastAPI imports (after line 7, `from fastapi.responses import FileResponse`):

```python
from fastapi.staticfiles import StaticFiles
```

Then, inside `create_app`, immediately before the final `return app` (currently line 188), add:

```python
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR), name="assets")
```

(`FRONTEND_DIR` is already defined at module top: `Path(__file__).resolve().parents[2] / "frontend"`. Mounting at `/assets` does not shadow the API routes or `GET /`, which keep their explicit paths.)

- [ ] **Step 4: Create the asset files so the mount has something to serve**

This task only needs `app.js` and `styles.css` to exist for its test. Create minimal real stubs now; Tasks 2–5 fill them with the final content.

Create `desktop_app/frontend/styles.css`:

```css
/* filled in Task 2 */
```

Create `desktop_app/frontend/app.js`:

```javascript
// router + render() dispatch filled in Task 4
export function render() {}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd desktop_app; .venv\Scripts\python -m pytest tests/test_static_assets.py -v`
Expected: PASS (both tests).

- [ ] **Step 6: Run the full suite (no regressions)**

Run: `cd desktop_app; .venv\Scripts\python -m pytest -q`
Expected: previous count + 2 passed (was 119 → 121), 1 warning.

- [ ] **Step 7: Commit (per repo rule)**

```bash
git add desktop_app/src/autoreview_app/api.py desktop_app/tests/test_static_assets.py desktop_app/frontend/styles.css desktop_app/frontend/app.js
git commit -m "feat(frontend): serve frontend assets under /assets"
```

---

## Task 2: App shell (`index.html`) + theme (`styles.css`)

**Files:**
- Modify: `desktop_app/frontend/index.html`
- Modify: `desktop_app/frontend/styles.css`

- [ ] **Step 1: Replace `index.html` with the shell**

Overwrite `desktop_app/frontend/index.html`:

```html
<!doctype html>
<html lang="zh">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Auto Review</title>
    <link rel="stylesheet" href="/assets/styles.css" />
  </head>
  <body>
    <header id="topbar"><h1>Auto Review</h1></header>
    <div id="layout">
      <nav id="nav">
        <a href="#/papers">藏书</a>
        <a href="#/import">导入</a>
        <a href="#/network">关系网</a>
        <a href="#/groups">课题组</a>
        <a href="#/writing">写作</a>
        <a href="#/settings">设置</a>
      </nav>
      <main id="view">加载中…</main>
    </div>
    <script type="module" src="/assets/app.js"></script>
  </body>
</html>
```

- [ ] **Step 2: Fill `styles.css` with the theme**

Overwrite `desktop_app/frontend/styles.css`:

```css
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: "Segoe UI", "Microsoft YaHei", system-ui, sans-serif;
  color: #1f2328; background: #f6f7f8;
}
#topbar { background: #24292f; color: #fff; padding: 10px 16px; }
#topbar h1 { font-size: 16px; margin: 0; font-weight: 600; }
#layout { display: flex; min-height: calc(100vh - 40px); }
#nav { width: 120px; background: #fff; border-right: 1px solid #d0d7de; padding: 8px 0; }
#nav a {
  display: block; padding: 8px 16px; color: #1f2328; text-decoration: none; font-size: 14px;
}
#nav a:hover { background: #f0f3f6; }
#nav a.active { background: #ddf4ff; border-left: 3px solid #0969da; font-weight: 600; }
#view { flex: 1; padding: 16px 20px; overflow: auto; }
h2 { font-size: 18px; margin: 0 0 12px; }
.muted { color: #656d76; }
.error { color: #cf222e; }
.search { width: 100%; max-width: 360px; padding: 6px 8px; margin-bottom: 12px;
  border: 1px solid #d0d7de; border-radius: 6px; }
.paper-list { display: flex; flex-direction: column; gap: 2px; }
.paper-row { display: flex; flex-direction: column; padding: 8px 10px; border-radius: 6px;
  text-decoration: none; color: inherit; }
.paper-row:hover { background: #eef1f4; }
.ptitle { font-size: 14px; }
.pmeta { font-size: 12px; color: #656d76; }
.tag { display: inline-block; background: #eef1f4; border-radius: 10px;
  padding: 1px 8px; margin: 2px 4px 2px 0; font-size: 12px; }
.section { margin: 16px 0; }
.section h3 { font-size: 14px; margin: 0 0 6px; color: #0969da; }
.card-box { background: #fff; border: 1px solid #d0d7de; border-radius: 8px; padding: 12px 14px; }
.atom { border-left: 3px solid #d0d7de; padding: 4px 10px; margin: 6px 0; }
.atom .quote { color: #656d76; font-size: 13px; }
button { padding: 6px 12px; border: 1px solid #d0d7de; border-radius: 6px;
  background: #f6f8fa; cursor: pointer; }
button:hover { background: #eef1f4; }
a.back { font-size: 13px; color: #0969da; text-decoration: none; }
```

- [ ] **Step 3: Verify the page still serves**

Run: `cd desktop_app; .venv\Scripts\python -m pytest tests/test_api.py::test_index_html_served -v`
Note: the existing test asserts `"/library" in response.text`. The new shell no longer contains the string `/library` (the fetch moved into JS). Update that test in the next step.

- [ ] **Step 4: Update the now-stale index test**

In `desktop_app/tests/test_api.py`, replace `test_index_html_served` (lines 31-35) with:

```python
def test_index_html_served(tmp_path: Path):
    response = _client(tmp_path).get("/")
    assert response.status_code == 200
    assert "Auto Review" in response.text
    assert "/assets/app.js" in response.text  # shell loads the router module
```

- [ ] **Step 5: Run tests**

Run: `cd desktop_app; .venv\Scripts\python -m pytest tests/test_api.py -q`
Expected: PASS.

- [ ] **Step 6: Commit (per repo rule)**

```bash
git add desktop_app/frontend/index.html desktop_app/frontend/styles.css desktop_app/tests/test_api.py
git commit -m "feat(frontend): app shell + light theme"
```

---

## Task 3: Fetch wrapper (`api.js`) + DOM helpers (`ui.js`)

**Files:**
- Create: `desktop_app/frontend/api.js`
- Create: `desktop_app/frontend/ui.js`

- [ ] **Step 1: Create `api.js`**

Create `desktop_app/frontend/api.js`:

```javascript
// Thin fetch wrapper. Throws Error with .code = HTTP status; 503 is surfaced
// distinctly so views can render "未接通" instead of a generic error.
export async function getJSON(path) {
  const res = await fetch(path);
  if (!res.ok) {
    const err = new Error(res.status === 503 ? "not_configured" : "HTTP " + res.status);
    err.code = res.status;
    throw err;
  }
  return res.json();
}

export async function postJSON(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = new Error(res.status === 503 ? "not_configured" : "HTTP " + res.status);
    err.code = res.status;
    throw err;
  }
  return res.json();
}
```

- [ ] **Step 2: Create `ui.js`**

Create `desktop_app/frontend/ui.js`:

```javascript
// DOM helpers. el() builds a node; the state helpers give every view the same
// loading / empty / error treatment so a failure never leaves a blank panel.
export function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (v != null) node.setAttribute(k, v);
  }
  for (const child of [].concat(children)) {
    if (child == null) continue;
    node.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return node;
}

export function clear(node) { node.replaceChildren(); }

export function loading(node) {
  clear(node);
  node.append(el("p", { class: "muted", text: "加载中…" }));
}

export function empty(node, message) {
  clear(node);
  node.append(el("p", { class: "muted", text: message }));
}

export function errorState(node, message, onRetry) {
  clear(node);
  node.append(el("p", { class: "error", text: "出错:" + message }));
  if (onRetry) {
    const button = el("button", { text: "重试" });
    button.addEventListener("click", onRetry);
    node.append(button);
  }
}

export function placeholder(node) {
  clear(node);
  node.append(el("p", { class: "muted", text: "(开发中)" }));
}
```

- [ ] **Step 3: Verify they serve over HTTP**

Run: `cd desktop_app; .venv\Scripts\python -m pytest tests/test_static_assets.py -q`
Then add to `desktop_app/tests/test_static_assets.py`:

```python
def test_helper_modules_served(tmp_path: Path):
    client = _client(tmp_path)
    assert client.get("/assets/api.js").status_code == 200
    assert client.get("/assets/ui.js").status_code == 200
```

Run: `cd desktop_app; .venv\Scripts\python -m pytest tests/test_static_assets.py -q`
Expected: PASS.

- [ ] **Step 4: Commit (per repo rule)**

```bash
git add desktop_app/frontend/api.js desktop_app/frontend/ui.js desktop_app/tests/test_static_assets.py
git commit -m "feat(frontend): fetch wrapper + DOM/state helpers"
```

---

## Task 4: Hash router (`app.js`)

**Files:**
- Modify: `desktop_app/frontend/app.js`

- [ ] **Step 1: Write the router**

Overwrite `desktop_app/frontend/app.js`:

```javascript
import { placeholder } from "/assets/ui.js";

// Routes whose module exists. Later batches add import/network/groups/writing/settings.
const ROUTES = {
  papers: () => import("/assets/views/papers.js"),
};

function parseHash() {
  const raw = (location.hash || "#/papers").replace(/^#\//, "");
  const parts = raw.split("/").filter(Boolean);
  return { name: parts[0] || "papers", params: parts.slice(1) };
}

function highlightNav(name) {
  document.querySelectorAll("#nav a").forEach((a) => {
    a.classList.toggle("active", a.getAttribute("href") === "#/" + name);
  });
}

async function route() {
  const view = document.getElementById("view");
  const { name, params } = parseHash();
  highlightNav(name);
  const loader = ROUTES[name];
  if (!loader) {            // nav target not built yet
    placeholder(view);
    return;
  }
  view.textContent = "加载中…";
  try {
    const mod = await loader();
    await mod.render(view, params);
  } catch (err) {
    view.textContent = "页面加载失败:" + err.message;
  }
}

window.addEventListener("hashchange", route);
window.addEventListener("load", route);
```

- [ ] **Step 2: Verify it serves and exports nothing breaking**

Run: `cd desktop_app; .venv\Scripts\python -m pytest tests/test_static_assets.py::test_app_js_served -v`
Expected: PASS (`"render"` no longer in app.js itself — UPDATE the assertion: app.js now imports views that have render; the string `render` still appears via `mod.render`). Confirm `"render" in response.text` still holds (it does: `mod.render(view, params)`). If it does not, change the assertion in `test_app_js_served` to `assert "route" in response.text`.

- [ ] **Step 3: Commit (per repo rule)**

```bash
git add desktop_app/frontend/app.js
git commit -m "feat(frontend): hash router with lazy view modules"
```

---

## Task 5: Papers view — list (`views/papers.js`)

**Files:**
- Create: `desktop_app/frontend/views/papers.js`

- [ ] **Step 1: Create the view with the list renderer**

Create `desktop_app/frontend/views/papers.js`:

```javascript
import { getJSON } from "/assets/api.js";
import { el, clear, loading, errorState } from "/assets/ui.js";

// render() dispatches the three Papers sub-routes:
//   []                -> list
//   [id]              -> detail
//   [id, "decompose"] -> decomposition
export async function render(view, params) {
  if (params.length === 0) return renderList(view);
  if (params.length >= 2 && params[1] === "decompose") return renderDecomposition(view, params[0]);
  return renderDetail(view, params[0]);
}

async function renderList(view) {
  loading(view);
  let data;
  try {
    data = await getJSON("/library/papers");
  } catch (err) {
    return errorState(view, err.message, () => renderList(view));
  }
  const papers = data.papers || [];
  clear(view);
  const search = el("input", { class: "search", placeholder: "搜索标题 / 期刊…" });
  const list = el("div", { class: "paper-list" });

  function draw(filter) {
    clear(list);
    const f = (filter || "").toLowerCase();
    const rows = papers.filter(
      (p) => !f || (p.title || "").toLowerCase().includes(f) || (p.journal || "").toLowerCase().includes(f)
    );
    if (rows.length === 0) {
      list.append(el("p", { class: "muted", text: "无匹配" }));
      return;
    }
    for (const p of rows) {
      list.append(
        el("a", { class: "paper-row", href: "#/papers/" + p.paper_id }, [
          el("span", { class: "ptitle", text: p.title || p.paper_id }),
          el("span", { class: "pmeta", text: [p.year, p.journal, p.paper_type].filter(Boolean).join(" · ") }),
        ])
      );
    }
  }

  search.addEventListener("input", () => draw(search.value));
  view.append(el("h2", { text: `藏书 ${papers.length} 篇` }), search, list);
  draw("");
}
```

(`renderDetail` and `renderDecomposition` are added in Tasks 6 and 7; the import in `render()` references them, so the file will not be runnable end-to-end until Task 6/7 add those functions. To keep each task's file valid JavaScript, add temporary stubs now at the bottom of the file:)

```javascript
async function renderDetail(view, id) { view.textContent = "详情待实现:" + id; }
async function renderDecomposition(view, id) { view.textContent = "拆解待实现:" + id; }
```

- [ ] **Step 2: Register the asset test**

Add to `desktop_app/tests/test_static_assets.py`:

```python
def test_papers_view_served(tmp_path: Path):
    response = _client(tmp_path).get("/assets/views/papers.js")
    assert response.status_code == 200
    assert "renderList" in response.text
```

- [ ] **Step 3: Run tests**

Run: `cd desktop_app; .venv\Scripts\python -m pytest tests/test_static_assets.py -q`
Expected: PASS.

- [ ] **Step 4: Commit (per repo rule)**

```bash
git add desktop_app/frontend/views/papers.js desktop_app/tests/test_static_assets.py
git commit -m "feat(frontend): papers list view"
```

---

## Task 6: Papers view — detail

**Files:**
- Modify: `desktop_app/frontend/views/papers.js`

- [ ] **Step 1: Replace the `renderDetail` stub with the real renderer**

In `desktop_app/frontend/views/papers.js`, replace the temporary stub
`async function renderDetail(view, id) { view.textContent = "详情待实现:" + id; }`
with:

```javascript
function tagRow(label, items) {
  if (!items || items.length === 0) return null;
  const box = el("div", { class: "section" }, [el("h3", { text: label })]);
  for (const t of items) box.append(el("span", { class: "tag", text: t }));
  return box;
}

async function renderDetail(view, id) {
  loading(view);
  let p;
  try {
    p = await getJSON("/papers/" + encodeURIComponent(id));
  } catch (err) {
    if (err.code === 404) return errorState(view, "未找到论文 " + id, null);
    return errorState(view, err.message, () => renderDetail(view, id));
  }
  clear(view);
  view.append(
    el("a", { class: "back", href: "#/papers" }, "← 返回藏书"),
    el("h2", { text: p.title || p.paper_id }),
    el("p", { class: "pmeta", text: [p.year, p.journal, p.doi].filter(Boolean).join(" · ") })
  );

  const card = el("div", { class: "card-box" });
  if (p.objective) card.append(el("div", { class: "section" }, [el("h3", { text: "目标" }), el("p", { text: p.objective })]));
  const findings = p.main_findings || [];
  if (findings.length) {
    const sec = el("div", { class: "section" }, [el("h3", { text: "主要发现" })]);
    const ul = el("ul");
    for (const f of findings) ul.append(el("li", { text: f }));
    sec.append(ul);
    card.append(sec);
  }
  for (const row of [
    tagRow("研究对象", p.research_objects),
    tagRow("方法", p.methods),
    tagRow("领域", p.domain_tags),
  ]) if (row) card.append(row);
  view.append(card);

  const btn = el("button", { text: "查看拆解 →" });
  btn.addEventListener("click", () => { location.hash = "#/papers/" + id + "/decompose"; });
  view.append(el("div", { class: "section" }, [btn]));
}
```

- [ ] **Step 2: Run tests (no backend contract change; static still serves)**

Run: `cd desktop_app; .venv\Scripts\python -m pytest tests/test_static_assets.py tests/test_api_browse.py -q`
Expected: PASS (the browse endpoint contract these reads is already covered by `test_api_browse.py`).

- [ ] **Step 3: Commit (per repo rule)**

```bash
git add desktop_app/frontend/views/papers.js
git commit -m "feat(frontend): papers detail view"
```

---

## Task 7: Papers view — decomposition

**Files:**
- Modify: `desktop_app/frontend/views/papers.js`

- [ ] **Step 1: Replace the `renderDecomposition` stub with the real renderer**

In `desktop_app/frontend/views/papers.js`, replace the temporary stub
`async function renderDecomposition(view, id) { view.textContent = "拆解待实现:" + id; }`
with:

```javascript
function blockList(title, blocks) {
  if (!blocks || blocks.length === 0) return null;
  const sec = el("div", { class: "section" }, [el("h3", { text: title })]);
  for (const b of blocks) sec.append(el("p", { text: b.text || "" }));
  return sec;
}

function atomList(title, atoms) {
  const sec = el("div", { class: "section" }, [el("h3", { text: `${title} (${atoms.length})` })]);
  if (atoms.length === 0) { sec.append(el("p", { class: "muted", text: "无" })); return sec; }
  for (const a of atoms) {
    sec.append(
      el("div", { class: "atom" }, [
        el("div", { text: a.minimal_claim || "" }),
        a.quote ? el("div", { class: "quote", text: "“" + a.quote + "”" }) : null,
      ])
    );
  }
  return sec;
}

async function renderDecomposition(view, id) {
  loading(view);
  let d;
  try {
    d = await getJSON("/papers/" + encodeURIComponent(id) + "/decomposition");
  } catch (err) {
    if (err.code === 404) return errorState(view, "未找到论文 " + id, null);
    return errorState(view, err.message, () => renderDecomposition(view, id));
  }
  const c = d.card || {};
  clear(view);
  view.append(
    el("a", { class: "back", href: "#/papers/" + id }, "← 返回详情"),
    el("h2", { text: (c.title || id) + " · 拆解" })
  );

  const abstract = blockList("摘要", d.abstract_blocks);
  if (abstract) view.append(abstract);
  const intro = blockList("引言提出的问题", d.intro_blocks);
  if (intro) view.append(intro);

  const glossary = d.glossary || [];
  if (glossary.length) {
    const sec = el("div", { class: "section" }, [el("h3", { text: "术语表" })]);
    for (const g of glossary) {
      const term = g.term || g.name || "";
      const def = g.definition || g.meaning || "";
      sec.append(el("p", {}, [el("strong", { text: term }), def ? ":" + def : ""]));
    }
    view.append(sec);
  }

  view.append(atomList("用了哪些分析", d.analyses || []));
  view.append(atomList("得到哪些结果", d.results || []));

  const rel = d.result_relations || [];
  const relSec = el("div", { class: "section" }, [el("h3", { text: `结果间关联 (${rel.length})` })]);
  if (rel.length === 0) relSec.append(el("p", { class: "muted", text: "无" }));
  for (const r of rel) {
    relSec.append(
      el("div", { class: "atom" }, [
        el("div", { text: (r.synthesis_type ? "[" + r.synthesis_type + "] " : "") + (r.claim || "") }),
        el("div", { class: "quote", text: "依据原子:" + (r.supporting_evidence_atom_ids || []).join(", ") }),
      ])
    );
  }
  view.append(relSec);
}
```

- [ ] **Step 2: Run tests**

Run: `cd desktop_app; .venv\Scripts\python -m pytest tests/test_static_assets.py tests/test_api_decomposition.py -q`
Expected: PASS (decomposition endpoint contract is covered by `test_api_decomposition.py`).

- [ ] **Step 3: Commit (per repo rule)**

```bash
git add desktop_app/frontend/views/papers.js
git commit -m "feat(frontend): single-paper decomposition view"
```

---

## Task 8: Real-machine smoke (the manual verification this batch can't automate)

**Files:** none (verification only).

- [ ] **Step 1: Full backend suite green**

Run: `cd desktop_app; .venv\Scripts\python -m pytest -q`
Expected: 119 + new tests passed (≈124), 1 warning.

- [ ] **Step 2: Launch the app against the real library**

Run (PowerShell, from repo root):

```powershell
$env:AUTOREVIEW_LIBRARY_DIR = (Resolve-Path .\Document_Decomposer\library).Path
.\desktop_app\.venv\Scripts\python -m autoreview_app.main
```

(The package is installed editable, so `-m autoreview_app.main` resolves. The env var points the app at the 261-paper engine library.)

- [ ] **Step 3: Click through and confirm**

In the window, verify:
- 藏书 shows "藏书 261 篇" and a scrollable list; the search box filters live.
- Clicking a paper opens its detail (title, meta, 目标, 主要发现, tag rows).
- "查看拆解 →" opens the decomposition (摘要 / 引言 / 术语表 / 分析 / 结果 / 结果间关联). Sections with no data show "无", never a blank panel.
- The other nav links (导入/关系网/课题组/写作/设置) show "(开发中)" — no console error, no white screen.
- This also satisfies the long-standing "M7 GUI actually opens" check (previously unverified).

- [ ] **Step 4: Record the smoke result**

If anything fails to render, note it; otherwise update `desktop_app/README.md` Status line to add: "Frontend batch 1 (shell + Papers) verified in-window on <date> against the 261-paper library." (Per repo rule, show the wording before writing if it is a status claim.)

---

## Self-review checklist (done by plan author)

- **Spec coverage:** Shell + router + view-module architecture ✓ (Tasks 1–4). Papers list/detail/decompose ✓ (Tasks 5–7). No-build static + `/assets` serving ✓ (Task 1). Loading/empty/error states ✓ (`ui.js`, used in every renderer). Smoke verification ✓ (Task 8). Out-of-scope screens (import/network/groups/writing/settings) correctly deferred to later batches — nav placeholders only.
- **Placeholder scan:** No "TBD"/"handle errors" placeholders. Temporary JS stubs in Task 5 are explicitly replaced in Tasks 6/7 with full code.
- **Type/name consistency:** `getJSON`/`postJSON` (api.js) used consistently; `el/clear/loading/empty/errorState/placeholder` (ui.js) names match every call site; `render(view, params)` contract matches `app.js`'s `mod.render(view, params)`; field names (`paper_id, title, year, journal, doi, paper_type, objective, research_objects, methods, domain_tags, main_findings`) match `sqlite_index._row_from`; decomposition fields (`card, abstract_blocks, intro_blocks, glossary, analyses, results, result_relations`) match `decomposition.assemble_decomposition`.
