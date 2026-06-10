import { getJSON, postJSON, pollJob } from "/assets/api.js";
import { el, clear, errorState } from "/assets/ui.js";

export async function render(view) {
  clear(view);
  view.append(el("h2", { text: "导入" }));
  view.append(searchSection());
  view.append(pdfSection());
  view.append(risSection());
}


function pdfSection() {
  const box = el("div", { class: "card-box section" }, [el("h3", { text: "导入 PDF" })]);
  box.append(el("p", { class: "muted", text: "暂不支持中文 PDF —— 会导入失败(ISSUES I17)。一行一个完整路径,多个文件作为同一批次导入。" }));
  const input = el("textarea", {
    class: "search", rows: "3",
    placeholder: "PDF 完整路径,一行一个,如 D:\\papers\\x.pdf",
  });
  const status = el("div", { class: "section" });
  const btn = el("button", { text: "开始导入" });
  btn.addEventListener("click", async () => {
    const paths = input.value.split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
    if (!paths.length) { clear(status); status.append(el("p", { class: "error", text: "请先填 PDF 路径" })); return; }
    btn.disabled = true;
    clear(status);
    // 同一次提交共用一个批次号 → 后端登记真实批次,地图"新着陆"按它识别
    const batchId = "b" + Date.now().toString(36);
    const finals = await Promise.all(paths.map(async (path) => {
      const name = path.split(/[\\/]/).pop() || path;
      const inner = el("div", {}, [el("p", { class: "muted", text: "提交中…" })]);
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
      status.append(el("p", {}, [el("strong", { text: `本批 ${ok}/${paths.length} 篇已完成,正在打开知识地图…` })]));
      setTimeout(() => { if (location.hash.startsWith("#/import")) location.hash = "#/map"; }, 1000);
    } else if (!detached && ok === 0) {
      status.append(el("p", { class: "error", text: "本批没有成功的导入,未跳转地图。" }));
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
      status.append(el("p", { class: "muted", text: (j.progress || []).join(" → ") || "运行中…" }));
    },
  });
  if (job.status === "succeeded") {
    status.append(el("p", {}, ["完成,论文号 ", el("strong", { text: String(job.result) }), " ",
      el("a", { href: "#/papers/" + job.result }, "查看")]));
    return "succeeded";
  }
  if (job.status === "failed") {
    status.append(el("p", { class: "error", text: "失败:" + (job.error || "未知错误") }));
    return "failed";
  }
  if (job.status === "detached") return "detached";
  status.append(el("p", { class: "error", text: "超时,仍在运行 —— 稍后到藏书查看(job " + jobId + ")。" }));
  return "timeout";
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
