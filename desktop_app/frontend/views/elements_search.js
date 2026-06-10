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
  }

  function drawTree() {
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
        el("div", { class: "quote-box", text: `"${m.quote}"` }),
        el("a", { href: `#/papers/${p.paper_id}/decompose`, text: `原文段 ${m.reading_block_id} ↗` }),
      );
    }
  }
}
