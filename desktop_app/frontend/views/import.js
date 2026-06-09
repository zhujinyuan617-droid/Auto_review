import { getJSON, postJSON } from "/assets/api.js";
import { el, clear, errorState } from "/assets/ui.js";

export async function render(view) {
  clear(view);
  view.append(el("h2", { text: "导入" }));
  view.append(searchSection());
  view.append(pdfSection());
  view.append(risSection());
}

function sleep(ms) { return new Promise((resolve) => setTimeout(resolve, ms)); }

function pdfSection() {
  const box = el("div", { class: "card-box section" }, [el("h3", { text: "导入 PDF" })]);
  box.append(el("p", { class: "muted", text: "暂不支持中文 PDF —— 会导入失败(ISSUES I17)。" }));
  const input = el("input", { class: "search", placeholder: "PDF 完整路径,如 D:\\\\papers\\\\x.pdf" });
  const status = el("div", { class: "section" });
  const btn = el("button", { text: "开始导入" });
  btn.addEventListener("click", async () => {
    const path = input.value.trim();
    if (!path) { clear(status); status.append(el("p", { class: "error", text: "请先填 PDF 路径" })); return; }
    btn.disabled = true;
    clear(status);
    status.append(el("p", { class: "muted", text: "提交中…" }));
    try {
      const { job_id } = await postJSON("/papers/import", { pdf_path: path });
      await pollJob(job_id, status);
    } catch (err) {
      errorState(status, err.message, null);
    } finally {
      btn.disabled = false;
    }
  });
  box.append(input, btn, status);
  return box;
}

async function pollJob(jobId, status) {
  for (let i = 0; i < 600; i++) {
    const job = await getJSON("/jobs/" + jobId);
    clear(status);
    status.append(el("p", { class: "muted", text: (job.progress || []).join(" → ") || "运行中…" }));
    if (job.status === "succeeded") {
      status.append(el("p", {}, ["完成,论文号 ", el("strong", { text: String(job.result) }), " ",
        el("a", { href: "#/papers/" + job.result }, "查看")]));
      return;
    }
    if (job.status === "failed") {
      status.append(el("p", { class: "error", text: "失败:" + (job.error || "未知错误") }));
      return;
    }
    await sleep(1000);
  }
  status.append(el("p", { class: "error", text: "超时,仍在运行 —— 稍后到藏书查看。" }));
}

function searchSection() {
  const box = el("div", { class: "card-box section" }, [el("h3", { text: "在线检索(Crossref)" })]);
  const input = el("input", { class: "search", placeholder: "输入关键词检索 Crossref…" });
  const out = el("div", { class: "section" });
  const btn = el("button", { text: "搜索" });
  btn.addEventListener("click", async () => {
    const q = input.value.trim();
    clear(out);
    if (!q) { out.append(el("p", { class: "error", text: "请输入关键词" })); return; }
    out.append(el("p", { class: "muted", text: "检索中…" }));
    try {
      const { records } = await postJSON("/discovery/search", { query: q });
      clear(out);
      if (!records.length) { out.append(el("p", { class: "muted", text: "无结果" })); return; }
      out.append(el("p", { class: "muted", text: `${records.length} 条结果` }));
      for (const r of records) {
        out.append(el("div", { class: "atom" }, [
          el("div", { text: r.title || "(无标题)" }),
          el("div", { class: "quote", text: [r.year, r.journal, r.doi].filter(Boolean).join(" · ") }),
        ]));
      }
    } catch (err) {
      clear(out);
      errorState(out, err.code === 503 ? "检索未接通" : err.message, null);
    }
  });
  box.append(input, btn, out);
  return box;
}

function risSection() {
  const box = el("div", { class: "card-box section" }, [el("h3", { text: "粘贴 RIS(取 DOI)" })]);
  const ta = el("textarea", { class: "search", rows: "6", placeholder: "粘贴 .ris 文本…" });
  const out = el("div", { class: "section" });
  const btn = el("button", { text: "解析" });
  btn.addEventListener("click", async () => {
    clear(out);
    try {
      const { records } = await postJSON("/discovery/import-ris", { text: ta.value });
      if (!records.length) { out.append(el("p", { class: "muted", text: "没解析到条目" })); return; }
      out.append(el("p", { class: "muted", text: `解析到 ${records.length} 条` }));
      for (const r of records) {
        out.append(el("div", { class: "atom" }, [
          el("div", { text: r.title || "(无标题)" }),
          el("div", { class: "quote", text: [r.year, r.journal, r.doi].filter(Boolean).join(" · ") }),
        ]));
      }
    } catch (err) { errorState(out, err.message, null); }
  });
  box.append(ta, btn, out);
  return box;
}
