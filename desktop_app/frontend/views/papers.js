import { getJSON } from "/assets/api.js";
import { el, clear, loading, errorState } from "/assets/ui.js";
import { t } from "/assets/i18n.js";

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
  const btn = el("button", { text: t("map.btn_pdf"), title: t("papers.open_pdf_title") });
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
  const search = el("input", { class: "search", placeholder: t("papers.search_placeholder") });
  const sortSel = el("select", { title: t("papers.sort_title") }, [
    el("option", { value: "new", text: t("papers.sort_new") }),
    el("option", { value: "old", text: t("papers.sort_old") }),
    el("option", { value: "title", text: t("papers.sort_title_az") }),
  ]);
  const list = el("div", { class: "paper-list" });

  const isReview = (p) => /review/i.test(String(p.paper_type || ""));
  function sorted(rows) {
    const v = sortSel.value;
    const yr = (p) => { const y = parseInt(p.year, 10); return isNaN(y) ? null : y; };
    return rows.slice().sort((a, b) => {
      if (v === "title") return String(a.title || "").localeCompare(String(b.title || ""));
      const ya = yr(a), yb = yr(b);
      if (ya == null && yb == null) return String(a.title || "").localeCompare(String(b.title || ""));
      if (ya == null) return 1;  // 无年份沉底
      if (yb == null) return -1;
      return v === "new" ? yb - ya : ya - yb;
    });
  }

  function draw(filter) {
    clear(list);
    const f = (filter || "").toLowerCase();
    const rows = sorted(papers.filter(
      (p) => !f || (p.title || "").toLowerCase().includes(f) || (p.journal || "").toLowerCase().includes(f)
    ));
    if (rows.length === 0) {
      list.append(el("p", { class: "muted", text: t("papers.no_match") }));
      return;
    }
    for (const p of rows) {
      list.append(
        el("a", { class: "paper-row", href: "#/papers/" + p.paper_id }, [
          el("span", { class: "ptitle" }, [
            p.title || p.paper_id,
            isReview(p) ? el("span", { class: "tag review-tag", text: t("papers.tag_review") }) : null,
          ]),
          el("span", { class: "pmeta", text: [p.year, p.journal].filter(Boolean).join(" · ") }),
        ])
      );
    }
  }

  search.addEventListener("input", () => draw(search.value));
  sortSel.addEventListener("change", () => draw(search.value));
  view.append(
    el("h2", { text: t("papers.library_count", { n: papers.length }) }),
    el("div", { style: "display:flex;gap:8px;align-items:center;" }, [search, sortSel]),
    list
  );
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
    if (err.code === 404) return errorState(view, t("papers.not_found", { id }), null);
    return errorState(view, err.message, () => renderDetail(view, id));
  }
  clear(view);
  // 头部:标题 → 年份·期刊·DOI(可点)→ 作者/机构(authorship 上屏)→ 操作按钮
  const metaP = el("p", { class: "pmeta" }, [[p.year, p.journal].filter(Boolean).join(" · ")]);
  if (p.doi) {
    if (metaP.textContent) metaP.append(" · ");
    metaP.append(el("a", { href: "https://doi.org/" + p.doi, target: "_blank",
      rel: "noopener", text: "doi:" + p.doi, title: t("papers.doi_title") }));
  }
  view.append(
    el("a", { class: "back", href: "#/papers" }, t("papers.back_to_list")),
    el("h2", { text: p.title || p.paper_id }),
    metaP
  );
  if ((p.authors || []).length) {
    const hasSenior = p.authors.some((a) => a.is_senior);
    view.append(el("p", { class: "pmeta", text: t("map.authors_label")
      + p.authors.map((a) => a.name + (a.is_senior ? "★" : "")).join("、")
      + (hasSenior ? t("papers.senior_note") : "") }));
  }
  if ((p.institutions || []).length) {
    view.append(el("p", { class: "pmeta", text: t("map.institutions_label") + p.institutions.join(" · ") }));
  }
  const btn = el("button", { text: t("papers.btn_decompose") });
  btn.addEventListener("click", () => { location.hash = "#/papers/" + id + "/decompose"; });
  const mapBtn = el("button", { text: t("papers.btn_map"), title: t("papers.btn_map_title") });
  mapBtn.addEventListener("click", () => {
    try { sessionStorage.setItem("mapFocusPaper", id); } catch (err) { /* 隐私模式跳过 */ }
    location.hash = "#/map";
  });
  view.append(el("div", { class: "section", style: "display:flex;gap:8px;" }, [btn, pdfButton(id), mapBtn]));

  const card = el("div", { class: "card-box" });
  if (p.objective) card.append(el("div", { class: "section" }, [el("h3", { text: t("papers.section_objective") }), el("p", { text: p.objective })]));
  const findings = p.main_findings || [];
  if (findings.length) {
    const sec = el("div", { class: "section" }, [el("h3", { text: t("papers.section_findings") })]);
    const ul = el("ul");
    for (const f of findings) ul.append(el("li", { text: f }));
    sec.append(ul);
    card.append(sec);
  }
  view.append(card);

  // 研究要素(要素索引口径,与地图论文卡同一套词;未构建时退回旧卡片标签)
  const legacyRows = () => [
    tagRow(t("papers.legacy_objects"), p.research_objects),
    tagRow(t("papers.legacy_methods"), p.methods),
    tagRow(t("papers.legacy_domain"), p.domain_tags),
  ].filter(Boolean);
  try {
    const d = await getJSON("/papers/" + encodeURIComponent(id) + "/elements");
    // 与地图论文卡同口径(全库统计背书):五类不合并、同要素去重、值智能追加
    const dedupe = (items) => {
      const seen = new Set();
      return (items || []).filter((it) => {
        const k = it.element_id || it.display_name;
        if (seen.has(k)) return false;
        seen.add(k);
        return true;
      });
    };
    const names = (items) => dedupe(items).map((it) => {
      const name = it.display_name || it.element_id;
      const vals = (it.values || []).map((v) => String(v.raw || v)).filter(Boolean);
      const extra = vals.filter((v) => !name.includes(v));
      return name + (extra.length ? " = " + extra.join(" / ") : "");
    });
    const by = new Map((d.groups || []).map((g) => [g.facet, g.items || []]));
    const rows = [
      tagRow(t("facet.material"), names(by.get("material"))),
      tagRow(t("facet.simulation"), names(by.get("simulation"))),
      tagRow(t("facet.measurement"), names(by.get("measurement"))),
      tagRow(t("facet.characterization"), names(by.get("characterization"))),
      tagRow(t("facet.preparation"), names(by.get("preparation"))),
      tagRow(t("facet.analysis"), names(by.get("analysis"))),
      tagRow(t("facet.condition"), names(by.get("condition"))),
      tagRow(t("facet.topic"), names(by.get("topic"))),
    ].filter(Boolean);
    for (const r of rows.length ? rows : legacyRows()) card.append(r);
  } catch (err) {
    for (const r of legacyRows()) card.append(r);
  }

  // 图表画廊(Wave-3 ②:图表墙撤屏后的完整画廊新家);拉不到图不挡详情
  try {
    const figs = (await getJSON("/papers/" + encodeURIComponent(id) + "/figures")).figures || [];
    if (figs.length) {
      const { openLightbox } = await import("/assets/views/figures.js");
      const sec = el("div", { class: "section" }, [el("h3", { text: t("papers.figures_section", { n: figs.length }) })]);
      const grid = el("div", {
        style: "display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;",
      });
      figs.forEach((f, i) => {
        const cap = f.caption || (f.page ? t("papers.page_figure", { n: f.page }) : f.name);
        const img = el("img", {
          src: "/papers/" + encodeURIComponent(id) + "/figures/" + encodeURIComponent(f.name),
          loading: "lazy", alt: cap, title: cap,
          style: "width:100%;height:110px;object-fit:contain;background:#fff;" +
            "border:1px solid #d0d7de;border-radius:6px;cursor:zoom-in;",
        });
        img.addEventListener("error", () => img.remove());
        img.addEventListener("click", () => openLightbox(id, figs, i));
        const cell = el("div", {}, [img, el("div", {
          class: "pmeta",
          style: "display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;",
          title: cap, text: cap,
        })]);
        grid.append(cell);
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
  const a = el("a", { href: "javascript:void 0", text: t("papers.block_anchor_label"), title: t("papers.block_anchor_title") });
  const slot = el("div", { class: "block-ctx" });
  slot.hidden = true;
  let loaded = false;
  a.addEventListener("click", async () => {
    slot.hidden = !slot.hidden;
    if (loaded || slot.hidden) return;
    loaded = true;
    slot.append(el("p", { class: "muted", text: t("papers.block_loading") }));
    try {
      const d = await getJSON(`/papers/${encodeURIComponent(paperId)}/blocks/${encodeURIComponent(rbId)}`);
      clear(slot);
      slot.append(...blockContextNodes(d));
    } catch (err) {
      clear(slot);
      slot.append(el("p", { class: "error", text: err.code === 404
        ? t("papers.block_not_found") : t("papers.block_load_fail") + err.message }));
    }
  });
  wrap.append(a, slot);
  return wrap;
}

function blockContextNodes(d) {
  const b = d.block || {};
  const out = [
    el("div", { class: "pmeta", text: [b.section_title || t("papers.section_title_fallback"),
      b.page_start != null ? t("papers.page_n", { n: b.page_start }) : null].filter(Boolean).join(" · ") }),
    el("p", { text: b.text || t("papers.block_empty") }),
  ];
  if (d.next && d.next.text) {
    out.push(el("p", { class: "muted", text: t("papers.next_block_prefix") + String(d.next.text).slice(0, 140) + "…" }));
  }
  return out;
}

function atomList(title, atoms, paperId) {
  const sec = el("div", { class: "section" }, [el("h3", { text: t("papers.atom_list_head", { title, n: atoms.length }) })]);
  if (atoms.length === 0) { sec.append(el("p", { class: "muted", text: t("papers.empty") })); return sec; }
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
    if (err.code === 404) return errorState(view, t("papers.not_found", { id }), null);
    return errorState(view, err.message, () => renderDecomposition(view, id, focusBlockId));
  }
  const c = d.card || {};
  clear(view);
  // 素材来源诚实标注:elements=新链(逐字锚定要素);legacy=旧原子链
  const srcBadge = d.source
    ? el("span", {
        class: "tag",
        title: d.source === "elements" ? t("papers.src_elements_title") : t("papers.src_legacy_title"),
        text: d.source === "elements" ? t("papers.src_elements") : t("papers.src_legacy"),
      })
    : null;
  view.append(
    el("a", { class: "back", href: "#/papers/" + id }, t("papers.back_to_detail")),
    el("h2", { text: t("papers.decompose_title", { title: c.title || id }) }),
    el("div", { class: "section", style: "display:flex;gap:8px;align-items:center;" }, [pdfButton(id), srcBadge])
  );

  // 深链定位:从检索/统计的"原文段↗"跳来时,顶端直接展开该原文段
  if (focusBlockId) {
    const banner = el("div", { class: "card-box block-focus" }, [
      el("h3", { style: "margin-top:0;", text: t("papers.block_focus_title") }),
    ]);
    view.append(banner);
    getJSON(`/papers/${encodeURIComponent(id)}/blocks/${encodeURIComponent(focusBlockId)}`)
      .then((bd) => banner.append(...blockContextNodes(bd)))
      .catch((err) => banner.append(el("p", { class: "error", text: err.code === 404
        ? t("papers.block_not_found") : t("papers.block_load_fail") + err.message })));
  }

  const abstract = blockList(t("papers.section_abstract"), d.abstract_blocks);
  if (abstract) view.append(abstract);
  const intro = blockList(t("papers.section_intro"), d.intro_blocks);
  if (intro) view.append(intro);

  const glossary = d.glossary || [];
  if (glossary.length) {
    const sec = el("div", { class: "section" }, [el("h3", { text: t("papers.section_glossary") })]);
    for (const g of glossary) {
      const term = g.term || g.name || "";
      const def = g.definition || g.meaning || "";
      sec.append(el("p", {}, [el("strong", { text: term }), def ? ":" + def : ""]));
    }
    view.append(sec);
  }

  view.append(atomList(t("papers.section_analyses"), d.analyses || [], id));
  if ((d.conditions || []).length) {
    view.append(atomList(t("papers.section_conditions"), d.conditions, id));
  }
  view.append(atomList(t("papers.section_results"), d.results || [], id));

  const rel = d.result_relations || [];
  const relSec = el("div", { class: "section" }, [el("h3", { text: t("papers.section_relations", { n: rel.length }) })]);
  if (rel.length === 0) relSec.append(el("p", { class: "muted", text: t("papers.empty") }));
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
