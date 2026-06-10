import { getJSON, postJSON } from "/assets/api.js";
import { el, clear, empty, errorState, loading } from "/assets/ui.js";

// 屏B 统计 = 分层:总览仪表盘 -> 单 facet 大图 -> 抽屉(论文+引文+共现)。
// 路由: #/stats(总览) #/stats/<facet>(大图)。role 开关控制是否含 mentioned。
let includeMentioned = false;
let _pollTimer = null;
let _titlesCache = null;

export async function render(view, params) {
  if (params.length >= 1) return renderFacet(view, params[0]);
  return renderOverview(view);
}

function roleParam() { return includeMentioned ? "&role=all" : "&role=used"; }

async function renderOverview(view) {
  if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
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
    for (const item of f.top) box.append(bar(item, max, () => { location.hash = `#/stats/${f.id}`; }));
    box.append(el("a", { href: `#/stats/${f.id}`, text: "看全部 →" }));
    grid.append(box);
  }
  view.append(grid);
}

async function renderFacet(view, facet) {
  if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
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

let drawerSeq = 0;

async function drawDrawer(drawer, facet, item) {
  const seq = ++drawerSeq;
  loading(drawer);
  const slug = item.slug || item.id.split("/")[1];
  let detail, co, titles;
  try {
    if (!_titlesCache) _titlesCache = getJSON("/library/papers");
    const [d, c, libData] = await Promise.all([
      getJSON(`/elements/${facet}/${slug}`),
      getJSON(`/elements/${facet}/${slug}/cooccurrence`),
      _titlesCache,
    ]);
    detail = d; co = c;
    titles = Object.fromEntries((libData.papers || []).map((p) => [p.paper_id, p.title || ""]));
  } catch (err) {
    _titlesCache = null; // 失败不缓存
    if (seq !== drawerSeq) return;
    return errorState(drawer, err.message);
  }
  if (seq !== drawerSeq) return; // superseded by a newer click
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
        el("div", { class: "quote-box", text: `"${q.quote}"` }),
        el("a", { href: `#/papers/${p.paper_id}/decompose`, text: `原文段 ${q.reading_block_id} ↗` }),
      );
    }
  }
}

function bar(item, max, onClick) {
  const fill = el("span", { class: "bar-fill" });
  fill.style.display = "block";
  fill.style.width = `${Math.max(2, Math.round((100 * item.papers) / max))}%`;
  const row = el("div", { class: "bar-row" }, [
    el("span", { class: "bar-label", text: item.display_name }),
    el("span", { class: "bar-track" }, [fill]),
    el("span", { class: "bar-count", text: String(item.papers) }),
  ]);
  row.addEventListener("click", onClick);
  return row;
}

function roleToggle(redraw) {
  const input = el("input", { type: "checkbox" });
  input.checked = includeMentioned;
  input.addEventListener("change", () => {
    includeMentioned = input.checked;
    redraw();
  });
  return el("label", { class: "muted" }, [input, " 包含 mentioned(综述等仅提及)"]);
}

function renderBuildOffer(view) {
  if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
  clear(view);
  view.append(
    el("h2", { text: "全库统计" }),
    el("p", { text: "还没有要素索引。点下面按钮做一次全库构建(并行逐批运行,全库量级通常 1–2 小时,费用约几十元)。中途退出应用会中断;之后再点本按钮会自动续跑缺失的部分,不会重复归并。" }),
  );
  const btn = el("button", { text: "构建要素索引(全库)" });
  const log = el("pre", { class: "muted" });
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    try {
      const { job_id } = await postJSON("/elements/bootstrap", {});
      _pollTimer = setInterval(async () => {
        try {
          const s = await getJSON(`/jobs/${job_id}`);
          log.textContent = s.progress.slice(-8).join("\n");
          if (s.status !== "running") {
            clearInterval(_pollTimer); _pollTimer = null;
            if (!location.hash.startsWith("#/stats")) return; // 用户已离开本屏,不碰别屏的 DOM
            if (s.status === "succeeded") renderOverview(view);
            else errorState(view, "构建失败:" + s.error, () => renderBuildOffer(view));
          }
        } catch (err) {
          clearInterval(_pollTimer); _pollTimer = null;
          if (!location.hash.startsWith("#/stats")) return; // 用户已离开本屏,不碰别屏的 DOM
          errorState(view, err.message, () => renderBuildOffer(view));
        }
      }, 2000);
    } catch (err) { errorState(view, err.message, () => renderBuildOffer(view)); }
  });
  view.append(btn, log);
}
