import { getJSON } from "/assets/api.js";
import { el, clear, loading, errorState } from "/assets/ui.js";

// render() dispatches the three Papers sub-routes:
//   []                          -> list
//   [id]                        -> detail
//   [id, "decompose"]           -> decomposition
//   [id, "decompose", blockId]  -> decomposition + 原文段定位(检索/统计的"原文段↗"落点)
export async function render(view, params) {
  if (params.length === 0) return renderList(view);
  if (params.length >= 2 && params[1] === "decompose") {
    return renderDecomposition(view, params[0], params[2] ? decodeURIComponent(params[2]) : null);
  }
  return renderDetail(view, params[0]);
}

function pdfButton(id) {
  const btn = el("button", { text: "打开 PDF", title: "在新窗口打开原文 PDF" });
  btn.addEventListener("click", () => window.open("/papers/" + encodeURIComponent(id) + "/pdf", "_blank"));
  return btn;
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
  view.append(el("div", { class: "section", style: "display:flex;gap:8px;" }, [btn, pdfButton(id)]));

  // 图表画廊(Wave-3 ②:图表墙撤屏后的完整画廊新家);拉不到图不挡详情
  try {
    const figs = (await getJSON("/papers/" + encodeURIComponent(id) + "/figures")).figures || [];
    if (figs.length) {
      const { openLightbox } = await import("/assets/views/figures.js");
      const sec = el("div", { class: "section" }, [el("h3", { text: `图表(${figs.length} 张,点开看大图)` })]);
      const grid = el("div", {
        style: "display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;",
      });
      figs.forEach((name, i) => {
        const img = el("img", {
          src: "/papers/" + encodeURIComponent(id) + "/figures/" + encodeURIComponent(name),
          loading: "lazy", alt: name, title: name,
          style: "width:100%;height:110px;object-fit:contain;background:#fff;" +
            "border:1px solid #d0d7de;border-radius:6px;cursor:zoom-in;",
        });
        img.addEventListener("error", () => img.remove());
        img.addEventListener("click", () => openLightbox(id, figs, i));
        grid.append(img);
      });
      sec.append(grid);
      view.append(sec);
    }
  } catch (err) { /* figures 可选 */ }
}
function blockList(title, blocks) {
  if (!blocks || blocks.length === 0) return null;
  const sec = el("div", { class: "section" }, [el("h3", { text: title })]);
  for (const b of blocks) sec.append(el("p", { text: b.text || "" }));
  return sec;
}

// "原文段↗"锚点兑现(Wave-3 ③):点开 = 取 GET /papers/{id}/blocks/{rb},
// 就地展开该段全文(章节名 + 页码 + 下一段预览),再点收起。
function blockAnchor(paperId, rbId) {
  if (!rbId) return null;
  const wrap = el("span", { class: "block-anchor" });
  const a = el("a", { href: "javascript:void 0", text: "原文段 ↗", title: "就地展开这一段原文" });
  const slot = el("div", { class: "block-ctx" });
  slot.hidden = true;
  let loaded = false;
  a.addEventListener("click", async () => {
    slot.hidden = !slot.hidden;
    if (loaded || slot.hidden) return;
    loaded = true;
    slot.append(el("p", { class: "muted", text: "加载原文段…" }));
    try {
      const d = await getJSON(`/papers/${encodeURIComponent(paperId)}/blocks/${encodeURIComponent(rbId)}`);
      clear(slot);
      slot.append(...blockContextNodes(d));
    } catch (err) {
      clear(slot);
      slot.append(el("p", { class: "error", text: err.code === 404
        ? "原文段不存在(可能来自旧版索引)" : "原文段加载失败:" + err.message }));
    }
  });
  wrap.append(a, slot);
  return wrap;
}

function blockContextNodes(d) {
  const b = d.block || {};
  const out = [
    el("div", { class: "pmeta", text: [b.section_title || "原文",
      b.page_start != null ? `第 ${b.page_start} 页` : null].filter(Boolean).join(" · ") }),
    el("p", { text: b.text || "(空段)" }),
  ];
  if (d.next && d.next.text) {
    out.push(el("p", { class: "muted", text: "下一段:" + String(d.next.text).slice(0, 140) + "…" }));
  }
  return out;
}

function atomList(title, atoms, paperId) {
  const sec = el("div", { class: "section" }, [el("h3", { text: `${title} (${atoms.length})` })]);
  if (atoms.length === 0) { sec.append(el("p", { class: "muted", text: "无" })); return sec; }
  for (const a of atoms) {
    const head = a.values && a.values.length
      ? `${a.minimal_claim || ""} = ${a.values.join(" / ")}`
      : (a.minimal_claim || "");
    sec.append(
      el("div", { class: "atom" }, [
        el("div", { text: head }),
        a.quote ? el("div", { class: "quote", text: "“" + a.quote + "”" }) : null,
        blockAnchor(paperId, a.reading_block_id),
      ])
    );
  }
  return sec;
}

async function renderDecomposition(view, id, focusBlockId) {
  loading(view);
  let d;
  try {
    d = await getJSON("/papers/" + encodeURIComponent(id) + "/decomposition");
  } catch (err) {
    if (err.code === 404) return errorState(view, "未找到论文 " + id, null);
    return errorState(view, err.message, () => renderDecomposition(view, id, focusBlockId));
  }
  const c = d.card || {};
  clear(view);
  // 素材来源诚实标注:elements=新链(逐字锚定要素);legacy=旧原子链
  const srcBadge = d.source
    ? el("span", {
        class: "tag",
        title: d.source === "elements" ? "素材来自要素抽取链(逐字原文锚定)" : "素材来自旧版原子链(待要素链补抽后自动切换)",
        text: d.source === "elements" ? "素材:要素链" : "素材:旧链 legacy",
      })
    : null;
  view.append(
    el("a", { class: "back", href: "#/papers/" + id }, "← 返回详情"),
    el("h2", { text: (c.title || id) + " · 拆解" }),
    el("div", { class: "section", style: "display:flex;gap:8px;align-items:center;" }, [pdfButton(id), srcBadge])
  );

  // 深链定位:从检索/统计的"原文段↗"跳来时,顶端直接展开该原文段
  if (focusBlockId) {
    const banner = el("div", { class: "card-box block-focus" }, [
      el("h3", { style: "margin-top:0;", text: "原文段定位" }),
    ]);
    view.append(banner);
    getJSON(`/papers/${encodeURIComponent(id)}/blocks/${encodeURIComponent(focusBlockId)}`)
      .then((bd) => banner.append(...blockContextNodes(bd)))
      .catch((err) => banner.append(el("p", { class: "error", text: err.code === 404
        ? "该原文段不存在(可能来自旧版索引)。" : "原文段加载失败:" + err.message })));
  }

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

  view.append(atomList("用了哪些分析", d.analyses || [], id));
  if ((d.conditions || []).length) {
    view.append(atomList("在什么条件下(温压/浓度等)", d.conditions, id));
  }
  view.append(atomList("得到哪些结果", d.results || [], id));

  const rel = d.result_relations || [];
  const relSec = el("div", { class: "section" }, [el("h3", { text: `结果间关联 (${rel.length})` })]);
  if (rel.length === 0) relSec.append(el("p", { class: "muted", text: "无" }));
  for (const r of rel) {
    // 依据原子的内部编号不再上屏(后台溯源字段;屏上各条目就在上方两节里)
    relSec.append(
      el("div", { class: "atom" }, [
        el("div", { text: (r.synthesis_type ? "[" + r.synthesis_type + "] " : "") + (r.claim || "") }),
      ])
    );
  }
  view.append(relSec);
}
