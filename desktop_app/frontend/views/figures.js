import { getJSON } from "/assets/api.js";
import { el, clear, loading, empty, errorState } from "/assets/ui.js";

// 图表墙(SP-Map §4b):按论文浏览 Docling 已抽取的图片;零 AI。
// 路由:#/figures(空选)、#/figures/<paper_id> 或 #/figures?paper=<paper_id> 直达某篇。
// 首版策略:不逐篇探测有无图(每篇一次请求太重);列表全量展示,
// 选中论文后才拉 GET /papers/<id>/figures;无图的选中后给明确提示。

export async function render(view, params) {
  loading(view);
  let papers;
  try {
    papers = (await getJSON("/library/papers")).papers || [];
  } catch (err) {
    return errorState(view, err.message, () => render(view, params));
  }
  clear(view);
  if (papers.length === 0) return empty(view, "藏书为空 —— 先到「导入」页导入论文。");

  const byId = Object.fromEntries(papers.map((p) => [p.paper_id, p]));
  let current = null; // 当前选中的 paper_id
  let seq = 0;        // 防止快速连点时旧响应覆盖新选择

  view.append(
    el("h2", { text: "图表墙" }),
    el("p", { class: "muted", text: "左侧选一篇论文,右侧浏览它已抽取的图片;点缩略图看大图(←/→ 切换,Esc 或点遮罩关闭)。" })
  );

  // ---- 骨架:左 论文列表 / 右 缩略图区(复用要素屏的两栏 class,不改 styles.css)----
  const layout = el("div", { class: "elements-layout" });
  const side = el("div", { class: "facet-tree card-box", style: "flex-basis:280px;" });
  const gridWrap = el("div", { class: "elements-results" });
  layout.append(side, gridWrap);
  view.append(layout);

  const searchBox = el("input", { class: "search", placeholder: "搜索标题 / 编号…", style: "max-width:none;" });
  const list = el("div");
  side.append(searchBox, list);
  searchBox.addEventListener("input", () => drawList(searchBox.value));

  function drawList(filter) {
    clear(list);
    const f = (filter || "").toLowerCase();
    const rows = papers.filter(
      (p) => !f || (p.title || "").toLowerCase().includes(f) || (p.paper_id || "").toLowerCase().includes(f)
    );
    if (rows.length === 0) { list.append(el("p", { class: "muted", text: "无匹配" })); return; }
    for (const p of rows) {
      const row = el("div", {
        class: "paper-row",
        style: "cursor:pointer;" + (p.paper_id === current ? "background:#ddf4ff;" : ""),
      }, [
        el("span", { class: "ptitle", text: p.title || p.paper_id }),
        el("span", { class: "pmeta", text: [p.year, p.journal].filter(Boolean).join(" · ") }),
      ]);
      row.addEventListener("click", () => select(p.paper_id));
      list.append(row);
    }
  }

  async function select(id) {
    current = id;
    // 让 URL 可直达可分享,但不触发 hashchange 重渲染(replaceState 不发事件)
    history.replaceState(null, "", "#/figures/" + encodeURIComponent(id));
    drawList(searchBox.value);
    const mySeq = ++seq;
    loading(gridWrap);
    let data;
    try {
      data = await getJSON("/papers/" + encodeURIComponent(id) + "/figures");
    } catch (err) {
      if (mySeq !== seq) return;
      if (err.code === 404) return errorState(gridWrap, "未找到论文 " + id, null);
      return errorState(gridWrap, err.message, () => select(id));
    }
    if (mySeq !== seq) return;
    drawGrid(id, data.figures || []);
  }

  function drawGrid(id, figures) {
    clear(gridWrap);
    const p = byId[id] || {};
    gridWrap.append(
      el("h3", { style: "margin:0 0 4px;", text: p.title || id }),
      el("p", { class: "pmeta", style: "margin:0 0 12px;" }, [
        [p.year, p.journal].filter(Boolean).join(" · ") + (figures.length ? ` · 共 ${figures.length} 张图片 · ` : " · "),
        el("a", { class: "back", href: "#/papers/" + encodeURIComponent(id) }, "查看论文 ↗"),
      ])
    );
    if (figures.length === 0) {
      gridWrap.append(el("p", { class: "muted", text: "该篇无已抽取图片(library/<id>/figures/ 目录为空或不存在)。" }));
      return;
    }
    const grid = el("div", { style: "display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px;" });
    figures.forEach((name, i) => {
      const img = el("img", {
        src: figURL(id, name),
        loading: "lazy",
        alt: name,
        style: "width:100%;height:140px;object-fit:contain;background:#fff;display:block;",
      });
      const cell = el("div", { class: "card-box", style: "padding:8px;cursor:zoom-in;" }, [
        img,
        el("div", {
          class: "pmeta",
          style: "margin-top:6px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;",
          title: name,
          text: name,
        }),
      ]);
      img.addEventListener("error", () => {
        img.style.display = "none";
        if (!cell.querySelector(".error")) cell.prepend(el("p", { class: "error", style: "margin:0;", text: "图片加载失败" }));
      });
      cell.addEventListener("click", () => openLightbox(id, figures, i));
      grid.append(cell);
    });
    gridWrap.append(grid);
  }

  drawList("");
  const want = requestedPaperId(params);
  if (want && byId[want]) select(want);
  else empty(gridWrap, "从左侧选择一篇论文,查看其已抽取图片。");
}

