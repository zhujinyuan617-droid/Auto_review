import { getJSON, postJSON, pollJob } from "/assets/api.js";
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
  container.append(angleGroup("张力(可能的矛盾)", tension, (t) => `${t.a || ""} ↔ ${t.b || ""} : ${t.why || ""}`));
  container.append(angleGroup("空白(概念覆盖薄)", gaps, (g) => `${g.concept || ""}(gap ${g.gap_score != null ? g.gap_score : "?"} · 核心 ${g.n_central != null ? g.n_central : "?"} 篇)`));
  container.append(angleGroup("综合(可整合)", synthesis, (s) => `${s.concept || ""}(互补 ${s.n_complements != null ? s.n_complements : "?"} 条 · 核心 ${s.n_central != null ? s.n_central : "?"} 篇)`));
}

function angleGroup(title, items, fmt) {
  const sec = el("div", { class: "section" }, [el("h3", { text: `${title} (${items.length})` })]);
  if (items.length === 0) { sec.append(el("p", { class: "muted", text: "无" })); return sec; }
  for (const it of items.slice(0, 50)) sec.append(el("div", { class: "atom", text: fmt(it) }));
  return sec;
}

function draftSection() {
  const box = el("div", { class: "card-box section" }, [el("h3", { text: "出稿(接地草稿)" })]);
  box.append(el("p", { class: "muted", text: "用所选论文 + 连接层证据生成一节草稿。会真实调用 AI,需数十秒到数分钟。" }));
  const topic = el("input", { class: "search", placeholder: "主题,如:methane adsorption in clay nanopores" });
  const papers = el("input", { class: "search", placeholder: "论文号,逗号分隔,如 S09,S108" });
  // 检索屏「送写作」的命中集种子(Wave-3 ⑤):读后即清,预填可删减
  try {
    const seed = JSON.parse(sessionStorage.getItem("writingSeedPapers") || "null");
    sessionStorage.removeItem("writingSeedPapers");
    const seedTopic = sessionStorage.getItem("writingSeedTopic") || "";
    sessionStorage.removeItem("writingSeedTopic");
    if (Array.isArray(seed) && seed.length) {
      papers.value = seed.join(",");
      if (seedTopic) topic.value = seedTopic;
      box.append(el("p", { class: "muted",
        text: `已带入检索命中 ${seed.length} 篇(可删减);主题预填了所选要素,请按需要改写。` }));
    }
  } catch (err) { /* sessionStorage 不可用:跳过种子 */ }
  const status = el("div", { class: "section" });
  const btn = el("button", { text: "出稿" });
  btn.addEventListener("click", async () => {
    const paper_ids = papers.value.split(",").map((s) => s.trim()).filter(Boolean);
    clear(status);
    if (paper_ids.length === 0) { status.append(el("p", { class: "error", text: "请至少填一个论文号" })); return; }
    btn.disabled = true; status.append(el("p", { class: "muted", text: "提交中…" }));
    try {
      const { job_id } = await postJSON("/writing/draft", { topic: topic.value.trim(), paper_ids, section_count: 1, word_target: 300 });
      const job = await pollJob(job_id, {
        hashPrefix: "#/writing",
        onTick: (j) => {
          clear(status);
          status.append(el("p", { class: "muted", text: (j.progress || []).slice(-1)[0] || "运行中…" }));
        },
      });
      if (job.status === "succeeded") {
        const r = job.result || {};
        status.append(el("p", { class: "muted", text: `状态:${r.status || ""} · 轮数:${r.rounds || 0}` }));
        status.append(el("pre", { class: "card-box", text: r.draft_text || "(空)" }));
        return;
      }
      if (job.status === "failed") { status.append(el("p", { class: "error", text: "失败:" + (job.error || "") })); return; }
      if (job.status === "timeout") status.append(el("p", { class: "error", text: "超时(任务仍在后台,job " + job_id + ")" }));
    } catch (err) { errorState(status, err.message, null); }
    finally { btn.disabled = false; }
  });
  box.append(el("div", { class: "section" }, [topic]), el("div", { class: "section" }, [papers]), btn, status);
  return box;
}
