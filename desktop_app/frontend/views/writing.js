import { getJSON, postJSON, pollJob } from "/assets/api.js";
import { el, clear, loading, errorState } from "/assets/ui.js";
import { t } from "/assets/i18n.js";

export async function render(view) {
  clear(view);
  view.append(el("h2", { text: t("writing.title") }));
  view.append(checkSection());
  const angles = el("div", { class: "section" }, [el("h3", { text: t("writing.angles_title") }), el("p", { class: "muted", text: t("common.loading") })]);
  view.append(angles);
  loadAngles(angles);
  view.append(draftSection());
}

function checkSection() {
  const box = el("div", { class: "card-box section" }, [el("h3", { text: t("writing.check_title") })]);
  const ta = el("textarea", { class: "search", rows: "5", placeholder: t("writing.check_placeholder") });
  const out = el("div", { class: "section" });
  const btn = el("button", { text: t("writing.btn_check") });
  btn.addEventListener("click", async () => {
    clear(out);
    try {
      const r = await postJSON("/writing/check", { draft: ta.value });
      const passed = r.citation && r.citation.passed;
      out.append(el("p", { class: passed ? "muted" : "error", text: t("writing.citation_prefix") + (passed ? t("writing.citation_pass") : t("writing.citation_fail")) }));
      const warnings = (r.style && r.style.warnings) || [];
      if (warnings.length === 0) {
        out.append(el("p", { class: "muted", text: t("writing.style_ok") }));
      } else {
        const ul = el("ul");
        for (const w of warnings) ul.append(el("li", { text: typeof w === "string" ? w : JSON.stringify(w) }));
        out.append(el("p", { text: t("writing.style_warn_prefix") }), ul);
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
  container.append(el("h3", { text: t("writing.angles_title") }));
  const tension = a.tension || [];
  const gaps = a.gaps || [];
  const synthesis = a.synthesis || [];
  if (tension.length + gaps.length + synthesis.length === 0) {
    container.append(el("p", { class: "muted", text: t("writing.no_angles") }));
    return;
  }
  // 张力:前台用标题(去S化);点击填入"共享概念",不是论文号
  const tt = (pid) => {
    const s = titles[pid] || pid || "";
    return s.length > 44 ? s.slice(0, 44) + "…" : s;
  };
  const sharedWords = (tn) => {
    const sh = tn.shared || {};
    return [...(sh.topic || []), ...(sh.method || [])];
  };
  container.append(angleGroup(t("writing.tension_title"), tension,
    (tn) => `${tt(tn.a)} ↔ ${tt(tn.b)}` + (sharedWords(tn).length
      ? ` · ${t("writing.shared_prefix")}${sharedWords(tn).slice(0, 3).join(t("map.enum_comma"))}` : (tn.why ? ` : ${tn.why}` : "")),
    (tn) => sharedWords(tn).slice(0, 2).join(" + ")));
  container.append(angleGroup(t("writing.gaps_title"), gaps,
    (g) => `${g.concept || ""}${t("writing.gap_format", { score: g.gap_score != null ? g.gap_score : "?", n: g.n_central != null ? g.n_central : "?" })}`,
    (g) => g.concept || ""));
  container.append(angleGroup(t("writing.synthesis_title"), synthesis,
    (s) => `${s.concept || ""}${t("writing.synthesis_format", { complements: s.n_complements != null ? s.n_complements : "?", n: s.n_central != null ? s.n_central : "?" })}`,
    (s) => s.concept || ""));
}

let topicInputRef = null; // 出稿主题输入框(draftSection 设;角度点击填入用)

function angleGroup(title, items, fmt, topicOf) {
  const sec = el("div", { class: "section" }, [el("h3", { text: `${title} (${items.length})` })]);
  if (items.length === 0) { sec.append(el("p", { class: "muted", text: t("writing.none") })); return sec; }
  for (const it of items.slice(0, 50)) {
    const row = el("div", { class: "atom angle-row", text: fmt(it), title: t("writing.angle_click_hint") });
    row.addEventListener("click", () => {
      const topicStr = topicOf ? topicOf(it) : "";
      if (!topicStr || !topicInputRef) return;
      topicInputRef.value = topicStr;
      topicInputRef.scrollIntoView({ behavior: "smooth", block: "center" });
      topicInputRef.focus();
    });
    sec.append(row);
  }
  return sec;
}

function draftSection() {
  const box = el("div", { class: "card-box section" }, [el("h3", { text: t("writing.draft_title") })]);
  box.append(el("p", { class: "muted", text: t("writing.draft_hint") }));
  const topic = el("input", { class: "search", placeholder: t("writing.topic_placeholder") });
  topicInputRef = topic; // 角度点击填入的落点
  const papers = el("input", { class: "search", placeholder: t("writing.papers_placeholder") });
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
        el("p", { text: t("writing.seed_info", { n: seed.length }) }),
      ]);
      box.append(seedInfo);
      // 编号是后台对应,屏上把标题列给用户看(拉不到标题就保持原样)
      getJSON("/library/papers").then((lib) => {
        const titleMap = Object.fromEntries((lib.papers || []).map((p) => [p.paper_id, p.title || ""]));
        for (const id of seed.slice(0, 6)) {
          seedInfo.append(el("p", { class: "pmeta", text: "· " + ((titleMap[id] || id).slice(0, 70)) }));
        }
        if (seed.length > 6) seedInfo.append(el("p", { class: "pmeta", text: t("writing.seed_more", { n: seed.length }) }));
      }).catch(() => { /* 标题列表是锦上添花 */ });
    }
  } catch (err) { /* sessionStorage 不可用:跳过种子 */ }
  const status = el("div", { class: "section" });
  const btn = el("button", { text: t("writing.btn_draft") });
  btn.addEventListener("click", async () => {
    const paper_ids = papers.value.split(",").map((s) => s.trim()).filter(Boolean);
    clear(status);
    if (paper_ids.length === 0) { status.append(el("p", { class: "error", text: t("writing.error_no_paper") })); return; }
    btn.disabled = true; status.append(el("p", { class: "muted", text: t("writing.submitting") }));
    try {
      const { job_id } = await postJSON("/writing/draft", { topic: topic.value.trim(), paper_ids, section_count: 1, word_target: 300 });
      const job = await pollJob(job_id, {
        hashPrefix: "#/writing",
        onTick: (j) => {
          clear(status);
          status.append(el("p", { class: "muted", text: (j.progress || []).slice(-1)[0] || t("writing.running") }));
        },
      });
      if (job.status === "succeeded") {
        const r = job.result || {};
        status.append(el("p", { class: "muted", text: t("writing.draft_status", { status: r.status || "", rounds: r.rounds || 0 }) }));
        const copyBtn = el("button", { text: t("writing.btn_copy") });
        copyBtn.addEventListener("click", async () => {
          try {
            await navigator.clipboard.writeText(r.draft_text || "");
            copyBtn.textContent = t("writing.btn_copy_done");
            setTimeout(() => { copyBtn.textContent = t("writing.btn_copy"); }, 1500);
          } catch (err) { copyBtn.textContent = t("writing.btn_copy_fail"); }
        });
        status.append(copyBtn);
        status.append(el("pre", { class: "card-box", text: r.draft_text || t("writing.draft_empty") }));
        return;
      }
      if (job.status === "failed") { status.append(el("p", { class: "error", text: t("writing.fail_prefix") + (job.error || "") })); return; }
      if (job.status === "timeout") status.append(el("p", { class: "error", text: t("writing.timeout", { job_id }) }));
    } catch (err) { errorState(status, err.message, null); }
    finally { btn.disabled = false; }
  });
  box.append(el("div", { class: "section" }, [topic]), el("div", { class: "section" }, [papers]), btn, status);
  return box;
}
