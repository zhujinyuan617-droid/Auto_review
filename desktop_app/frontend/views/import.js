import { getJSON, postJSON, pollJob } from "/assets/api.js";
import { el, clear, errorState } from "/assets/ui.js";
import { t } from "/assets/i18n.js";

export async function render(view) {
  clear(view);
  view.append(el("h2", { text: t("nav.import") }));
  view.append(searchSection());
  view.append(pdfSection());
  view.append(risSection());
}


function pdfSection() {
  const box = el("div", { class: "card-box section" }, [el("h3", { text: t("import.pdf_title") })]);
  box.append(el("p", { class: "muted", text: t("import.pdf_hint") }));
  const input = el("textarea", {
    class: "search", rows: "3",
    placeholder: t("import.pdf_placeholder"),
  });
  const status = el("div", { class: "section" });
  const btn = el("button", { text: t("import.btn_import") });
  btn.addEventListener("click", async () => {
    const paths = input.value.split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
    if (!paths.length) { clear(status); status.append(el("p", { class: "error", text: t("import.error_no_path") })); return; }
    btn.disabled = true;
    clear(status);
    // 同一次提交共用一个批次号 → 后端登记真实批次,地图"新着陆"按它识别
    const batchId = "b" + Date.now().toString(36);
    const finals = await Promise.all(paths.map(async (path) => {
      const name = path.split(/[\\/]/).pop() || path;
      const inner = el("div", {}, [el("p", { class: "muted", text: t("import.submitting") })]);
      status.append(el("div", { class: "atom" }, [el("div", {}, [el("strong", { text: name })]), inner]));
      try {
        const { job_id } = await postJSON("/papers/import", { pdf_path: path, batch_id: batchId });
        return await pollImportJob(job_id, inner);
      } catch (err) {
        errorState(inner, err.message, null);
        return "failed";
      }
    }));
    btn.disabled = false;
    const ok = finals.filter((s) => s === "succeeded").length;
    const detached = finals.includes("detached"); // 用户已离屏:不跳转不报错,着陆卡兜底
    if (ok > 0 && location.hash.startsWith("#/import")) {
      try { sessionStorage.setItem("arriveAfterImport", "1"); } catch (err) { /* 私隐模式:跳过自动着陆 */ }
      status.append(el("p", {}, [el("strong", { text: t("import.batch_done", { ok, total: paths.length }) })]));
      setTimeout(() => { if (location.hash.startsWith("#/import")) location.hash = "#/map"; }, 1000);
    } else if (!detached && ok === 0) {
      status.append(el("p", { class: "error", text: t("import.batch_fail") }));
    }
  });
  box.append(input, btn, status);
  return box;
}

// 轮询到终态(共享 pollJob:离开导入屏即静默停,任务在服务端继续,地图着陆卡兜底)。
async function pollImportJob(jobId, status) {
  const job = await pollJob(jobId, {
    hashPrefix: "#/import", maxTicks: 600,
    onTick: (j) => {
      clear(status);
      status.append(el("p", { class: "muted", text: (j.progress || []).join(" → ") || t("import.running") }));
    },
  });
  if (job.status === "succeeded") {
    status.append(el("p", {}, [t("import.job_done_prefix") + " ", el("strong", { text: String(job.result) }), " ",
      el("a", { href: "#/papers/" + job.result }, t("import.btn_view"))]));
    return "succeeded";
  }
  if (job.status === "failed") {
    status.append(el("p", { class: "error", text: t("import.job_failed_prefix") + (job.error || t("import.unknown_error")) }));
    return "failed";
  }
  if (job.status === "detached") return "detached";
  status.append(el("p", { class: "error", text: t("import.job_timeout", { id: jobId }) }));
  return "timeout";
}

function searchSection() {
  const box = el("div", { class: "card-box section" }, [el("h3", { text: t("import.search_title") })]);
  const input = el("input", { class: "search", placeholder: t("import.search_placeholder") });
  const out = el("div", { class: "section" });
  const btn = el("button", { text: t("import.btn_search") });
  btn.addEventListener("click", async () => {
    const q = input.value.trim();
    clear(out);
    if (!q) { out.append(el("p", { class: "error", text: t("import.error_no_query") })); return; }
    out.append(el("p", { class: "muted", text: t("import.searching") }));
    try {
      const { records } = await postJSON("/discovery/search", { query: q });
      clear(out);
      if (!records.length) { out.append(el("p", { class: "muted", text: t("import.no_results") })); return; }
      out.append(el("p", { class: "muted", text: t("import.result_count", { n: records.length }) }));
      for (const r of records) {
        out.append(el("div", { class: "atom" }, [
          el("div", { text: r.title || t("import.no_title") }),
          el("div", { class: "quote", text: [r.year, r.journal, r.doi].filter(Boolean).join(" · ") }),
        ]));
      }
    } catch (err) {
      clear(out);
      errorState(out, err.code === 503 ? t("import.search_unavailable") : err.message, null);
    }
  });
  box.append(input, btn, out);
  return box;
}

function risSection() {
  const box = el("div", { class: "card-box section" }, [el("h3", { text: t("import.ris_title") })]);
  const ta = el("textarea", { class: "search", rows: "6", placeholder: t("import.ris_placeholder") });
  const out = el("div", { class: "section" });
  const btn = el("button", { text: t("import.btn_parse") });
  btn.addEventListener("click", async () => {
    clear(out);
    try {
      const { records } = await postJSON("/discovery/import-ris", { text: ta.value });
      if (!records.length) { out.append(el("p", { class: "muted", text: t("import.ris_no_records") })); return; }
      out.append(el("p", { class: "muted", text: t("import.ris_count", { n: records.length }) }));
      for (const r of records) {
        out.append(el("div", { class: "atom" }, [
          el("div", { text: r.title || t("import.no_title") }),
          el("div", { class: "quote", text: [r.year, r.journal, r.doi].filter(Boolean).join(" · ") }),
        ]));
      }
    } catch (err) { errorState(out, err.message, null); }
  });
  box.append(ta, btn, out);
  return box;
}
