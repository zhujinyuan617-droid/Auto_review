# Frontend Batch 3 — 🔴 Backend Features (keyring / groups / search / draft) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Checkbox steps.

**Goal:** Wire the four deferred backend features so every screen shows real data: (1) keyring key reaches the engine client, (2) research-group clustering via Crossref author lookup, (3) live Crossref search, (4) grounded draft generation reusing the engine's brief builder + writing loop.

**Architecture:** No engine changes. Desktop wraps engine modules. Offline tests use fakes (FakeTransport, injected runners, fake keyring); the real network/AI paths are smoke-tested on a real machine (mirrors how the import runner is real-but-fake-tested).

**Repo rule:** commit only when the user says 提交. `git commit` steps are checkpoints.

**Grounding facts (from code investigation):**
- Authors are absent from all library JSON; only `metadata_candidates.first_page_text` (free-form) or Crossref-by-DOI give author lists. 254/261 have DOIs; 7 blank (`S26,S27,S36,S44,S47,S83,S351`) — excluded from clustering by design (`save_authors` skips blank DOI).
- `cluster_papers(papers, authors_by_doi)` reads `paper.{paper_id,doi,title}` and `authors_by_doi[doi.lower()] -> [names]` (last = senior). `save_authors(db, doi, authors)` upserts; `load_authors(db) -> {doi: [names]}`.
- `build_ai_client(config_root)` calls engine `load_ai_config` (env `DOCDECOMP_AI_API_KEY` beats `config/ai.local.json`). Keyring key in `settings.get_api_key()`.
- Draft: `run_writing_loop(brief, run_dir, max_rounds, author_client, expert_client)` (desktop `writing/loop.py`). A grounded `brief` must come from the engine `build_writing_brief.py` (run as subprocess against the engine tree: `Document_Decomposer/` with `config/`, `reports/connection/`, `library/`). Seed mode + section_count=1 keeps gates lenient. The runner builds the brief from a selection; the frontend cannot.

---

## Task 1: keyring key → engine client

**Files:** Modify `desktop_app/src/autoreview_app/ai/client.py`; Test `desktop_app/tests/test_ai_client.py` (append).

- [ ] **Step 1: failing test** — append to `desktop_app/tests/test_ai_client.py`:

```python
def test_build_ai_client_prefers_keyring(tmp_path, monkeypatch):
    # When a key is in the OS keychain and no env override, it must reach the config.
    import autoreview_app.ai.client as client_mod
    monkeypatch.setattr(client_mod.app_settings, "get_api_key", lambda: "sk-keyring-xyz")
    monkeypatch.delenv("DOCDECOMP_AI_API_KEY", raising=False)
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    (cfg_dir / "ai.local.json").write_text(
        '{"base_url":"https://api.deepseek.com","api_key":"sk-file-old","model":"deepseek-v4-flash"}',
        encoding="utf-8",
    )
    c = client_mod.build_ai_client(tmp_path)
    assert c.config.api_key == "sk-keyring-xyz"


def test_build_ai_client_env_beats_keyring(tmp_path, monkeypatch):
    import autoreview_app.ai.client as client_mod
    monkeypatch.setattr(client_mod.app_settings, "get_api_key", lambda: "sk-keyring-xyz")
    monkeypatch.setenv("DOCDECOMP_AI_API_KEY", "sk-env-wins")
    cfg_dir = tmp_path / "config"; cfg_dir.mkdir()
    (cfg_dir / "ai.local.json").write_text(
        '{"base_url":"https://api.deepseek.com","api_key":"sk-file","model":"m"}', encoding="utf-8")
    c = client_mod.build_ai_client(tmp_path)
    assert c.config.api_key == "sk-env-wins"
```

- [ ] **Step 2: run, expect fail** (`AttributeError: module has no attribute 'app_settings'` or key mismatch). Run: `desktop_app\.venv\Scripts\python.exe -m pytest desktop_app/tests/test_ai_client.py -k keyring_or_env -q` (use `-k "keyring or env"`).

- [ ] **Step 3: implement** — rewrite `desktop_app/src/autoreview_app/ai/client.py`:

