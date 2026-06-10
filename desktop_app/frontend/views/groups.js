import { getJSON, postJSON, pollJob } from "/assets/api.js";
import { el, clear, loading, errorState } from "/assets/ui.js";

export async function render(view) {
  loading(view);
  let data;
  try { data = await getJSON("/groups"); }
  catch (err) { return errorState(view, err.message, () => render(view)); }
  const groups = data.groups || [];
  clear(view);
  view.append(el("h2", { text: `课题组 (${groups.length})` }));
  if (groups.length === 0) {
    view.append(el("p", { class: "muted", text: "作者库未建立 —— 点下方按钮用 Crossref 按 DOI 拉取作者(需联网,254 篇约数分钟)。" }));
    const btn = el("button", { text: "建立作者库(Crossref)" });
    const status = el("div", { class: "section" });
    btn.addEventListener("click", async () => {
      btn.disabled = true; clear(status); status.append(el("p", { class: "muted", text: "提交中…" }));
      try {
        const { job_id } = await postJSON("/groups/build", {});
        const job = await pollJob(job_id, {
          hashPrefix: "#/groups", maxTicks: 1200,
          onTick: (j) => {
            clear(status);
            status.append(el("p", { class: "muted", text: (j.progress || []).slice(-1)[0] || "运行中…" }));
          },
        });
        // 仍在本屏才允许重画;离屏(detached)则静默——任务在服务端继续
        if (job.status === "succeeded" && location.hash.startsWith("#/groups")) { render(view); return; }
        if (job.status === "failed") status.append(el("p", { class: "error", text: "失败:" + (job.error || "") }));
        if (job.status === "timeout") status.append(el("p", { class: "error", text: "超时(任务仍在后台,job " + job_id + ")" }));
      } catch (err) { errorState(status, err.message, null); }
      finally { btn.disabled = false; }
    });
    view.append(btn, status);
    return;
  }
  for (const g of groups) {
    const box = el("div", { class: "card-box section" }, [
      el("h3", { text: `${g.anchor_name || g.anchor_identity || "?"} · ${g.size} 篇` }),
    ]);
    const list = el("div", { class: "paper-list" });
    for (const p of g.papers || []) {
      list.append(el("a", { class: "paper-row", href: "#/papers/" + p.paper_id }, [
        el("span", { class: "ptitle", text: p.title || p.paper_id }),
      ]));
    }
    box.append(list);
    view.append(box);
  }
}
