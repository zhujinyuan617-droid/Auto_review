import { getJSON } from "/assets/api.js";
import { el, clear, loading, empty, errorState } from "/assets/ui.js";

export async function render(view) {
  loading(view);
  let data;
  try {
    data = await getJSON("/network");
  } catch (err) {
    return errorState(view, err.message, () => render(view));
  }
  const edges = data.edges || [];
  clear(view);
  view.append(el("h2", { text: `关系网 (${data.n_edges || edges.length} 条边)` }));

  if (edges.length === 0) {
    return empty(view, "关系数据未配置 —— 启动时未找到 edges.json(见设计文档配置接线)。");
  }

  const counts = data.relation_counts || {};
  const types = Object.keys(counts);
  const summary = el("p", { class: "muted", text: types.map((t) => `${t}:${counts[t]}`).join("  ·  ") });
  view.append(summary);

  const select = el("select", { class: "search" });
  select.append(el("option", { value: "" }, "全部关系"));
  for (const t of types) select.append(el("option", { value: t }, t));

  const list = el("div", { class: "paper-list" });
  function draw(filter) {
    clear(list);
    const rows = edges.filter((e) => !filter || e.relation === filter);
    if (rows.length === 0) { list.append(el("p", { class: "muted", text: "无匹配" })); return; }
    for (const e of rows.slice(0, 500)) {
      list.append(
        el("div", { class: "atom" }, [
          el("div", {}, [
            el("a", { href: "#/papers/" + e.a }, e.a), " — ",
            el("strong", { text: e.relation || "?" }), " — ",
            el("a", { href: "#/papers/" + e.b }, e.b),
          ]),
          e.rationale ? el("div", { class: "quote", text: e.rationale }) : null,
        ])
      );
    }
    if (rows.length > 500) list.append(el("p", { class: "muted", text: `仅显示前 500 / 共 ${rows.length} 条` }));
  }
  select.addEventListener("change", () => draw(select.value));
  view.append(select, list);
  draw("");
}