// 直达参数,两种形态都认(读不出就返回 null,由调用方忽略):
//   #/figures?paper=S01  —— query 形(需 app.js 路由把 ? 后缀剥掉才会派发到本视图)
//   #/figures/S01        —— 路径形(现有 parseHash 原生支持,params[0] 即 id)
function requestedPaperId(params) {
  try {
    const q = (location.hash || "").match(/[?&]paper=([^&]+)/);
    if (q) return decodeURIComponent(q[1]);
    if (params && params.length) return decodeURIComponent(String(params[0]).split("?")[0]);
  } catch (err) { /* 编码非法等:忽略参数 */ }
  return null;
}

function figURL(id, name) {
  return "/papers/" + encodeURIComponent(id) + "/figures/" + encodeURIComponent(name);
}

// 全屏 lightbox:半透明遮罩 + 大图 + 左右切换(循环);Esc / 点遮罩关闭;
// 切路由(hashchange)时也自动关闭,避免遮罩残留在别的页面上。
// 导出共用(Wave-3 ②):地图论文卡前 3 张缩略图、论文详情页画廊都用它看大图。
export function openLightbox(paperId, figures, startIndex) {
  let i = startIndex;
  const img = el("img", {
    style: "max-width:92vw;max-height:84vh;background:#fff;box-shadow:0 4px 24px rgba(0,0,0,.5);cursor:default;",
  });
  const caption = el("div", { style: "color:#fff;margin-top:10px;font-size:13px;text-align:center;" });
  const stage = el("div", { style: "display:flex;flex-direction:column;align-items:center;" }, [img, caption]);

  const btnStyle = "position:absolute;top:50%;transform:translateY(-50%);font-size:28px;line-height:1;" +
    "background:rgba(255,255,255,.18);color:#fff;border:none;border-radius:6px;padding:10px 16px;cursor:pointer;";
  const prev = el("button", { style: btnStyle + "left:16px;", text: "‹" });
  const next = el("button", { style: btnStyle + "right:16px;", text: "›" });

  const overlay = el("div", {
    style: "position:fixed;inset:0;z-index:1000;background:rgba(0,0,0,.78);" +
      "display:flex;align-items:center;justify-content:center;cursor:zoom-out;",
  }, [stage, prev, next]);

  function show(n) {
    i = (n + figures.length) % figures.length;
    img.setAttribute("src", figURL(paperId, figures[i]));
    img.setAttribute("alt", figures[i]);
    caption.textContent = figures[i] + " (" + (i + 1) + "/" + figures.length + ")";
  }
  function close() {
    document.removeEventListener("keydown", onKey);
    window.removeEventListener("hashchange", close);
    overlay.remove();
  }
  function onKey(e) {
    if (e.key === "Escape") close();
    else if (e.key === "ArrowLeft") show(i - 1);
    else if (e.key === "ArrowRight") show(i + 1);
  }

  stage.addEventListener("click", (e) => e.stopPropagation());
  prev.addEventListener("click", (e) => { e.stopPropagation(); show(i - 1); });
  next.addEventListener("click", (e) => { e.stopPropagation(); show(i + 1); });
  overlay.addEventListener("click", close);
  document.addEventListener("keydown", onKey);
  window.addEventListener("hashchange", close);
  if (figures.length <= 1) { prev.style.display = "none"; next.style.display = "none"; }

  show(i);
  document.body.append(overlay);
}
