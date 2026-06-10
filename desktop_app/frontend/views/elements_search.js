import { getJSON, postJSON } from "/assets/api.js";
import { el, clear, empty, errorState, loading } from "/assets/ui.js";

// 屏A 检索 = 三栏工作台 + 搜索顶栏 + 列表⇄表格切换(spec §8)。
// v1.1 联动计数(map-home spec §4c):每次选中集变化 POST /elements/refine,
// 左树全量刷新「与已选组合的交集计数」;零结果灰显沉底;热度 top-10 + 折叠分层。
// Wave-3 ⑤:结果行标题化;命中集「送写作」(sessionStorage 种子 → 写作屏预填);
// 选中单个要素时右栏展示配套要素(共现抽屉并入本屏,点一条即加入组合)。
// 状态:selected = 已选要素 chip;mode = "list"|"table"。
// 跨视图保留选择(模块级状态):离开再回来时 chips 不清空,这是有意设计。
let selected = [];
let mode = "list";
let querySeq = 0;

const TOP_VISIBLE = 10; // 每 facet 默认展开的热度条目数
const SEED_PAPERS_KEY = "writingSeedPapers"; // 检索 → 写作 的命中集交接(writing.js 读后即清)
const SEED_TOPIC_KEY = "writingSeedTopic";