```python
from __future__ import annotations

import os
from pathlib import Path

from .. import engine_bridge  # noqa: F401  # ensures engine src is on sys.path
from .. import settings as app_settings

from docdecomp.ai_client import OpenAICompatibleClient, load_ai_config


def build_ai_client(config_root: Path, config_path: Path | None = None) -> OpenAICompatibleClient:
    """Build the engine's real AI client from config. The OS-keychain key (if set
    and no explicit env override) is injected so a key entered in Settings reaches
    the engine. Precedence: DOCDECOMP_AI_API_KEY env > keychain > config file."""
    key = app_settings.get_api_key()
    if key and not os.environ.get("DOCDECOMP_AI_API_KEY"):
        os.environ["DOCDECOMP_AI_API_KEY"] = key
    config = load_ai_config(config_root, config_path)
    return OpenAICompatibleClient(config)
```

- [ ] **Step 4: run tests pass**; **Step 5: full suite** (expect prior + 2). **Step 6: commit** `feat(desktop): keyring key reaches the engine AI client`.

(Frontend follow-up: in `settings.js`, change the "暂未生效" note to "已接入引擎(env 覆盖优先)". Do this in Task 8.)

---

## Task 2: Crossref by-DOI author fetch + author-store population + build endpoint

**Files:** Modify `desktop_app/src/autoreview_app/discovery/sources/crossref.py` (add `fetch_by_doi`); Create `desktop_app/src/autoreview_app/groups/populate.py`; Modify `api.py` (add `POST /groups/build` job + inject author-populate runner); Tests `desktop_app/tests/test_crossref_source.py`, `desktop_app/tests/test_groups_populate.py`.

