import { getJSON, postJSON, pollJob } from "/assets/api.js";
import { el, clear, loading, errorState } from "/assets/ui.js";
import { t } from "/assets/i18n.js";

export async function render(view) {
  loading(view);
  let data;
  try { data = await getJSON("/groups"); }
  catch (err) { return errorState(view, err.message, () => render(view)); }
  const groups = data.groups || [];
  clear(view);
  view.append(el("h2", { text: t("groups.title", { n: groups.length }) }));
  if (groups.length === 0) {
    view.append(el("p", { class: "muted", text: t("groups.empty_hint") }));
    const btn = el("button", { text: t("groups.build_btn") });
    const status = el("div", { class: "section" });
    btn.addEventListener("click", async () => {
      btn.disabled = true; clear(status); status.append(el("p", { class: "muted", text: t("groups.submitting") }));
      try {
        const { job_id } = await postJSON("/groups/build", {});
        const job = await pollJob(job_id, {
          hashPrefix: "#/groups", maxTicks: 1200,
          onTick: (j) => {
            clear(status);
            status.append(el("p", { class: "muted", text: (j.progress || []).slice(-1)[0] || t("groups.running") }));
          },
        });
        // 仍在本屏才允许重画;离屏(detached)则静默——任务在服务端继续
        if (job.status === "succeeded" && location.hash.startsWith("#/groups")) { render(view); return; }
        if (job.status === "failed") status.append(el("p", { class: "error", text: t("groups.fail_prefix") + (job.error || "") }));
        if (job.status === "timeout") status.append(el("p", { class: "error", text: t("groups.timeout", { id: job_id }) }));
      } catch (err) { errorState(status, err.message, null); }
      finally { btn.disabled = false; }
    });
    view.append(btn, status);
    return;
  }
  for (const g of groups) {
    const box = el("div", { class: "card-box section" }, [
      el("h3", { text: t("groups.group_head", { name: g.anchor_name || g.anchor_identity || "?", n: g.size }) }),
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
