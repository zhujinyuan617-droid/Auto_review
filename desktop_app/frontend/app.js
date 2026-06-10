import { placeholder } from "/assets/ui.js";

// Routes whose module exists. Later batches add import/network/groups/writing/settings.
const ROUTES = {
  papers: () => import("/assets/views/papers.js"),
  import: () => import("/assets/views/import.js"),
  network: () => import("/assets/views/network.js"),
  writing: () => import("/assets/views/writing.js"),
  settings: () => import("/assets/views/settings.js"),
  groups: () => import("/assets/views/groups.js"),
  elements: () => import("/assets/views/elements_search.js"),
  stats: () => import("/assets/views/elements_stats.js"),
};

function parseHash() {
  const raw = (location.hash || "#/papers").replace(/^#\//, "");
  const parts = raw.split("/").filter(Boolean);
  return { name: parts[0] || "papers", params: parts.slice(1) };
}

function highlightNav(name) {
  document.querySelectorAll("#nav a").forEach((a) => {
    a.classList.toggle("active", a.getAttribute("href") === "#/" + name);
  });
}

async function route() {
  const view = document.getElementById("view");
  const { name, params } = parseHash();
  highlightNav(name);
  const loader = ROUTES[name];
  if (!loader) {            // nav target not built yet
    placeholder(view);
    return;
  }
  view.textContent = "加载中…";
  try {
    const mod = await loader();
    await mod.render(view, params);
  } catch (err) {
    view.textContent = "页面加载失败:" + err.message;
  }
}

window.addEventListener("hashchange", route);
window.addEventListener("load", route);
