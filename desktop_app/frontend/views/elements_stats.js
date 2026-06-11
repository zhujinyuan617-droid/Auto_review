import { getJSON, postJSON } from "/assets/api.js";
import { el, clear, empty, errorState, loading } from "/assets/ui.js";
import { t } from "/assets/i18n.js";

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
  view.append(el("h2", { text: t("stats.title", { n: ov.library_papers }) }), roleToggle(() => renderOverview(view)));
  const grid = el("div", { class: "stats-grid" });
  for (const f of ov.facets) {
    const box = el("div", { class: "card-box" });
    box.append(el("h3", { text: t("stats.facet_overview_head", { facet: f.id, n: f.total_elements }) }));
    const max = f.top.length ? f.top[0].papers : 1;
    for (const item of f.top) box.append(bar(item, max, () => { location.hash = `#/stats/${f.id}`; }));
    box.append(el("a", { href: `#/stats/${f.id}`, text: t("stats.see_all") }));
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
    el("p", {}, [el("a", { href: "#/stats", text: t("stats.back") })]),
    el("h2", { text: t("stats.facet_title", { facet, n: stats.items.length }) }),
    roleToggle(() => renderFacet(view, facet)),
  );
  const layout = el("div", { class: "elements-layout" });
  const chart = el("div", { class: "elements-results" });
  const drawer = el("div", { class: "elements-detail card-box" });
  empty(drawer, t("stats.drawer_hint"));
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
  drawer.append(el("h3", { text: t("stats.drawer_head", { name: detail.display_name, n: detail.paper_count }) }));
  if (detail.aliases.length) drawer.append(el("p", { class: "muted", text: t("stats.aliases_prefix") + detail.aliases.join(" / ") }));

  drawer.append(el("h4", { text: t("stats.cooc_head", { n: co.m }) }));
  for (const g of co.groups) {
    drawer.append(el("p", { class: "muted", text: g.facet }));
    for (const x of g.items.slice(0, 5)) {
      drawer.append(el("div", { class: "bar-row" }, [
        el("span", { class: "bar-label", text: x.display_name }),
        el("span", { class: "bar-count", text: `${x.n}/${co.m}` }),
      ]));
    }
  }

  drawer.append(el("h4", { text: t("stats.papers_head") }));
  for (const p of detail.papers) {
    drawer.append(el("div", { class: "paper-row" }, [
      el("b", { text: (titles[p.paper_id] || p.paper_id).slice(0, 60) }),
    ]));
    for (const q of p.quotes) {
      drawer.append(
        el("div", { class: "quote-box", text: `"${q.quote}"` }),
        el("a", { href: `#/papers/${p.paper_id}/decompose/${encodeURIComponent(q.reading_block_id)}`,
          text: t("papers.block_anchor_label"), title: t("search.block_anchor_title") }),
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
  return el("label", { class: "muted" }, [input, t("stats.role_toggle_label")]);
}

function renderBuildOffer(view) {
  if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
  clear(view);
  view.append(
    el("h2", { text: t("stats.title_plain") }),
    el("p", { text: t("stats.build_offer_hint") }),
  );
  const btn = el("button", { text: t("stats.build_btn") });
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
            else errorState(view, t("stats.build_fail_prefix") + s.error, () => renderBuildOffer(view));
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