export async function render(view, params) {
  loading(view);
  let facets, recs;
  try {
    const [ov, lib] = await Promise.all([
      getJSON("/elements/overview?top_n=9999"),
      getJSON("/library/papers"),
    ]);
    facets = ov.facets;
    recs = Object.fromEntries((lib.papers || []).map((p) => [p.paper_id, p]));
  } catch (err) {
    if (err.code === 503) return empty(view, "尚未构建要素索引 — 回知识地图首页,点右上角状态角标一键构建。");
    return errorState(view, err.message, () => render(view, params));
  }
  const titles = Object.fromEntries(Object.entries(recs).map(([k, p]) => [k, p.title || ""]));

  clear(view);
  view.append(el("h2", { text: "要素检索" }));
  const searchBox = el("input", { class: "search", placeholder: "搜要素:球磨 / XRD / GCMC …(回车选第一个命中)" });
  const chipsRow = el("div");
  const layout = el("div", { class: "elements-layout" });
  const tree = el("div", { class: "facet-tree card-box" });
  const treeFilterBox = el("input", { class: "search", placeholder: "过滤要素树…" });
  const treeBody = el("div");
  tree.append(treeFilterBox, treeBody);
  const results = el("div", { class: "elements-results" });
  const detail = el("div", { class: "elements-detail card-box" });
  layout.append(tree, results, detail);
  view.append(searchBox, chipsRow, layout);
  empty(detail, "点结果里的论文,看命中要素的逐字原文。");

  // 联动计数状态(render 级):counts=null 表示 refine 还没回来,树先用全库静态计数。
  let counts = null;
  let treeFilter = "";
  const openAll = new Set();  // 「展开全部」目前展开着的 facet(重画后保持)
  const openOnes = new Set(); // 「各 1 篇」二级折叠展开着的 facet

  treeFilterBox.addEventListener("input", () => {
    treeFilter = treeFilterBox.value.trim().toLowerCase();
    drawTree();
  });

  drawTree();
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
    if (selected.length) {
      const toggleBtn = el("button", { text: mode === "list" ? "表格模式" : "列表模式" });
      toggleBtn.addEventListener("click", () => { mode = mode === "list" ? "table" : "list"; runQuery(); });
      chipsRow.append(toggleBtn);
    }
    if (selected.length >= 2) {
      const clearBtn = el("button", { text: "清空条件" });
      clearBtn.addEventListener("click", () => { selected = []; drawChips(); drawTree(); runQuery(); });
      chipsRow.append(clearBtn);
    }
  }

  function isSelected(id) { return selected.some((s) => s.id === id); }

  function countOf(item) { return counts ? (counts[item.id] ?? 0) : item.papers; }

  function itemLabel(it) {
    const on = isSelected(it.id);
    const attrs = { text: `${on ? "☑" : "☐"} ${it.display_name} (${it.n})` };
    if (!on && it.n === 0) attrs.class = "muted"; // 零结果灰显;已选条目不灰
    const label = el("label", attrs);
    label.addEventListener("click", () => toggle({ ...it, slug: it.slug || it.id.split("/")[1] }));
    return label;
  }

  function fold(summaryText, openSet, facetId) {
    const det = el("details");
    if (openSet.has(facetId)) det.open = true;
    det.addEventListener("toggle", () => { if (det.open) openSet.add(facetId); else openSet.delete(facetId); });
    det.append(el("summary", { text: summaryText }));
    return det;
  }

  function drawTree() {
    clear(treeBody);
    for (const f of facets) {
      let items = f.top.map((item) => ({ ...item, facet: f.id, n: countOf(item) }));
      if (treeFilter) {
        items = items.filter((it) => (it.display_name || "").toLowerCase().includes(treeFilter)
          || it.id.toLowerCase().includes(treeFilter));
        if (!items.length) continue; // 整个 facet 无命中就不画
      }
      items.sort((a, b) => b.n - a.n || (a.display_name || "").localeCompare(b.display_name || ""));
      treeBody.append(el("h4", { text: `${f.id}(${f.total_elements})` }));
      if (treeFilter) { // 过滤时平铺所有命中项,不折叠
        for (const it of items) treeBody.append(itemLabel(it));
        continue;
      }
      const sel = items.filter((it) => isSelected(it.id));
      const rest = items.filter((it) => !isSelected(it.id));
      const hot = rest.filter((it) => it.n >= 2);
      const ones = rest.filter((it) => it.n === 1);
      const zeros = rest.filter((it) => it.n === 0);
      for (const it of sel) treeBody.append(itemLabel(it)); // 已选置顶,永远可见
      for (const it of hot.slice(0, TOP_VISIBLE)) treeBody.append(itemLabel(it));
      const hidden = Math.max(hot.length - TOP_VISIBLE, 0) + ones.length + zeros.length;
      if (!hidden) continue;
      const det = fold(`展开全部 (${hidden})`, openAll, f.id);
      for (const it of hot.slice(TOP_VISIBLE)) det.append(itemLabel(it));
      if (ones.length) { // 长尾分层:各只命中 1 篇的条目再收一级
        const sub = fold(`其余 ${ones.length} 项(各 1 篇)`, openOnes, f.id);
        for (const it of ones) sub.append(itemLabel(it));
        det.append(sub);
      }
      for (const it of zeros) det.append(itemLabel(it)); // 零结果沉到组末
      treeBody.append(det);
    }
  }

  async function runQuery() {
    const seq = ++querySeq;
    const ids = selected.map((s) => s.id);
    if (ids.length) loading(results);
    else empty(results, "从左栏勾选要素,或在上方搜索 — 命中论文会列在这里。");
    let refine, data;
    try {
      // refine 给左树计数 + 命中论文;query 给表格/详情要用的逐字 matches
      [refine, data] = await Promise.all([
        postJSON("/elements/refine", { element_ids: ids }),
        ids.length ? postJSON("/elements/query", { element_ids: ids }) : Promise.resolve(null),
      ]);
      if (seq !== querySeq) return; // superseded by a newer selection
    } catch (err) {
      if (seq !== querySeq) return;
      return errorState(results, err.message, runQuery);
    }
    counts = refine.counts;
    drawTree(); // 联动:计数徽标 + 灰显沉底 + 折叠分层全量重算
    if (!ids.length) { empty(detail, "点结果里的论文,看命中要素的逐字原文。"); return; }
    clear(results);
    // 命中头行:计数 + 送写作(Wave-3 ⑤:命中集一键带到写作屏出稿)
    const head = el("div", { class: "results-head" }, [
      el("span", { class: "muted", text: `命中 ${refine.papers.length} 篇(AND 组合)` }),
    ]);
    if (refine.papers.length) {
      const sendBtn = el("button", {
        text: `送写作(${refine.papers.length} 篇)`,
        title: "把这批命中论文带到写作屏出稿(可再删减)",
      });
      sendBtn.addEventListener("click", () => {
        try {
          sessionStorage.setItem(SEED_PAPERS_KEY, JSON.stringify(refine.papers));
          sessionStorage.setItem(SEED_TOPIC_KEY, selected.map((s) => s.name).join(" + "));
        } catch (err) { /* 隐私模式存不了:照样跳,用户手填 */ }
        location.hash = "#/writing";
      });
      head.append(sendBtn);
    }
    results.append(head);
    const byId = new Map(data.papers.map((p) => [p.paper_id, p]));
    const rows = refine.papers.map((pid) => byId.get(pid) || { paper_id: pid, matches: [] });
    if (ids.length === 1) drawCooccurrence(selected[0]); // 单要素:右栏先给配套要素
    else empty(detail, "点结果里的论文,看命中要素的逐字原文。");
    if (mode === "table") return drawTable({ papers: rows });
    for (const p of rows) {
      const rec = recs[p.paper_id] || {};
      const row = el("div", { class: "paper-row" }, [
        el("span", { class: "ptitle", text: rec.title || p.paper_id }),
        el("span", { class: "pmeta", text: [p.paper_id, rec.year, rec.journal].filter(Boolean).join(" · ") }),
      ]);
      row.addEventListener("click", () => drawDetail(p));
      results.append(row);
    }
  }

  // 配套要素(共现抽屉并入,Wave-3 ⑤):单要素选中时,右栏列同批论文里的其他要素;
  // 点一条 = 加入 AND 组合(等于把"统计屏抽屉"变成了检索的下一步动作)。
  let coSeq = 0;
  async function drawCooccurrence(s) {
    const seq = ++coSeq;
    clear(detail);
    detail.append(
      el("h3", { text: `「${s.name}」的配套要素` }),
      el("p", { class: "muted", text: "同批命中论文里还出现的要素;点任一条加入组合继续收窄。" }),
    );
    let co;
    try {
      co = await getJSON(`/elements/${s.facet}/${s.slug}/cooccurrence`);
    } catch (err) {
      if (seq === coSeq) errorState(detail, err.message);
      return;
    }
    if (seq !== coSeq) return; // 用户已点了论文/换了选择
    if (!(co.groups || []).length) {
      detail.append(el("p", { class: "muted", text: "没有配套要素。" }));
      return;
    }
    for (const g of co.groups) {
      detail.append(el("h4", { text: g.facet }));
      for (const x of g.items.slice(0, 5)) {
        const row = el("div", { class: "bar-row co-row", title: "加入组合" }, [
          el("span", { class: "bar-label", text: x.display_name }),
          el("span", { class: "bar-count", text: `${x.n}/${co.m}` }),
        ]);
        row.addEventListener("click", () => toggle({
          id: x.id, facet: g.facet, slug: x.id.split("/")[1], display_name: x.display_name,
        }));
        detail.append(row);
      }
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
    const url = URL.createObjectURL(blob);
    const a = el("a", { href: url, download: "elements_query.csv" });
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 100);
  }

  function drawDetail(p) {
    coSeq++; // 盖掉迟到的共现响应
    clear(detail);
    const rec = recs[p.paper_id] || {};
    detail.append(
      el("h3", { text: rec.title || p.paper_id }),
      el("p", { class: "pmeta", text: [p.paper_id, rec.year, rec.journal].filter(Boolean).join(" · ") }),
    );
    for (const m of p.matches) {
      detail.append(
        el("div", {}, [el("span", { class: "tag", text: m.display_name }), ` ${m.surface}`]),
        el("div", { class: "quote-box", text: `"${m.quote}"` }),
        el("a", { href: `#/papers/${p.paper_id}/decompose/${encodeURIComponent(m.reading_block_id)}`,
          text: `原文段 ${m.reading_block_id} ↗`, title: "跳到拆解页并定位这一段原文" }),
      );
    }
  }
}
