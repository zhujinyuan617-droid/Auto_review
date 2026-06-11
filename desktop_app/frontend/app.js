import { placeholder } from "/assets/ui.js";
import { t, applyStatic, initLang } from "/assets/i18n.js";

// Routes whose module exists. map 是首页(无 hash / #/ 时进入);network 不在导航上
// 但路由保留(书签兼容,SP-Map §5)。
const ROUTES = {
  map: () => import("/assets/views/map.js"),
  papers: () => import("/assets/views/papers.js"),
  import: () => import("/assets/views/import.js"),
  network: () => import("/assets/views/network.js"),
  writing: () => import("/assets/views/writing.js"),
  settings: () => import("/assets/views/settings.js"),
  groups: () => import("/assets/views/groups.js"),
  elements: () => import("/assets/views/elements_search.js"),
  stats: () => import("/assets/views/elements_stats.js"),
  figures: () => import("/assets/views/figures.js"),
};

function parseHash() {
  const raw = (location.hash || "#/map").replace(/^#\//, "").split("?")[0];
  const parts = raw.split("/").filter(Boolean);
  return { name: parts[0] || "map", params: parts.slice(1) };
}

function highlightNav(name) {
  document.querySelectorAll("#nav a").forEach((a) => {
    a.classList.toggle("active", a.getAttribute("href") === "#/" + name);
  });
}

let routeSeq = 0; // 防串台:慢请求的旧视图渲染返回时,若用户已切屏则丢弃结果

async function route() {
  const seq = ++routeSeq;
  const view = document.getElementById("view");
  const { name, params } = parseHash();
  highlightNav(name);
  view.className = ""; // 视图级布局类(如地图的 map-full)不得跨路由残留
  const loader = ROUTES[name];
  if (!loader) {            // nav target not built yet
    placeholder(view);
    return;
  }
  view.textContent = t("common.loading");
  try {
    const mod = await loader();
    if (seq !== routeSeq) return; // 已切去别屏,本次渲染作废
    await mod.render(view, params);
  } catch (err) {
    if (seq !== routeSeq) return;
    view.textContent = t("app.load_fail") + err.message;
  }
}

window.addEventListener("hashchange", route);
window.addEventListener("load", () => { applyStatic(); initLang(); route(); });