- [ ] **Step 1 (crossref by-DOI) failing test** — append to `desktop_app/tests/test_crossref_source.py` a test that, given a `FakeTransport` returning a Crossref `works/{doi}` JSON (`{"message": {"author": [{"family":"Yin","given":"Xiaolong"},{"family":"Koch","given":"Donald L."}], "title":["T"], "DOI":"10.1/x"}}`), `CrossrefSource(transport).fetch_by_doi("10.1/x")` returns a `CitationRecord` whose `authors == ("Yin, Xiaolong", "Koch, Donald L.")`. (Mirror the existing search test's FakeTransport usage in that file.)

- [ ] **Step 2: run, fail.**

- [ ] **Step 3: implement `fetch_by_doi`** in `crossref.py`. Read the existing file first to reuse `_to_record` and the transport. Add:

```python
    def fetch_by_doi(self, doi: str):
        """Fetch one work by DOI from Crossref; return a CitationRecord or None."""
        url = "https://api.crossref.org/works/" + quote(doi, safe="")
        body = self._transport.get_json(url)
        message = body.get("message") if isinstance(body, dict) else None
        if not isinstance(message, dict):
            return None
        return self._to_record(message)
```

(Use the same `quote` import + `self._transport.get_json` pattern the existing search method uses — match the real signatures in the file. If `_to_record` is named differently, use the real name.)

- [ ] **Step 4: run pass.**

- [ ] **Step 5 (populate) failing test** — create `desktop_app/tests/test_groups_populate.py`: build a tmp library with 2 papers (use `_library_fixtures.write_card` with DOIs), a fake source whose `fetch_by_doi` returns canned `CitationRecord`s, call `populate_authors(library_dir, authors_db, source, progress)`, then assert `load_authors(authors_db)` maps each lower-cased DOI to the expected author list. Include one paper with a blank DOI and assert it is skipped.

- [ ] **Step 6: run, fail.**

- [ ] **Step 7: implement** `desktop_app/src/autoreview_app/groups/populate.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Protocol

from ..library_index import list_papers
from ..store.sqlite_index import _load_card  # reuse the card reader
from .store import save_authors


class DoiAuthorSource(Protocol):
    def fetch_by_doi(self, doi: str) -> Any: ...


def populate_authors(
    library_dir: Path,
    authors_db: Path,
    source: DoiAuthorSource,
    progress: Callable[[str], None] = lambda _m: None,
) -> dict[str, int]:
    """Populate the author store by looking up each paper's DOI on the source.

    Returns counts {found, skipped}. Papers with a blank DOI or no source hit are
    skipped (save_authors also skips blank DOIs).
    """
    ids = list_papers(library_dir)
    found = skipped = 0
    for i, pid in enumerate(ids):
        card = _load_card(library_dir / pid) or {}
        doi = ((card.get("paper") or {}).get("doi") or "").strip()
        progress(f"{i + 1}/{len(ids)} {pid}")
        if not doi:
            skipped += 1
            continue
        try:
            rec = source.fetch_by_doi(doi)
        except Exception:  # noqa: BLE001 — network hiccup, skip this paper
            rec = None
        authors = list(rec.authors) if rec and rec.authors else []
        if not authors:
            skipped += 1
            continue
        save_authors(authors_db, doi, authors)
        found += 1
    return {"found": found, "skipped": skipped}
```

(If `_load_card` is private/awkward to import, replace with a small local `json.loads` of `literature_card.json` — read the real `sqlite_index.py` to confirm the import works; otherwise inline the read.)

- [ ] **Step 8: run pass.**

- [ ] **Step 9: add `POST /groups/build` endpoint** in `api.py`. Add an injectable `author_populate_runner` param to `create_app` (default wires `CrossrefSource(UrllibTransport())` + `populate_authors`), and a route that submits a job:

```python
    @app.post("/groups/build")
    def groups_build() -> dict:
        job_id = jobs.submit(lambda report: author_populate_runner(report))
        return {"job_id": job_id}
```

with a `_default_author_populate_runner(config)` mirroring `_default_import_runner` (builds `populate_authors(config.library_dir, config.authors_db, CrossrefSource(UrllibTransport()), report)`). Add a test in `desktop_app/tests/test_api_groups.py` using an injected fake runner asserting `/groups/build` returns a `job_id` and the job result has `found`.

- [ ] **Step 10: run pass; full suite; commit** `feat(desktop): crossref-by-DOI author lookup + group author-store population job`.

---

## Task 3: Groups frontend screen

**Files:** Create `desktop_app/frontend/views/groups.js`; Modify `app.js` (register `groups` route — replace the placeholder); Modify `test_static_assets.py`.

- [ ] **Step 1: create groups.js** — `render(view)` fetches `GET /groups`; if `groups` empty, show an empty state plus a "建立作者库(Crossref)" button that `POST /groups/build`, polls `/jobs/{id}` (reuse the same poll shape as import: status/progress/result), then re-renders. When groups exist, render one `.card-box` per group: anchor_name (senior author), size, and the paper list (links to `#/papers/<id>`). Use the same `el/clear/loading/empty/errorState` helpers and the job-poll pattern from `import.js`.

```javascript
import { getJSON, postJSON } from "/assets/api.js";
import { el, clear, loading, errorState } from "/assets/ui.js";

function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

export async function render(view) {
  loading(view);
  let data;
  try { data = await getJSON("/groups"); }
  catch (err) { return errorState(view, err.message, () => render(view)); }
  const groups = data.groups || [];
  clear(view);
  view.append(el("h2", { text: `课题组 (${groups.length})` }));
  if (groups.length === 0) {
    view.append(el("p", { class: "muted", text: "作者库未建立 —— 点下方按钮用 Crossref 按 DOI 拉取作者(需联网,254 篇约数分钟)。" }));
    const btn = el("button", { text: "建立作者库(Crossref)" });
    const status = el("div", { class: "section" });
    btn.addEventListener("click", async () => {
      btn.disabled = true; clear(status); status.append(el("p", { class: "muted", text: "提交中…" }));
      try {
        const { job_id } = await postJSON("/groups/build", {});
        for (let i = 0; i < 1200; i++) {
          const job = await getJSON("/jobs/" + job_id);
          clear(status); status.append(el("p", { class: "muted", text: (job.progress || []).slice(-1)[0] || "运行中…" }));
          if (job.status === "succeeded") { render(view); return; }
          if (job.status === "failed") { status.append(el("p", { class: "error", text: "失败:" + (job.error || "") })); break; }
          await sleep(1000);
        }
      } catch (err) { errorState(status, err.message, null); }
      finally { btn.disabled = false; }
    });
    view.append(btn, status);
    return;
  }
  for (const g of groups) {
    const box = el("div", { class: "card-box section" }, [
      el("h3", { text: `${g.anchor_name || g.anchor_identity || "?"} · ${g.size} 篇` }),
    ]);
    const list = el("div", { class: "paper-list" });
    for (const p of g.papers || []) {
      list.append(el("a", { class: "paper-row", href: "#/papers/" + p.paper_id }, [
        el("span", { class: "ptitle", text: p.title || p.paper_id }),
      ]));
    }
    box.append(list);
    view.append(box);
  }
}
```

- [ ] **Step 2: register route** in `app.js` ROUTES: add `groups: () => import("/assets/views/groups.js"),`.
- [ ] **Step 3: asset test** (`test_groups_view_served`, assert 200 + `"课题组"`). **Step 4: run; commit** `feat(frontend): research-group screen + build-author-store action`.

---

## Task 4: default Crossref search runner

**Files:** Modify `api.py` (add `_default_search_runner`); Test `desktop_app/tests/test_api_discovery.py` (append a default-wiring test using an injected search_runner is already covered; add one asserting the default runner is wired when none injected — but since the default makes a real network call, instead test that `search_runner=` injection path works and that the default factory is constructed without error).

- [ ] **Step 1: implement** `_default_search_runner(config)` in `api.py`:

```python
def _default_search_runner(config: AppConfig) -> SearchRunner:
    def run(query: str) -> list[dict[str, Any]]:
        from .discovery.sources.crossref import CrossrefSource
        from .discovery.transport import UrllibTransport
        source = CrossrefSource(UrllibTransport())
        return [_record_to_dict(r) for r in source.search(query)]
    return run
```

and change the `search` route to use `search_runner if search_runner is not None else _default_search_runner(config)`. (Match `CrossrefSource.search`'s real return type — read `crossref.py`. If `search` returns `CitationRecord`s, `_record_to_dict` applies.)

- [ ] **Step 2: test** — append to `test_api_discovery.py` a test injecting a fake `search_runner=lambda q: [{"title": "T", "doi": "10/x", ...}]` and asserting `POST /discovery/search` returns those records (proves the route uses the runner). The 503 test for the unconfigured case must be updated since the default is now wired — instead assert that with a fake transport-less default it still returns 200 (or keep an injected-runner test). Read `test_api_discovery.py` first and adapt without breaking existing tests.

- [ ] **Step 3: run; commit** `feat(desktop): default crossref search runner`.

---

## Task 5: search UI in the import screen

**Files:** Modify `desktop_app/frontend/views/import.js` (add a search section); Modify `test_static_assets.py` (assertion still holds — `pollJob` present).

- [ ] **Step 1:** add a `searchSection()` to `import.js` and append it in `render`. It has a query input + 搜索 button → `postJSON("/discovery/search", {query})` → render each record (title, year·journal·doi). On 503/error show `errorState`. Reuse `el/clear/errorState`. Keep the existing PDF + RIS sections.

- [ ] **Step 2: run static test; commit** `feat(frontend): in-app OA search (crossref) in import screen`.

---

## Task 6: grounded draft runner (backend)

**Files:** Modify `api.py` (change `DraftRequest` to a selection; add `_default_draft_runner`); Create `desktop_app/src/autoreview_app/writing/draft_runner.py`; Test `desktop_app/tests/test_api_writing_draft.py` (adapt), `desktop_app/tests/test_draft_runner.py`.

**Design:** The runner builds a real brief by running the engine's `build_writing_brief.py` as a subprocess against the engine tree (`Document_Decomposer/`), then runs `run_writing_loop`. The API takes a **selection** `{topic, paper_ids:[...], concepts:[...], section_count=1, word_target=300}`, not a pre-built brief.

- [ ] **Step 1: implement** `desktop_app/src/autoreview_app/writing/draft_runner.py`:

```python
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from .. import engine_bridge
from .loop import run_writing_loop


def build_brief_via_engine(selection: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    """Build a grounded writing brief by invoking the engine's build_writing_brief.py
    as a subprocess against the engine tree, then read brief.json back."""
    engine_root = engine_bridge.ENGINE_SRC.parent  # Document_Decomposer/
    script = engine_root / "scripts" / "write" / "build_writing_brief.py"
    run_dir.mkdir(parents=True, exist_ok=True)
    out = run_dir / "brief.json"
    cmd = [sys.executable, str(script),
           "--out", str(out),
           "--section-count", str(selection.get("section_count", 1)),
           "--word-target", str(selection.get("word_target", 300))]
    if selection.get("topic"):
        cmd += ["--topic", str(selection["topic"])]
    for pid in selection.get("paper_ids", []):
        cmd += ["--paper-id", str(pid)]
    for c in selection.get("concepts", []):
        cmd += ["--concept", str(c)]
    subprocess.run(cmd, cwd=str(engine_root), check=True, capture_output=True, text=True)
    return json.loads(out.read_text(encoding="utf-8"))


def run_draft(selection: dict[str, Any], library_dir: Path, client_factory: Callable[[], Any],
              progress: Callable[[str], None], max_rounds: int = 2) -> dict[str, Any]:
    run_dir = library_dir.parent / "writing" / "run"
    progress("building brief")
    brief = build_brief_via_engine(selection, run_dir)
    progress("running writing loop")
    client = client_factory()
    summary = run_writing_loop(brief, run_dir, max_rounds, client, client)
    draft = run_dir / "draft_v01.md"
    summary["draft_text"] = draft.read_text(encoding="utf-8") if draft.is_file() else ""
    summary["run_dir"] = str(run_dir)
    progress("done")
    return summary
```

(Read `engine_bridge.py` to confirm `ENGINE_SRC` and that `.parent` is `Document_Decomposer/`. Read `build_writing_brief.py` argparse to confirm flag names `--out/--topic/--paper-id/--concept/--section-count/--word-target`. Confirm the per-round draft file name written by `run_writing_round` — the investigation said `draft_v01.md` / `draft_vNN.md`; adjust if the real name differs.)

- [ ] **Step 2: change the API contract** in `api.py`: replace `DraftRequest(brief: dict)` with `DraftSelection(topic: str = "", paper_ids: list[str] = [], concepts: list[str] = [], section_count: int = 1, word_target: int = 300)`; the `draft` route submits `lambda report: draft_runner(req.model_dump(), report)`; add `_default_draft_runner(config)` building the real client via `build_ai_client(engine_root)` and calling `run_draft(...)`.

- [ ] **Step 3: tests** — `test_draft_runner.py`: unit-test `build_brief_via_engine` is hard (subprocess); instead test `run_draft` with a monkeypatched `build_brief_via_engine` (returns a canned brief) + a `SequencedFakeClient` so the loop runs offline, asserting the returned summary has `status` and `draft_text`. Adapt `test_api_writing_draft.py` to the new selection contract using an injected `draft_runner`.

- [ ] **Step 4: run; commit** `feat(desktop): grounded draft runner (engine brief + writing loop)`.

---

## Task 7: draft UI in the writing screen

**Files:** Modify `desktop_app/frontend/views/writing.js` (replace the "未接通" draft section with a selection form); `test_static_assets.py` (assertion `checkSection` still holds).

- [ ] **Step 1:** replace `draftSection()` with a form: topic input, paper-ids input (comma-separated), a 出稿 button → `POST /writing/draft` with `{topic, paper_ids:[...], section_count:1, word_target:300}` → poll `/jobs/{id}` → on success render `result.draft_text` in a `<pre>` (or `.card-box`), on failure show error. Reuse the poll pattern. Warn that it makes real AI calls and takes a while.

- [ ] **Step 2: run static test; commit** `feat(frontend): draft generation form in writing screen`.

---

## Task 8: misc + real-machine smoke

- [ ] **Step 1:** In `settings.js`, change the API-key note from "暂未生效" to "已接入引擎(env 覆盖优先)".
- [ ] **Step 2:** Full suite green: `desktop_app\.venv\Scripts\python.exe -m pytest desktop_app -q`.
- [ ] **Step 3:** Relaunch (`$env:AUTOREVIEW_LIBRARY_DIR=...; python -m autoreview_app.main`) and smoke each new path: groups build (or its offline-injected equivalent), search a real query, draft one section for 1-2 paper ids. Record results; note any failure honestly (these hit real network/AI).

---

## Self-review (plan author)
- Coverage: keyring→engine (T1), groups author-store + screen (T2,T3), live search + UI (T4,T5), grounded draft + UI (T6,T7), settings note + smoke (T8). All four 🔴 items addressed.
- Honesty: draft runner reuses the engine's tested brief builder via subprocess (lowest risk) against the engine tree; API contract changed from brief→selection because the frontend cannot build a grounded brief. Real network/AI paths are smoke-only (offline tests use fakes), matching the import-runner precedent.
- Consistency: `populate_authors`, `fetch_by_doi`, `run_draft`, `build_brief_via_engine` signatures match their call sites and tests. Field names from real endpoints. Verify the real names in `crossref.py`, `engine_bridge.py`, `build_writing_brief.py`, and the per-round draft filename during implementation; adjust if reality differs (noted inline).
