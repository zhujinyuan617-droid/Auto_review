import { getJSON } from "/assets/api.js";
import { el, clear, loading, empty, errorState } from "/assets/ui.js";
import { t } from "/assets/i18n.js";

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
  view.append(el("h2", { text: t("network.title", { n: data.n_edges || edges.length }) }));

  if (edges.length === 0) {
    return empty(view, t("network.no_data"));
  }

  const counts = data.relation_counts || {};
  const types = Object.keys(counts);
  const summary = el("p", { class: "muted", text: types.map((rel) => `${rel}:${counts[rel]}`).join("  ·  ") });
  view.append(summary);

  const select = el("select", { class: "search" });
  select.append(el("option", { value: "" }, t("network.all_relations")));
  for (const rel of types) select.append(el("option", { value: rel }, rel));

  const list = el("div", { class: "paper-list" });
  function draw(filter) {
    clear(list);
    const rows = edges.filter((e) => !filter || e.relation === filter);
    if (rows.length === 0) { list.append(el("p", { class: "muted", text: t("network.no_match") })); return; }
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
    if (rows.length > 500) list.append(el("p", { class: "muted", text: t("network.truncated", { n: rows.length }) }));
  }
  select.addEventListener("change", () => draw(select.value));
  view.append(select, list);
  draw("");
}
