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
  let a, titles = {};
  try {
    const [resp, lib] = await Promise.all([
      getJSON("/writing/angles"),
      getJSON("/library/papers").catch(() => ({ papers: [] })),
    ]);
    a = resp;
    titles = Object.fromEntries((lib.papers || []).map((p) => [p.paper_id, p.title || ""]));
  } catch (err) { return errorState(container, err.message, () => loadAngles(container)); }
  clear(container);
  container.append(el("h3", { text: "候选角度" }));
  const tension = a.tension || [];
  const gaps = a.gaps || [];
  const synthesis = a.synthesis || [];
  if (tension.length + gaps.length + synthesis.length === 0) {
    container.append(el("p", { class: "muted", text: "无候选 —— 关系/概念数据未配置或为空。" }));
    return;
  }
  // 张力:前台用标题(去S化);点击填入"共享概念",不是论文号
  const tt = (pid) => {
    const s = titles[pid] || pid || "";
    return s.length > 44 ? s.slice(0, 44) + "…" : s;
  };
  const sharedWords = (t) => {
    const sh = t.shared || {};
    return [...(sh.topic || []), ...(sh.method || [])];
  };
  container.append(angleGroup("张力(可能的矛盾)", tension,
    (t) => `${tt(t.a)} ↔ ${tt(t.b)}` + (sharedWords(t).length
      ? ` · 共享:${sharedWords(t).slice(0, 3).join("、")}` : (t.why ? ` : ${t.why}` : "")),
    (t) => sharedWords(t).slice(0, 2).join(" + ")));
  container.append(angleGroup("空白(概念覆盖薄)", gaps,
    (g) => `${g.concept || ""}(gap ${g.gap_score != null ? g.gap_score : "?"} · 核心 ${g.n_central != null ? g.n_central : "?"} 篇)`,
    (g) => g.concept || ""));
  container.append(angleGroup("综合(可整合)", synthesis,
    (s) => `${s.concept || ""}(互补 ${s.n_complements != null ? s.n_complements : "?"} 条 · 核心 ${s.n_central != null ? s.n_central : "?"} 篇)`,
    (s) => s.concept || ""));
}

let topicInputRef = null; // 出稿主题输入框(draftSection 设;角度点击填入用)

function angleGroup(title, items, fmt, topicOf) {
  const sec = el("div", { class: "section" }, [el("h3", { text: `${title} (${items.length})` })]);
  if (items.length === 0) { sec.append(el("p", { class: "muted", text: "无" })); return sec; }
  for (const it of items.slice(0, 50)) {
    const row = el("div", { class: "atom angle-row", text: fmt(it), title: "点击把这个角度填入下方出稿主题" });
    row.addEventListener("click", () => {
      const t = topicOf ? topicOf(it) : "";
      if (!t || !topicInputRef) return;
      topicInputRef.value = t;
      topicInputRef.scrollIntoView({ behavior: "smooth", block: "center" });
      topicInputRef.focus();
    });
    sec.append(row);
  }
  return sec;
}

function draftSection() {
  const box = el("div", { class: "card-box section" }, [el("h3", { text: "出稿(接地草稿)" })]);
  box.append(el("p", { class: "muted", text: "用所选论文 + 连接层证据生成一节草稿。会真实调用 AI,需数十秒到数分钟。" }));
  const topic = el("input", { class: "search", placeholder: "主题,如:methane adsorption in clay nanopores" });
  topicInputRef = topic; // 角度点击填入的落点
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
      const seedInfo = el("div", { class: "muted" }, [
        el("p", { text: `已带入检索命中 ${seed.length} 篇(可删减);主题预填了所选要素,请按需要改写。` }),
      ]);
      box.append(seedInfo);
      // 编号是后台对应,屏上把标题列给用户看(拉不到标题就保持原样)
      getJSON("/library/papers").then((lib) => {
        const t = Object.fromEntries((lib.papers || []).map((p) => [p.paper_id, p.title || ""]));
        for (const id of seed.slice(0, 6)) {
          seedInfo.append(el("p", { class: "pmeta", text: "· " + ((t[id] || id).slice(0, 70)) }));
        }
        if (seed.length > 6) seedInfo.append(el("p", { class: "pmeta", text: `…等共 ${seed.length} 篇` }));
      }).catch(() => { /* 标题列表是锦上添花 */ });
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
        const copyBtn = el("button", { text: "复制全文" });
        copyBtn.addEventListener("click", async () => {
          try {
            await navigator.clipboard.writeText(r.draft_text || "");
            copyBtn.textContent = "已复制 ✓";
            setTimeout(() => { copyBtn.textContent = "复制全文"; }, 1500);
          } catch (err) { copyBtn.textContent = "复制失败(请手动选择文本)"; }
        });
        status.append(copyBtn);
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
