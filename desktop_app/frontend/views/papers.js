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
