import { getJSON, postJSON, putJSON, pollJob } from "/assets/api.js";
import { el, clear, loading, errorState } from "/assets/ui.js";

// 知识地图首页(SP-Map §1/§2/§4 前端面)。
//
// 渲染决定:vendored 的 force-graph 是力导向「模拟」库(坐标由它自己迭代算),
// 而本视图的坐标全部来自后端 /map 的缓存布局(静态、要稳定)。261 个点的散点
// + 同区凸包,用原生 canvas 直接画最合适:零新依赖、老点位置一像素不漂。
// Wave-3 ①:布点为后端确定性径向(大区在中心、区内年轮老内新外);时间镜头退役,
// 年份信息由年轮 + 区面板「年代跨度/首现要素」承载;灰点收最外圈「待构建」区。
// 特写外环(Wave-2 起)= GET /map/neighbors 的共享要素 top-8(真口径,替换了
// 首发版"同区 size top-8"的简化方案);内环仍是 /network 的 AI 判边。

const LENS_NAMES = { topic: "主题", method: "方法", material: "材料", institution: "机构" };

// 灰点原因按镜头说人话(spec 对方法/材料镜头的原文是「该篇要素未构建」)。
const UNLIT_REASON = {
  topic: "该篇无主题标签",
  method: "该篇要素未构建",
  material: "该篇要素未构建",
  institution: "该篇机构信息未拉取",
};

// 确定性调色板:cluster 按 id 排序后轮转取色。学术系配色,与 graph.js 同风格,
// 但自带一份 —— graph.js 未入 git,不能作为依赖。
const PALETTE = [
  "#4e79a7", "#59a14f", "#b07aa1", "#e15759", "#f28e2b",
  "#76b7b2", "#9c755f", "#b5992b", "#7e8aa2", "#d3795f",
  "#6b8e5a", "#a26769",
];
const GREY = "#9aa4b2";
const ACCENT = "#0969da";
const REL_COLORS = { supports: "#2e8b6f", contradicts: "#c2502f", complements: "#3f6bb0" };
const REL_LABELS = { supports: "支持", contradicts: "矛盾", complements: "互补" };
const REL_FALLBACK = "#8a7aa8";

const STATE_KEY = "mapState";              // sessionStorage:{lens, scale, panX, panY, selectedId}
const ARRIVE_KEY = "arriveAfterImport";    // 导入闭环标志(import.js 置位,本视图读后即清)

function trunc(s, n) {
  s = String(s || "");
  return s.length > n ? s.slice(0, n) + "…" : s;
}

// 区描述(POST /map/describe)每镜头每次会话只发一次;pending 供面板显示"生成中"。
const describedLenses = new Set();
const describePending = new Set();

let teardown = null; // 上一次挂载的清理(重进/离开路由时执行,防 rAF 与监听泄漏)

export async function render(view) {
  if (teardown) { teardown(); teardown = null; }
  loading(view);

  // 状态记忆:镜头要在数据加载前生效(其余视口量等 prepareLens 后恢复)。
  let savedState = null;
  try { savedState = JSON.parse(sessionStorage.getItem(STATE_KEY) || "null"); } catch (err) { savedState = null; }
  const startLens = savedState && LENS_NAMES[savedState.lens] ? savedState.lens : "topic";

  let payload, library, coverage, arrivals;
  try {
    [payload, library, coverage, arrivals] = await Promise.all([
      getJSON(`/map?lens=${encodeURIComponent(startLens)}`).catch((err) => {
        if (startLens === "topic") throw err;
        return getJSON("/map?lens=topic"); // 记忆的镜头不可用(如要素索引被删)→ 回退主题
      }),
      getJSON("/library/papers").catch(() => ({ papers: [] })),
      getJSON("/elements/coverage").catch(() => null),
      getJSON("/map/arrivals").catch(() => ({ batch: [] })),
    ]);
  } catch (err) {
    return errorState(view, err.message, () => render(view));
  }

  const titles = {};
  for (const p of library.papers || []) titles[p.paper_id] = p;
  const batch = (arrivals && arrivals.batch) || [];

  // ---------- 状态 ----------
  const S = {
    lens: "topic",
    nodes: [],                 // {id,x,y,cluster,size,lit,r} 世界坐标 ∈ [0,1]²
    clusters: [],              // {id,label,n,color,members:[node]}
    byId: new Map(),
    clusterById: new Map(),
    hasBackendClusters: true,  // time 镜头的分带是前端合成的,无后端路线可调
    vw: { s: 1, ox: 0, oy: 0 },// world→screen: sx = ox + x*s
    fitS: 1,
    anim: null,
    dimSet: null,              // 搜索高亮:仅这些 id 保持亮,其余压暗
    selectedId: null,
    haloId: null,              // 呼吸光圈所在论文
    hover: null,               // {type:"node",node} | {type:"cluster",cluster}
    dirty: true,
    disposed: false,
    netCache: null,            // /network 响应缓存(特写用)
    regionPanel: null,         // 当前打开的区面板 {cluster, slot}(描述句异步回填用)
  };
  const neighborCache = new Map(); // `${lens}|${pid}` → /map/neighbors 结果(特写外环)

  // ---------- DOM 骨架(全屏画布 + 悬浮件) ----------
  clear(view);
  view.classList.add("map-full");
  const stage = el("div", { class: "map-stage" });
  const canvas = el("canvas", { class: "map-canvas" });

  const lensSel = el("select", { class: "map-lens", title: "切换镜头(分区依据)" });
  for (const l of payload.lenses || Object.keys(LENS_NAMES)) {
    lensSel.append(el("option", { value: l }, LENS_NAMES[l] || l));
  }
  lensSel.value = payload.lens || "topic";
  const relayoutBtn = el("button", { class: "map-btn", text: "重新布局", title: "全量重排当前镜头(老点会动)" });
  const topleft = el("div", { class: "map-overlay map-topleft" }, [lensSel, relayoutBtn]);

  const searchInput = el("input", {
    class: "map-search",
    placeholder: "搜标题关键词 / 要素名;Esc 清除",
  });
  const searchChip = el("span", { class: "map-chip", hidden: "" });
  const searchDrop = el("div", { class: "map-search-drop", hidden: "" });
  const topcenter = el("div", { class: "map-overlay map-topcenter" }, [searchInput, searchChip, searchDrop]);

  // 状态角标 = 构建入口(Wave-3 ②:统计屏撤并后,"构建要素索引"的家在地图上):
  // 缺要素 → 可点,打开一键构建面板;全量就位 → 纯展示。
  const statusBadge = el("div", { class: "map-overlay map-status" });
  const nPapers = coverage ? coverage.papers : (payload.nodes || []).length;
  if (coverage) {
    statusBadge.textContent = `${nPapers} 篇 · 要素 ${coverage.with_elements}/${coverage.papers}`;
    if (coverage.with_elements < coverage.papers) {
      statusBadge.classList.add("map-status-action");
      statusBadge.title = "有论文还没生成研究要素,点击一键补全";
      statusBadge.addEventListener("click", () =>
        showBuildPanel(coverage.papers - coverage.with_elements));
    }
  } else {
    statusBadge.textContent = `${nPapers} 篇 · 要素未构建`;
    statusBadge.classList.add("map-status-action");
    statusBadge.title = "点击构建要素索引(方法/材料镜头与检索都靠它)";
    statusBadge.addEventListener("click", () => showBuildPanel(null));
  }

  const arrivalsBadge = el("button", { class: "map-arrivals", hidden: "" });
  if (batch.length) {
    arrivalsBadge.hidden = false;
    arrivalsBadge.textContent = `${batch.length} 篇新文献着陆 →`;
  }

  const sideTitle = el("div", { class: "map-side-title" });
  const sideClose = el("button", { class: "map-side-close", text: "×", title: "关闭" });
  const sideBody = el("div", { class: "map-side-body" });
  const side = el("aside", { class: "map-side" }, [
    el("div", { class: "map-side-head" }, [sideTitle, sideClose]),
    sideBody,
  ]);

  const halo = el("div", { class: "map-halo", hidden: "" });
  const toast = el("div", { class: "map-toast", hidden: "" });
  const tooltip = el("div", { class: "map-tooltip", hidden: "" });
  const emptyMsg = el("div", { class: "map-empty", hidden: "" });
  const closeup = el("div", { class: "map-closeup", hidden: "" });

  stage.append(canvas, topleft, topcenter, statusBadge, arrivalsBadge, side, halo, emptyMsg, toast, tooltip, closeup);
  view.append(stage);

  // ---------- 画布尺寸 ----------
  const ctx = canvas.getContext("2d");
  let cssW = 0, cssH = 0;
  function resize() {
    const rect = stage.getBoundingClientRect();
    cssW = Math.max(80, rect.width);
    cssH = Math.max(80, rect.height);
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(cssW * dpr);
    canvas.height = Math.round(cssH * dpr);
    canvas.style.width = cssW + "px";
    canvas.style.height = cssH + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    S.dirty = true;
  }

  // ---------- 镜头数据准备 ----------
  function prepareLens(p) {
    S.lens = p.lens;
    S.hasBackendClusters = Array.isArray(p.clusters);
    const nodes = (p.nodes || []).map((n) => ({ ...n }));
    const clusters = (p.clusters || []).map((c) => ({ ...c }));
    clusters.slice().sort((a, b) => (String(a.id) < String(b.id) ? -1 : 1))
      .forEach((c, i) => { c.color = PALETTE[i % PALETTE.length]; });
    for (const c of clusters) c.members = [];
    const byCluster = new Map(clusters.map((c) => [c.id, c]));
    const maxSize = Math.max(1e-9, ...nodes.map((n) => n.size || 0));
    for (const n of nodes) {
      n.r = 3 + Math.sqrt(Math.max(0, n.size || 0) / maxSize) * 7;
      let c = byCluster.get(n.cluster);
      if (!c && n.cluster != null) { // payload 防御:点引用了未登记的区
        c = { id: n.cluster, label: String(n.cluster), n: 0, color: PALETTE[byCluster.size % PALETTE.length], members: [] };
        byCluster.set(n.cluster, c);
        clusters.push(c);
      }
      if (c) c.members.push(n);
    }
    for (const c of clusters) c.members.sort((a, b) => (b.size || 0) - (a.size || 0));
    // 机构镜头:洲内按机构预分组(大区套小区的"小区",画子轮廓用)
    S.instGroups = [];
    if (p.lens === "institution") {
      const by = new Map();
      for (const n of nodes) {
        if (!n.institution) continue;
        const k = n.cluster + "|" + n.institution;
        if (!by.has(k)) by.set(k, { name: n.institution, members: [] });
        by.get(k).members.push(n);
      }
      S.instGroups = [...by.values()].filter((g) => g.members.length >= 2);
    }
    S.nodes = nodes;
    S.clusters = clusters;
    S.byId = new Map(nodes.map((n) => [n.id, n]));
    S.clusterById = byCluster;
    S.dimSet = null; S.selectedId = null; S.haloId = null; S.hover = null;
    hideChip();
    emptyMsg.hidden = nodes.length > 0;
    if (!nodes.length) emptyMsg.textContent = "库为空 —— 先到「读 → 导入」添加论文。";
    fitAll(false);
    S.dirty = true;
  }

  // ---------- 视口(缩放/平移/聚焦动画) ----------
  const SX = (x) => S.vw.ox + x * S.vw.s;
  const SY = (y) => S.vw.oy + y * S.vw.s;
  const lerp = (a, b, t) => a + (b - a) * t;

  function setView(target, animate) {
    if (!animate) { S.vw = target; S.anim = null; S.dirty = true; return; }
    S.anim = { from: { ...S.vw }, to: target, t0: performance.now(), dur: 450 };
  }

  function fitAll(animate) {
    const m = 70;
    let xs = S.nodes.map((n) => n.x), ys = S.nodes.map((n) => n.y);
    if (!xs.length) { xs = [0, 1]; ys = [0, 1]; }
    const minX = Math.min(...xs), maxX = Math.max(...xs);
    const minY = Math.min(...ys), maxY = Math.max(...ys);
    const w = Math.max(0.05, maxX - minX), h = Math.max(0.05, maxY - minY);
    const s = Math.max(10, Math.min((cssW - 2 * m) / w, (cssH - 2 * m) / h)); // 窗口极小时不翻转
    S.fitS = s;
    setView({ s, ox: (cssW - s * (minX + maxX)) / 2, oy: (cssH - s * (minY + maxY)) / 2 }, animate);
  }

  function zoomAt(mx, my, f) {
    const s2 = Math.min(Math.max(S.vw.s * f, S.fitS * 0.3), S.fitS * 50);
    const wx = (mx - S.vw.ox) / S.vw.s, wy = (my - S.vw.oy) / S.vw.s;
    setView({ s: s2, ox: mx - wx * s2, oy: my - wy * s2 }, false);
  }

  const panelW = () => 340; // 右侧滑出卡占位,聚焦时把目标让到左侧可视区中央
  function focusNode(n) {
    const s = Math.max(S.vw.s, S.fitS * 4);
    setView({ s, ox: (cssW - panelW()) / 2 - n.x * s, oy: cssH / 2 - n.y * s }, true);
  }
  function focusCluster(c) {
    if (!c.members.length) return;
    const xs = c.members.map((n) => n.x), ys = c.members.map((n) => n.y);
    const minX = Math.min(...xs), maxX = Math.max(...xs);
    const minY = Math.min(...ys), maxY = Math.max(...ys);
    const w = Math.max(0.02, maxX - minX), h = Math.max(0.02, maxY - minY);
    const m = 90, availW = Math.max(240, cssW - panelW());
    const s = Math.min((availW - 2 * m) / w, (cssH - 2 * m) / h, S.fitS * 14);
    setView({ s, ox: (availW - s * (minX + maxX)) / 2, oy: (cssH - s * (minY + maxY)) / 2 }, true);
  }

  // ---------- 绘制 ----------
  function hexA(hex, a) {
    const h = hex.replace("#", "");
    const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
    const n = parseInt(full, 16);
    return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
  }
  function shade(hex) { // 标签用:同色系加深
    const h = hex.replace("#", "");
    const n = parseInt(h, 16);
    const f = (v) => Math.round(v * 0.55);
    return `rgb(${f((n >> 16) & 255)},${f((n >> 8) & 255)},${f(n & 255)})`;
  }

  function convexHull(pts) {
    if (pts.length <= 2) return pts.slice();
    const p = pts.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    const cross = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
    const lower = [];
    for (const pt of p) {
      while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], pt) <= 0) lower.pop();
      lower.push(pt);
    }
    const upper = [];
    for (let i = p.length - 1; i >= 0; i--) {
      while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p[i]) <= 0) upper.pop();
      upper.push(p[i]);
    }
    lower.pop(); upper.pop();
    return lower.concat(upper);
  }

  function hullStats(hull) {
    let cx = 0, cy = 0, area = 0;
    for (const [x, y] of hull) { cx += x; cy += y; }
    cx /= hull.length; cy /= hull.length;
    for (let i = 0; i < hull.length; i++) {
      const [x1, y1] = hull[i], [x2, y2] = hull[(i + 1) % hull.length];
      area += x1 * y2 - x2 * y1;
    }
    return { cx, cy, area: Math.abs(area / 2) };
  }

  const HULL_PAD = 16;
  function tracePath(hull) {
    ctx.beginPath();
    if (hull.length === 1) {
      ctx.arc(hull[0][0], hull[0][1], HULL_PAD, 0, 2 * Math.PI);
      return;
    }
    ctx.moveTo(hull[0][0], hull[0][1]);
    for (let i = 1; i < hull.length; i++) ctx.lineTo(hull[i][0], hull[i][1]);
    ctx.closePath();
  }

  function draw() {
    ctx.clearRect(0, 0, cssW, cssH);
    ctx.fillStyle = "#fbfcfd";
    ctx.fillRect(0, 0, cssW, cssH);

    // 同区凸包淡色底(粗描边 + 填充 = 外扩圆角的廉价实现);misc 区不画凸包不画名;
    // 待构建区(unbuilt)画虚线轮廓 —— 可点(进面板一键构建),但视觉上是"还没入区"。
    for (const c of S.clusters) {
      if (!c.members.length || c.misc) { c._hull = null; continue; }
      const hull = convexHull(c.members.map((n) => [SX(n.x), SY(n.y)]));
      c._hull = hull;
      const hovered = S.hover && S.hover.type === "cluster" && S.hover.cluster === c;
      if (c.unbuilt) {
        tracePath(hull);
        ctx.fillStyle = hexA(GREY, hovered ? 0.12 : 0.05);
        ctx.strokeStyle = hexA(GREY, hovered ? 0.16 : 0.07);
        ctx.lineWidth = HULL_PAD * 2;
        ctx.lineJoin = "round";
        ctx.lineCap = "round";
        ctx.stroke();
        ctx.fill();
        ctx.save();
        ctx.setLineDash([6, 5]);
        ctx.lineWidth = 1.4;
        ctx.strokeStyle = "rgba(110,120,135,0.75)";
        tracePath(hull);
        ctx.stroke();
        ctx.restore();
        continue;
      }
      const fill = hexA(c.color || GREY, hovered ? 0.17 : 0.09);
      tracePath(hull);
      ctx.fillStyle = fill;
      ctx.strokeStyle = fill;
      ctx.lineWidth = HULL_PAD * 2;
      ctx.lineJoin = "round";
      ctx.lineCap = "round";
      ctx.stroke();
      ctx.fill();
    }
    // 机构子轮廓(大区套小区):洲色块之上、点之下,浅描边 + 大团标机构名
    const instLabelBoxes = [];
    for (const g of S.instGroups || []) {
      const hull = convexHull(g.members.map((n) => [SX(n.x), SY(n.y)]));
      g._hull = hull; // 悬停命中用(团级 tooltip)
      tracePath(hull);
      ctx.fillStyle = "rgba(255,255,255,0.35)";
      ctx.strokeStyle = "rgba(255,255,255,0.35)";
      ctx.lineWidth = 18;
      ctx.lineJoin = "round";
      ctx.lineCap = "round";
      ctx.stroke();
      ctx.fill();
      ctx.save();
      ctx.setLineDash([4, 4]);
      ctx.lineWidth = 1;
      ctx.strokeStyle = "rgba(90,100,115,0.55)";
      tracePath(hull);
      ctx.stroke();
      ctx.restore();
      // 同大区规则:屏上面积够大(放大)才显示,显示即完整名;缩小自动隐去
      const gs = hull.length >= 3 ? hullStats(hull) : null;
      if (gs && gs.area >= 1800) {
        const gx = gs.cx, gy = gs.cy;
        const t = g.name;
        ctx.font = "600 11px 'Segoe UI','Microsoft YaHei',sans-serif";
        const w = ctx.measureText(t).width;
        const box = { x0: gx - w / 2, x1: gx + w / 2, y0: gy - 18, y1: gy - 6 };
        if (!instLabelBoxes.some((b) => box.x0 < b.x1 && box.x1 > b.x0 && box.y0 < b.y1 && box.y1 > b.y0)) {
          instLabelBoxes.push(box);
          ctx.textAlign = "center";
          ctx.lineWidth = 3;
          ctx.strokeStyle = "rgba(255,255,255,0.9)";
          ctx.strokeText(t, gx, gy - 10);
          ctx.fillStyle = "rgba(70,80,95,0.95)";
          ctx.fillText(t, gx, gy - 10);
        }
      }
    }
    // 点
    for (const n of S.nodes) {
      const x = SX(n.x), y = SY(n.y);
      const c = S.clusterById.get(n.cluster);
      let alpha = n.lit ? 0.92 : 0.38;
      if (S.dimSet && !S.dimSet.has(n.id)) alpha = 0.10;
      ctx.globalAlpha = alpha;
      ctx.beginPath();
      ctx.arc(x, y, n.r, 0, 2 * Math.PI);
      ctx.fillStyle = n.lit && !(c && c.misc) ? (c && c.color) || GREY : GREY; // 零散文献保持灰点
      ctx.fill();
      ctx.lineWidth = 0.6;
      ctx.strokeStyle = "rgba(27,34,48,0.3)";
      ctx.stroke();
      ctx.globalAlpha = 1;
      const hovered = S.hover && S.hover.type === "node" && S.hover.node === n;
      if (n.id === S.selectedId || hovered) {
        ctx.beginPath();
        ctx.arc(x, y, n.r + 3, 0, 2 * Math.PI);
        ctx.lineWidth = 2;
        ctx.strokeStyle = ACCENT;
        ctx.stroke();
      }
    }
    // 区名标签:画在点之上(否则被点淹没);字号随区规模;大区优先,碰撞则小区让位
    const drawn = [];
    const byArea = S.clusters
      .filter((c) => c._hull)
      .map((c) => ({ c, ...hullStats(c._hull) }))
      .sort((a, b) => b.c.members.length - a.c.members.length);
    for (const { c, cx, cy, area } of byArea) {
      const hovered = S.hover && S.hover.type === "cluster" && S.hover.cluster === c;
      // 待构建区的名字是行动入口(点进去一键构建),不论面积大小都画
      if (area < 2200 && !hovered && !c.unbuilt) continue;
      const labelText = c.unbuilt ? `待构建 ${c.members.length} 篇 · 点击构建` : c.label;
      const px = Math.max(12, Math.min(19, 10 + Math.sqrt(c.members.length) * 1.6));
      ctx.font = `700 ${px}px 'Segoe UI','Microsoft YaHei',sans-serif`;
      const w = ctx.measureText(labelText).width;
      const box = { x0: cx - w / 2 - 6, x1: cx + w / 2 + 6, y0: cy - px, y1: cy + px };
      const collides = drawn.some(
        (b) => box.x0 < b.x1 && box.x1 > b.x0 && box.y0 < b.y1 && box.y1 > b.y0
      );
      if (collides && !hovered) continue;
      drawn.push(box);
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.lineWidth = 5;
      ctx.lineJoin = "round";
      ctx.strokeStyle = "rgba(255,255,255,0.92)";
      ctx.strokeText(labelText, cx, cy);
      ctx.fillStyle = c.unbuilt ? "rgba(90,100,115,0.9)" : shade(c.color || GREY);
      ctx.fillText(labelText, cx, cy);
    }
    positionHalo();
  }

  function positionHalo() {
    const n = S.haloId ? S.byId.get(S.haloId) : null;
    halo.hidden = !n;
    if (!n) return;
    halo.style.left = SX(n.x) + "px";
    halo.style.top = SY(n.y) + "px";
  }

  // ---------- 命中测试 ----------
  function nodeAt(mx, my) {
    let best = null, bestD = Infinity;
    for (const n of S.nodes) {
      const d = Math.hypot(SX(n.x) - mx, SY(n.y) - my);
      if (d <= Math.max(n.r + 4, 8) && d < bestD) { best = n; bestD = d; }
    }
    return best;
  }
  function pointInPoly(p, poly) {
    let inside = false;
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      const [xi, yi] = poly[i], [xj, yj] = poly[j];
      if ((yi > p[1]) !== (yj > p[1]) && p[0] < ((xj - xi) * (p[1] - yi)) / (yj - yi) + xi) inside = !inside;
    }
    return inside;
  }
  function distToSeg(p, a, b) {
    const vx = b[0] - a[0], vy = b[1] - a[1];
    const len2 = vx * vx + vy * vy || 1e-9;
    const t = Math.max(0, Math.min(1, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / len2));
    return Math.hypot(p[0] - (a[0] + t * vx), p[1] - (a[1] + t * vy));
  }
  function clusterAt(mx, my) {
    // 小区先测,避免被大区盖住点不中
    const order = S.clusters.slice().sort((a, b) => a.members.length - b.members.length);
    for (const c of order) {
      const hull = c._hull;
      if (!hull || !hull.length) continue;
      if (hull.length === 1) {
        if (Math.hypot(hull[0][0] - mx, hull[0][1] - my) <= HULL_PAD + 2) return c;
      } else if (hull.length === 2) {
        if (distToSeg([mx, my], hull[0], hull[1]) <= HULL_PAD + 2) return c;
      } else if (pointInPoly([mx, my], hull)) {
        return c;
      } else {
        for (let i = 0; i < hull.length; i++) {
          if (distToSeg([mx, my], hull[i], hull[(i + 1) % hull.length]) <= HULL_PAD + 2) return c;
        }
      }
    }
    return null;
  }

  // ---------- 悬浮提示 ----------
  function showTooltip(clientX, clientY, text) {
    const r = stage.getBoundingClientRect();
    tooltip.textContent = text;
    tooltip.hidden = false;
    tooltip.style.left = Math.min(clientX - r.left + 14, Math.max(0, r.width - 290)) + "px";
    tooltip.style.top = Math.min(clientY - r.top + 12, Math.max(0, r.height - 44)) + "px";
  }
  function hideTooltip() { tooltip.hidden = true; }

  function instGroupAt(mx, my) {
    if (S.lens !== "institution") return null;
    const order = (S.instGroups || []).slice().sort((a, b) => a.members.length - b.members.length);
    for (const g of order) {
      const hull = g._hull;
      if (!hull || !hull.length) continue;
      if (hull.length === 1) {
        if (Math.hypot(hull[0][0] - mx, hull[0][1] - my) <= 20) return g;
      } else if (hull.length === 2) {
        if (distToSeg([mx, my], hull[0], hull[1]) <= 14) return g;
      } else if (pointInPoly([mx, my], hull)) {
        return g;
      }
    }
    return null;
  }

  function updateHover(mx, my, clientX, clientY) {
    const n = nodeAt(mx, my);
    const g = n ? null : instGroupAt(mx, my); // 机构团命中优先于洲(小区在大区里)
    const c = n || g ? null : clusterAt(mx, my);
    const prev = S.hover;
    S.hover = n ? { type: "node", node: n }
      : g ? { type: "inst", group: g }
      : c ? { type: "cluster", cluster: c } : null;
    const same = ((prev && prev.node) || null) === ((S.hover && S.hover.node) || null)
      && ((prev && prev.cluster) || null) === ((S.hover && S.hover.cluster) || null)
      && ((prev && prev.group) || null) === ((S.hover && S.hover.group) || null);
    if (!same) S.dirty = true;
    canvas.style.cursor = S.hover ? "pointer" : "default";
    if (n) {
      const rec = titles[n.id] || {};
      const head = rec.title
        ? trunc(rec.title, 60) + (rec.year ? `(${rec.year})` : "")
        : n.id; // 无标题才退回编号兜底(前台一律标题,编号留在后台)
      const unlitReason = n.cluster === "__nofacet__"
        ? "无此类要素(如综述只提及不使用)" : (UNLIT_REASON[S.lens] || "未点亮");
      const sub = [n.institution, rec.journal, n.lit ? null : unlitReason]
        .filter(Boolean).join(" · ");
      showTooltip(clientX, clientY, head + (sub ? "\n" + sub : ""));
    } else if (S.hover && S.hover.type === "inst") {
      const g2 = S.hover.group;
      showTooltip(clientX, clientY, `${g2.name} · ${g2.members.length} 篇(机构团)`);
    } else if (c) {
      showTooltip(clientX, clientY,
        `${c.label} · ${c.members.length} 篇${c.description ? "\n" + c.description : ""}`);
    } else {
      hideTooltip();
    }
  }

  // ---------- 右侧滑出卡 ----------
  function openPanel(titleText, build) {
    S.regionPanel = null; // 非区面板一律清掉描述回填指针(showRegion 自己再设)
    sideTitle.textContent = titleText;
    clear(sideBody);
    build(sideBody);
    side.classList.add("open");
  }
  function closePanel() { side.classList.remove("open"); S.regionPanel = null; }
  sideClose.addEventListener("click", closePanel);

  // 用户可见处一律以标题称呼论文(无标题才退回 Sxx)。
  function paperLabel(pid, len) {
    const t = (titles[pid] && titles[pid].title) || "";
    return t ? trunc(t, len) : pid;
  }

  function showArrivals() {
    openPanel(`新文献着陆(${batch.length} 篇)`, (body) => {
      for (const a of batch) {
        const head = el("div", {}, [
          el("b", { text: paperLabel(a.paper_id, 56) }),
          el("div", { class: "map-side-meta", text: a.isolated
            ? "⚠ 空白地带(与现有库关联弱)"
            : `→ 落入「${a.cluster_label || a.cluster || "?"}」` }),
        ]);
        const row = el("div", { class: "map-row" }, [
          head,
          a.neighbors && a.neighbors.length
            ? el("div", { class: "map-side-meta" }, [
                "最近邻:",
                ...a.neighbors.map((x) => el("div", { class: "map-arrival-nb", text: "· " + paperLabel(x.paper_id, 32) })),
              ])
            : null,
        ]);
        row.addEventListener("click", () => {
          const n = S.byId.get(a.paper_id);
          if (!n) return showToast(`当前镜头里找不到「${paperLabel(a.paper_id, 32)}」`);
          S.selectedId = a.paper_id;
          S.haloId = a.paper_id; // 呼吸光圈(CSS 动画)
          focusNode(n);
          S.dirty = true;
        });
        body.append(row);
      }
    });
  }
  arrivalsBadge.addEventListener("click", showArrivals);

  // ---- 区面板标题行:区名 +「人工」徽标 +「改名」按钮(misc/时间分带不可改名) ----
  function regionTitle(c) {
    clear(sideTitle);
    sideTitle.append(document.createTextNode(`${c.label}(${c.members.length} 篇)`));
    if (c.label_overridden) {
      sideTitle.append(el("span", { class: "map-badge-human", text: "人工", title: "人工命名,永久优先" }));
    }
    if (S.hasBackendClusters && !c.misc && !c.unbuilt && !c.nodata) {
      const btn = el("button", { class: "map-rename-btn", text: "改名", title: "为这个区起个永久名字(优先于自动命名)" });
      btn.addEventListener("click", () => renameUI(c));
      sideTitle.append(btn);
    }
  }

  function renameUI(c) {
    clear(sideTitle);
    const input = el("input", { class: "map-rename-input", value: c.label });
    const ok = el("button", { class: "map-rename-btn", text: "确定" });
    const cancel = el("button", { class: "map-rename-btn", text: "取消" });
    cancel.addEventListener("click", () => regionTitle(c));
    ok.addEventListener("click", async () => {
      const label = input.value.trim();
      if (!label) return showToast("区名不能为空");
      ok.disabled = true; cancel.disabled = true;
      try {
        await putJSON("/map/cluster-label", { lens: S.lens, cluster_id: String(c.id), label });
        c.label = label;
        c.label_overridden = true;
        regionTitle(c);
        S.dirty = true; // 地图上的区名同步重画
        showToast("已改名(人工命名,永久优先)");
      } catch (err) {
        showToast("改名失败:" + err.message);
        ok.disabled = false; cancel.disabled = false;
      }
    });
    input.addEventListener("keydown", (e) => {
      e.stopPropagation(); // 不触发全局 Esc/搜索框逻辑
      if (e.key === "Enter") ok.click();
      if (e.key === "Escape") regionTitle(c);
    });
    sideTitle.append(input, ok, cancel);
    input.focus();
    input.select();
  }

  // ---- 区描述句(AI 一句话):面板顶部淡色块;生成中/缺失时各有说法 ----
  function fillRegionDesc(c, slot) {
    clear(slot);
    if (c.misc) return;
    if (c.description) {
      slot.append(el("span", { text: c.description }), el("span", { class: "map-desc-tag", text: "AI 生成" }));
    } else if (describePending.has(S.lens)) {
      slot.append(el("span", { class: "map-desc-tag", text: "区描述生成中…" }));
    }
  }

  // 进入镜头后:有区缺描述 → 后台静默批量生成(每镜头每次会话只发一次,不阻塞渲染)。
  function maybeDescribe() {
    const lens = S.lens;
    if (!S.hasBackendClusters || describedLenses.has(lens)) return;
    if (!S.clusters.some((c) => !c.misc && !c.description && c.members.length)) return;
    describedLenses.add(lens);
    describePending.add(lens);
    postJSON(`/map/describe?lens=${encodeURIComponent(lens)}`, {})
      .then((resp) => {
        if (S.disposed || S.lens !== lens) return;
        const fresh = new Map((resp.clusters || []).map((rc) => [rc.id, rc]));
        for (const c of S.clusters) {
          const rc = fresh.get(c.id);
          if (rc && rc.description) c.description = rc.description;
        }
        if (S.regionPanel) fillRegionDesc(S.regionPanel.cluster, S.regionPanel.slot);
      })
      .catch(() => { /* 描述是锦上添花:失败静默(无 key 时后端也只回 generated=0) */ })
      .finally(() => {
        describePending.delete(lens);
        if (!S.disposed && S.regionPanel) fillRegionDesc(S.regionPanel.cluster, S.regionPanel.slot);
      });
  }

  // ---- 区面板:本区工具的进场时间线(区内口径,Wave-3 跟进③):
  //      只看本区论文用到的要素,各自在库内首现于何年。折叠 + 展开才拉数据 ----
  function firstSeenSection(c) {
    const det = el("details", { class: "map-panel-sec" });
    det.append(el("summary", { class: "map-facet-head", text: "本区工具的进场时间线" }));
    const slot = el("div", {}, [el("p", { class: "muted", text: "加载中…" })]);
    det.append(slot);
    let loaded = false;
    det.addEventListener("toggle", () => {
      if (!det.open || loaded) return;
      loaded = true;
      getJSON(`/map/first-seen?lens=${encodeURIComponent(S.lens)}&cluster=${encodeURIComponent(c.id)}`)
        .then((d) => {
          clear(slot);
          const list = d.elements || [];
          if (!list.length) return slot.append(el("p", { class: "muted", text: "本区论文没有可定年的要素。" }));
          for (const e2 of list) {
            slot.append(el("div", {
              class: "map-first-seen-row",
              text: `${e2.first_year} · ${e2.name}(库内共 ${e2.papers_total} 篇在用)`,
              title: `库内首现于 ${paperLabel(e2.first_paper, 60)}`,
            }));
          }
        })
        .catch((err) => {
          clear(slot);
          slot.append(el("p", {
            class: "muted",
            text: err.code === 503 ? "要素索引未构建(点右上角状态角标一键构建)。" : "首现数据加载失败:" + err.message,
          }));
        });
    });
    return det;
  }

  // ---- 论文集×要素画像区块(共用):机构面貌 / 区高频要素(撤并自统计屏) ----
  function facetProfileSection(heading, url, emptyText) {
    const box = el("div", { class: "map-panel-sec" }, [
      el("h4", { class: "map-facet-head", text: heading }),
    ]);
    const slot = el("div", {}, [el("p", { class: "muted", text: "加载中…" })]);
    box.append(slot);
    getJSON(url)
      .then((d) => {
        clear(slot);
        const facets = d.facets || {};
        const keys = Object.keys(facets);
        if (!keys.length) return slot.append(el("p", { class: "muted", text: emptyText }));
        for (const f of keys) {
          slot.append(el("div", { class: "map-side-meta", text: f }));
          const wrap = el("div", { class: "map-chip-wrap" });
          for (const it of facets[f] || []) {
            wrap.append(el("span", { class: "tag", text: `${it.name}×${it.papers}` }));
          }
          slot.append(wrap);
        }
      })
      .catch((err) => {
        clear(slot);
        slot.append(el("p", { class: "muted", text: err.code === 503
          ? "要素索引未构建(点右上角状态角标一键构建)。"
          : "要素画像加载失败:" + err.message }));
      });
    return box;
  }

  function institutionSection(instId) {
    return facetProfileSection("该机构的研究面貌",
      `/map/institution-elements?id=${encodeURIComponent(instId)}`,
      "暂无要素数据(该机构论文的要素未构建)。");
  }

  // 五大洲面板:本洲高产机构榜,每行 <details> 展开才拉该机构的要素画像
  function continentInstitutionsSection(c) {
    const box = el("div", { class: "map-panel-sec" }, [
      el("h4", { class: "map-facet-head", text: "本洲高产机构(展开看研究面貌)" }),
    ]);
    for (const inst of c.top_institutions) {
      const det = el("details");
      det.append(el("summary", {}, [
        inst.name, el("span", { class: "map-side-meta", text: ` ×${inst.papers} 篇` }),
      ]));
      let loaded = false;
      det.addEventListener("toggle", () => {
        if (!det.open || loaded) return;
        loaded = true;
        det.append(institutionSection(inst.id));
      });
      box.append(det);
    }
    return box;
  }

  // 区共性画像(瘦身版,用户实测反馈):只列 ≥2 篇共用的要素,叙事序
  // 材料 → 方法 → 主题;单篇专属折叠成一行计数(condition/finding 后端已撤出)。
  function regionElementsSection(c) {
    const box = el("div", { class: "map-panel-sec" }, [
      el("h4", { class: "map-facet-head", text: "本区共性(≥2 篇共用的要素)" }),
    ]);
    const slot = el("div", {}, [el("p", { class: "muted", text: "加载中…" })]);
    box.append(slot);
    getJSON(`/map/region-elements?lens=${encodeURIComponent(S.lens)}&cluster=${encodeURIComponent(c.id)}`)
      .then((d) => {
        clear(slot);
        const facets = d.facets || {};
        const row = (label, items) => {
          if (!items || !items.length) return;
          slot.append(el("div", { class: "map-side-meta", text: label }));
          const wrap = el("div", { class: "map-chip-wrap" });
          for (const it of items) wrap.append(el("span", { class: "tag", text: `${it.name}×${it.papers}` }));
          slot.append(wrap);
        };
        const methods = [];
        for (const f of METHOD_FACETS) methods.push(...(facets[f] || []));
        methods.sort((a, b) => b.papers - a.papers);
        row("材料", facets.material);
        row("方法", methods);
        row("主题", facets.topic);
        for (const f of Object.keys(facets)) {
          if (f === "material" || f === "topic" || METHOD_FACETS.includes(f)) continue;
          row(f, facets[f]);
        }
        if (!slot.childNodes.length) {
          slot.append(el("p", { class: "muted", text: "本区没有 ≥2 篇共用的要素(成员各做各的,靠主题相聚)。" }));
        }
        if (d.singles) {
          slot.append(el("p", { class: "map-side-meta",
            text: `另有 ${d.singles} 项仅单篇出现的要素——点下方成员逐篇看。` }));
        }
      })
      .catch((err) => {
        clear(slot);
        slot.append(el("p", { class: "muted", text: err.code === 503
          ? "要素索引未构建(点右上角状态角标一键构建)。" : "要素画像加载失败:" + err.message }));
      });
    return box;
  }

  function showRegion(c) {
    if (c.unbuilt) return showUnbuilt(c);
    focusCluster(c);
    openPanel("", (body) => {
      const descSlot = el("div", { class: "map-region-desc" });
      body.append(descSlot);
      fillRegionDesc(c, descSlot);
      S.regionPanel = { cluster: c, slot: descSlot };
      // 本区高频要素(Wave-3 ②:统计屏总览的新家;misc/nodata 区成员太杂,不画画像)
      if (S.hasBackendClusters && !c.misc && !c.nodata) {
        body.append(regionElementsSection(c));
      }
      // 年代跨度(年轮口径:区心最老、区缘最新)+ 本区工具进场时间线(折叠懒加载)
      const years = c.members.map((n) => n.year).filter((y) => y != null);
      if (years.length) {
        body.append(el("div", { class: "map-side-meta",
          text: `年代跨度 ${Math.min(...years)}–${Math.max(...years)}(区内年轮:靠区心更老,靠区缘更新)` }));
      }
      if (!c.misc && !c.nodata && S.hasBackendClusters) body.append(firstSeenSection(c));
      // 机构镜头(Wave-3 ④ 五大洲):本洲高产机构,每行展开看"机构×要素"研究面貌
      if (S.lens === "institution" && c.top_institutions && c.top_institutions.length) {
        body.append(continentInstitutionsSection(c));
      }
      if (c.nodata) {
        body.append(el("p", { class: "muted",
          text: "这些论文还没有机构信息(作者机构未拉取,或机构国别未能识别)。" }));
      }
      // 成员列表 = 阅读路线本身(原"阅读路线"按钮的口径并入):
      // 综述优先 → 关联紧密度(size)降序;第一篇给"从这篇读起"标记。
      const isReview = (pid) => /review/i.test(String((titles[pid] || {}).paper_type || ""));
      const ordered = c.members.slice().sort((a, b) =>
        (isReview(b.id) - isReview(a.id)) || ((b.size || 0) - (a.size || 0)));
      body.append(el("div", { class: "map-side-meta",
        text: "成员(按建议阅读顺序:综述优先,其次与同区关联最紧的)" }));
      ordered.forEach((n, i) => {
        const rec = titles[n.id] || {};
        const row = el("div", { class: "map-row" }, [
          el("div", {}, [
            i === 0 ? el("span", { class: "map-read-first", text: "从这篇读起 " }) : null,
            el("b", { text: paperLabel(n.id, 70) }),
            isReview(n.id) ? el("span", { class: "map-side-meta", text: " (综述)" }) : null,
            n.lit ? null : el("span", { class: "map-side-meta", text: " (未点亮)" }),
          ]),
          el("div", { class: "map-side-meta", text: [rec.year, rec.journal].filter(Boolean).join(" · ") }),
        ]);
        row.addEventListener("click", () => showPaper(n));
        body.append(row);
      });
    });
    regionTitle(c); // openPanel 只接受纯文本标题,区标题行(徽标+改名)在这之后自绘
  }

  // ---- 一键构建(共用):待构建区面板 + 状态角标面板都走这套按钮/轮询 ----
  function buildControls(btnText) {
    const btn = el("button", { class: "map-btn", text: btnText });
    const log = el("pre", { class: "muted map-build-log" });
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      btn.textContent = "构建中…(可离开本屏,任务在后台继续)";
      try {
        const { job_id } = await postJSON("/elements/bootstrap", {});
        const job = await pollJob(job_id, {
          hashPrefix: "#/map",
          intervalMs: 2000,
          onTick: (j) => { log.textContent = (j.progress || []).slice(-6).join("\n"); },
        });
        if (job.status === "succeeded") {
          showToast("构建完成,刷新地图…");
          render(view); // 重新拉 /map:要素集指纹已变,灰点自动归位
        } else if (job.status === "detached") {
          // 用户已切去别屏:任务继续在后台跑,不打扰
        } else {
          showToast("构建未完成:" + (job.error || job.status));
          btn.disabled = false;
          btn.textContent = btnText;
        }
      } catch (err) {
        showToast("构建启动失败:" + err.message);
        btn.disabled = false;
        btn.textContent = btnText;
      }
    });
    return { btn, log };
  }

  function showBuildPanel(missing) {
    openPanel("构建要素索引", (body) => {
      body.append(el("p", { class: "muted", text: missing == null
        ? "整库还没有要素索引。构建后,方法/材料镜头、要素检索、区面板画像才有数据(可中断,下次续跑缺失部分)。"
        : `还有 ${missing} 篇没有研究要素。一键补全(增量:只跑缺失的,不重复花钱)。` }));
      const { btn, log } = buildControls("开始构建");
      body.append(el("div", { class: "map-paper-actions" }, [btn]), log);
    });
  }

  // ---- 待构建区面板(Wave-3 ①):解释 + 一键增量构建 + 成员清单 ----
  function showUnbuilt(c) {
    focusCluster(c);
    openPanel(`待构建(${c.members.length} 篇)`, (body) => {
      body.append(el("p", { class: "muted", text:
        `这 ${c.members.length} 篇的研究要素还没有生成,所以暂时进不了任何分区。` +
        "点下面按钮一键构建(增量,只补缺的);完成后这些点会自动落进对应的区。" }));
      const { btn, log } = buildControls(`一键构建要素(${c.members.length} 篇)`);
      body.append(el("div", { class: "map-paper-actions" }, [btn]), log);
      for (const n of c.members) {
        const rec = titles[n.id] || {};
        const row = el("div", { class: "map-row" }, [
          el("div", {}, [el("b", { text: paperLabel(n.id, 70) })]),
          el("div", { class: "map-side-meta", text: [rec.year, rec.journal].filter(Boolean).join(" · ") }),
        ]);
        row.addEventListener("click", () => showPaper(n));
        body.append(row);
      }
    });
  }

  // 论文卡的 facet 顺序与人话标签:按"读论文的顺序"讲——先做什么/发现什么,
  // 再用什么材料、什么方法、什么条件;主题殿后。finding 不在卡上重复
  //(卡片的"主要发现"是整句版本;压缩版半句留在拆解页带原文锚点)。
  const METHOD_FACETS = ["simulation", "measurement", "preparation", "characterization", "analysis"];
  const FACET_SKIP = new Set(["finding", "topic", "material", ...METHOD_FACETS, "condition"]);

  // 折叠词条行(全库统计:五类合并后 204/260 篇超 6 项 → 默认露 6,余下 +N 展开)
  function chipsRow(label, chips, foldAt = 6) {
    if (!chips.length) return null;
    const wrap = el("div", { class: "map-chip-wrap" });
    const mk = (c) => el("span", { class: "tag", text: c.text, title: c.tip || c.text });
    chips.slice(0, foldAt).forEach((c) => wrap.append(mk(c)));
    if (chips.length > foldAt) {
      const more = el("span", { class: "tag tag-more", text: `+${chips.length - foldAt}`,
        title: "展开全部" });
      more.addEventListener("click", () => {
        more.remove();
        chips.slice(foldAt).forEach((c) => wrap.append(mk(c)));
      });
      wrap.append(more);
    }
    return el("div", { class: "map-panel-sec" }, [
      el("h4", { class: "map-facet-head", text: `${label}(${chips.length})` }), wrap,
    ]);
  }

  // 机构团面板:研究面貌(机构×要素)+ 成员按课题组(资深作者)分组
  //(课题组屏撤并入此处:洲→机构→课题组→论文 四级一张图)
  let groupsCache = null; // /groups 响应(pid → 组名),一次会话拉一次
  async function paperGroupMap() {
    if (groupsCache) return groupsCache;
    try {
      const d = await getJSON("/groups");
      const m = new Map();
      for (const grp of d.groups || []) {
        const anchor = grp.anchor_name || grp.anchor_identity || "?";
        for (const p of grp.papers || []) m.set(p.paper_id, anchor);
      }
      groupsCache = m;
    } catch (err) { groupsCache = new Map(); }
    return groupsCache;
  }

  function showInstGroup(g) {
    openPanel(`${g.name}(${g.members.length} 篇)`, (body) => {
      const iid = g.members[0] && g.members[0].institution_id;
      if (iid) body.append(institutionSection(iid));
      const slot = el("div", {}, [el("p", { class: "muted", text: "成员加载中…" })]);
      body.append(slot);
      paperGroupMap().then((pg) => {
        clear(slot);
        const byGroup = new Map();
        for (const n of g.members) {
          const k = pg.get(n.id) || "";
          if (!byGroup.has(k)) byGroup.set(k, []);
          byGroup.get(k).push(n);
        }
        const keys = [...byGroup.keys()].sort((a, b) =>
          (byGroup.get(b).length - byGroup.get(a).length) || a.localeCompare(b));
        for (const k of keys) {
          const ms = byGroup.get(k).sort((a, b) => (a.year || 9999) - (b.year || 9999));
          slot.append(el("h4", { class: "map-facet-head",
            text: k ? `${k} 组(${ms.length} 篇)` : `其他成员(${ms.length} 篇)` }));
          for (const n of ms) {
            const rec = titles[n.id] || {};
            const row = el("div", { class: "map-row" }, [
              el("div", {}, [el("b", { text: paperLabel(n.id, 70) })]),
              el("div", { class: "map-side-meta", text: [rec.year, rec.journal].filter(Boolean).join(" · ") }),
            ]);
            row.addEventListener("click", () => showPaper(n));
            slot.append(row);
          }
        }
      });
    });
  }

  function showPaper(n) {
    S.selectedId = n.id;
    S.haloId = null;
    S.dirty = true;
    focusNode(n);
    const rec = titles[n.id] || {};
    // 标头=标题;编号不上前台(后台对应用,见 paperLabel 兜底)。
    openPanel(rec.title ? trunc(rec.title, 90) : n.id, (body) => {
      const meta = [rec.year, rec.journal].filter(Boolean).join(" · ");
      if (meta) body.append(el("div", { class: "map-side-meta", text: meta }));
      const b1 = el("button", { class: "map-btn", text: "进拆解页" });
      b1.addEventListener("click", () => { location.hash = `#/papers/${n.id}/decompose`; });
      const b2 = el("button", { class: "map-btn", text: "打开 PDF" });
      b2.addEventListener("click", () => window.open(`/papers/${encodeURIComponent(n.id)}/pdf`, "_blank"));
      const b3 = el("button", { class: "map-btn", text: "关系特写" });
      b3.addEventListener("click", () => openCloseup(n.id));
      body.append(el("div", { class: "map-paper-actions" }, [b1, b2, b3]));

      // 1) 先讲这篇做什么 + 主要发现(卡片摘要的整句版本,人读的开场)
      const aboutBox = el("div");
      body.append(aboutBox);
      getJSON(`/papers/${encodeURIComponent(n.id)}`)
        .then((p) => {
          // 作者(★资深)与机构(与详情页同口径)
          if ((p.authors || []).length) {
            aboutBox.append(el("div", { class: "map-side-meta", text: "作者:"
              + p.authors.map((a) => a.name + (a.is_senior ? "★" : "")).join("、") }));
          }
          if ((p.institutions || []).length) {
            aboutBox.append(el("div", { class: "map-side-meta",
              text: "机构:" + p.institutions.join(" · ") }));
          }
          if (p.objective) {
            aboutBox.append(el("div", { class: "map-panel-sec" }, [
              el("h4", { class: "map-facet-head", text: "这篇做什么" }),
              el("p", { class: "map-about", text: p.objective }),
            ]));
          }
          const findings = p.main_findings || [];
          if (findings.length) {
            const ul = el("ul", { class: "map-findings" });
            for (const f of findings) ul.append(el("li", { text: f }));
            aboutBox.append(el("div", { class: "map-panel-sec" }, [
              el("h4", { class: "map-facet-head", text: "主要发现" }), ul,
            ]));
          }
        })
        .catch(() => { /* 摘要拉不到不挡卡片其余部分 */ });

      // 2) 图表:3 列网格最多 9 张;大图可左右翻看全部;再多去详情页画廊
      const figBox = el("div");
      body.append(figBox);
      getJSON(`/papers/${encodeURIComponent(n.id)}/figures`)
        .then(async (d) => {
          const figs = d.figures || [];
          if (!figs.length) return;
          const { openLightbox } = await import("/assets/views/figures.js");
          const wrap = el("div", { class: "map-fig-grid" });
          figs.slice(0, 9).forEach((f, i) => {
            const img = el("img", {
              src: `/papers/${encodeURIComponent(n.id)}/figures/${encodeURIComponent(f.name)}`,
              loading: "lazy", alt: f.caption || f.name, title: f.caption || f.name,
            });
            img.addEventListener("error", () => img.remove());
            img.addEventListener("click", () => openLightbox(n.id, figs, i));
            wrap.append(img);
          });
          const sec = el("div", { class: "map-panel-sec" }, [
            el("h4", { class: "map-facet-head",
              text: `图表(${figs.length} 张 · 点开后可左右翻看全部)` }),
            wrap,
          ]);
          if (figs.length > 9) {
            const more = el("a", { href: `#/papers/${n.id}`, class: "map-fig-more",
              text: `在详情页看全部 ${figs.length} 张 →` });
            sec.append(more);
          }
          figBox.append(sec);
        })
        .catch(() => { /* 图表是锦上添花:拉不到就不显示 */ });

      // 3) 材料 → 方法 → 条件 → 主题:干净词条(引语在拆解页带原文锚点,不在卡上拖半句)
      const elemBox = el("div");
      elemBox.append(el("p", { class: "muted", text: "要素加载中…" }));
      body.append(elemBox);
      getJSON(`/papers/${encodeURIComponent(n.id)}/elements`)
        .then((d) => {
          clear(elemBox);
          const groups = d.groups || [];
          if (!groups.length) {
            elemBox.append(el("p", { class: "muted", text: "该篇要素未构建(到待构建区或右上角状态角标一键构建)。" }));
            return;
          }
          // 全库统计背书的渲染口径:同要素去重(~10% 论文有重复出现);
          // "= 值"只在名字未含该值时追加(73% 条件名已嵌值);五类不再合并。
          const dedupe = (items) => {
            const seen = new Set();
            return (items || []).filter((it) => {
              const k = it.element_id || it.display_name;
              if (seen.has(k)) return false;
              seen.add(k);
              return true;
            });
          };
          const chip = (it, tip) => {
            const name = it.display_name || it.element_id;
            const vals = (it.values || []).map((v) => String(v.raw || v)).filter(Boolean);
            const extra = vals.filter((v) => !name.includes(v));
            return { text: name + (extra.length ? " = " + extra.join(" / ") : ""),
                     tip: tip || String(it.quote || "") };
          };
          const byFacet = new Map(groups.map((g) => [g.facet, dedupe(g.items)]));
          const row = (label, facet, tip) =>
            chipsRow(label, (byFacet.get(facet) || []).map((it) => chip(it, tip)));
          const otherChips = [];
          for (const g of groups) {
            if (FACET_SKIP.has(g.facet)) continue;
            for (const it of byFacet.get(g.facet) || []) {
              otherChips.push(chip(it, `${g.facet}:${it.quote || ""}`));
            }
          }
          for (const sec of [
            row("材料", "material"),
            row("模拟方法", "simulation"),
            row("测量", "measurement"),
            row("表征", "characterization"),
            row("制备", "preparation"),
            row("分析", "analysis"),
            row("条件", "condition"),
            row("主题", "topic", "本库主题标签(地图分区依据)"),
            chipsRow("其他要素", otherChips),
          ]) if (sec) elemBox.append(sec);
          elemBox.append(el("p", { class: "map-side-meta",
            text: "每个词条都有原文出处——进拆解页可看逐字引语并展开原文段。" }));
        })
        .catch((err) => {
          clear(elemBox);
          elemBox.append(el("p", { class: "muted", text: err.code === 503 ? "要素索引未构建(点右上角状态角标一键构建)。" : "要素加载失败:" + err.message }));
        });
    });
  }

  // ---------- 单篇关系特写(自我网络浮层) ----------
  const SVG_NS = "http://www.w3.org/2000/svg";
  function svgEl(tag, attrs = {}, children = []) {
    const node = document.createElementNS(SVG_NS, tag);
    for (const [k, v] of Object.entries(attrs)) if (v != null) node.setAttribute(k, v);
    for (const ch of [].concat(children)) if (ch != null) node.append(ch);
    return node;
  }

  async function openCloseup(pid) {
    closeup.hidden = false;
    clear(closeup);
    const card = el("div", { class: "map-closeup-card" });
    closeup.append(card);
    card.append(el("p", { class: "muted", text: "加载关系数据…" }));
    if (!S.netCache) {
      try { S.netCache = await getJSON("/network"); }
      catch (err) { S.netCache = { edges: [], _error: err.message }; }
    }
    buildCloseup(card, pid);
  }
  function closeCloseup() { closeup.hidden = true; clear(closeup); }
  closeup.addEventListener("click", (e) => { if (e.target === closeup) closeCloseup(); });

  // 外环真口径:该镜头下共享要素最强的 top-8(GET /map/neighbors),按 (镜头|论文) 缓存。
  async function fetchNeighbors(pid) {
    const key = S.lens + "|" + pid;
    if (neighborCache.has(key)) return neighborCache.get(key);
    const d = await getJSON(`/map/neighbors?paper_id=${encodeURIComponent(pid)}&lens=${encodeURIComponent(S.lens)}`);
    const list = d.neighbors || [];
    neighborCache.set(key, list);
    return list;
  }

  async function buildCloseup(card, pid) {
    clear(card);
    const rec = titles[pid] || {};
    const closeBtn = el("button", { class: "map-side-close", text: "×", title: "关闭" });
    closeBtn.addEventListener("click", closeCloseup);
    card.append(el("div", { class: "map-closeup-head" }, [
      el("div", {}, [
        el("b", { text: trunc(rec.title || pid, 70) }),
        el("div", { class: "map-side-meta", text: "关系特写" + (rec.year ? ` · ${rec.year}` : "") }),
      ]),
      closeBtn,
    ]));
    const ld = el("p", { class: "muted", text: "加载共享要素邻居…" });
    card.append(ld);
    let nbList = [], nbErr = null;
    try { nbList = await fetchNeighbors(pid); } catch (err) { nbErr = err; }
    if (closeup.hidden) return; // 等待期间用户已关闭
    ld.remove();

    // 内环 = /network 中与焦点相连的 AI 判边;外环 = /map/neighbors top-8(真·共享要素口径)
    const incident = (S.netCache.edges || []).filter((e2) => e2.a === pid || e2.b === pid);
    const innerMap = new Map();
    for (const e2 of incident) {
      const nid = e2.a === pid ? e2.b : e2.a;
      if (nid && !innerMap.has(nid)) innerMap.set(nid, e2.relation || "");
    }
    const inner = [...innerMap.entries()].slice(0, 12).map(([id, rel]) => ({ id, rel }));
    const innerIds = new Set(inner.map((x) => x.id));
    const outer = nbList
      .filter((x) => x.paper_id !== pid && !innerIds.has(x.paper_id))
      .slice(0, 8)
      .map((x) => ({ id: x.paper_id, rel: null, shared: x.shared || [] }));

    const W = 680, H = 540, cx = W / 2, cy = H / 2;
    const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, class: "map-closeup-svg" });

    function ring(items, radius, isInner) {
      items.forEach((item, i) => {
        const ang = -Math.PI / 2 + (2 * Math.PI * i) / Math.max(1, items.length);
        const x = cx + radius * Math.cos(ang), y = cy + radius * Math.sin(ang);
        const color = isInner ? (REL_COLORS[item.rel] || REL_FALLBACK) : "#98a2b3";
        svg.append(svgEl("line", {
          x1: cx, y1: cy, x2: x, y2: y,
          stroke: color, "stroke-width": isInner ? 2 : 1.2,
          "stroke-dasharray": isInner ? null : "4 4", opacity: isInner ? 0.8 : 0.5,
        }));
        // 圈下两行 = 标题截两段(编号不上前台;悬停 <title> 看全称)
        const full = (titles[item.id] && titles[item.id].title) || item.id;
        const t1 = trunc(full, 16);
        const t2 = full.length > 16 ? trunc(full.slice(16), 14) : "";
        const tip = [
          full,
          isInner
            ? "关系:" + (REL_LABELS[item.rel] || item.rel || "关联")
            : (item.shared && item.shared.length ? "共享要素:" + item.shared.join("、") : null),
        ].filter(Boolean).join("\n");
        const g = svgEl("g", { class: "map-closeup-node" }, [
          svgEl("title", {}, [tip]), // 悬停显示全称 + 全部共享要素
          svgEl("circle", { cx: x, cy: y, r: isInner ? 13 : 10, fill: "#fff", stroke: color, "stroke-width": 2 }),
          svgEl("text", { x, y: y + (isInner ? 26 : 22), "text-anchor": "middle", "font-size": 9, fill: "#1f2328" }, [t1]),
          t2 ? svgEl("text", { x, y: y + (isInner ? 36 : 32), "text-anchor": "middle", "font-size": 8.5, fill: "#656d76" }, [t2]) : null,
          !isInner && item.shared && item.shared.length
            ? svgEl("text", { x, y: y + 44, "text-anchor": "middle", "font-size": 8.5, fill: "#8a7aa8" },
                [trunc(item.shared[0], 14)])
            : null,
        ]);
        g.addEventListener("click", () => buildCloseup(card, item.id)); // 点邻居切焦点
        svg.append(g);
      });
    }
    ring(outer, 218, false);
    ring(inner, 126, true);
    svg.append(
      svgEl("circle", { cx, cy, r: 17, fill: ACCENT }, [svgEl("title", {}, [rec.title || pid])]),
      svgEl("text", { x: cx, y: cy + 32, "text-anchor": "middle", "font-size": 10,
        "font-weight": "600", fill: "#1f2328" }, [trunc(rec.title || pid, 28)]),
    );
    card.append(svg);

    const legend = el("div", { class: "map-legend" });
    const item = (color, label, dashed) =>
      el("span", {}, [el("i", { style: dashed ? `border:1px dashed ${color};background:none` : `background:${color}` }), label]);
    legend.append(
      item(REL_COLORS.supports, "支持"),
      item(REL_COLORS.contradicts, "矛盾"),
      item(REL_COLORS.complements, "互补"),
      item("#98a2b3", "共享要素邻居 top-8(当前镜头)", true),
    );
    card.append(legend);
    if (nbErr) {
      card.append(el("p", { class: "muted", text: nbErr.code === 503 ? "共享要素邻居需要先构建要素索引(外环为空)。" : "共享要素邻居加载失败:" + nbErr.message }));
    } else if (!outer.length) {
      card.append(el("p", { class: "muted", text: "该篇在当前镜头下没有共享要素的邻居(外环为空)。" }));
    }
    if (!inner.length) {
      card.append(el("p", { class: "muted", text: S.netCache._error ? "关系数据不可用:" + S.netCache._error : "该篇暂无 AI 判定的关系边(内环为空)。" }));
    }
  }

  // ---------- 搜索 ----------
  function showChip(text) { searchChip.textContent = text; searchChip.hidden = false; }
  function hideChip() { searchChip.hidden = true; }
  function clearSearch() {
    S.dimSet = null;
    hideChip();
    S.dirty = true;
  }
  function clearSelection() {
    S.selectedId = null;
    S.haloId = null;
    closePanel();
    S.dirty = true;
  }

  function jumpToPaper(pid) { // 标题命中:飞行定位
    const n = S.byId.get(pid);
    if (!n) return showToast(`当前镜头里找不到「${paperLabel(pid, 32)}」`);
    clearSearch();
    S.selectedId = pid;
    S.haloId = null;
    focusNode(n);
    S.dirty = true;
  }

  async function searchByElement(v) { // 要素名:取首个命中要素 → 高亮所有含它的论文,其余压暗
    hideDrop();
    try {
      const hits = (await getJSON(`/elements?q=${encodeURIComponent(v)}`)).elements || [];
      if (!hits.length) return showToast(`没有匹配的要素:${v}`);
      const hit = hits[0];
      const res = await postJSON("/elements/query", { element_ids: [hit.id] });
      const ids = new Set((res.papers || []).map((p) => p.paper_id));
      if (!ids.size) return showToast(`要素「${hit.display_name}」没有命中论文`);
      S.dimSet = ids;
      showChip(`要素「${hit.display_name}」· ${ids.size} 篇(Esc 清除)`);
      S.dirty = true;
    } catch (err) {
      showToast(err.code === 503 ? "要素索引未构建,点右上角状态角标一键构建" : "检索失败:" + err.message);
    }
  }

  // ---- 关键词下拉:标题子串 top-8(本地标题缓存)+ 末行按要素筛选;回车=第一项 ----
  let dropItems = [];
  let dropTimer = null;
  function hideDrop() { searchDrop.hidden = true; clear(searchDrop); dropItems = []; }
  function updateDrop() {
    const q = searchInput.value.trim();
    if (!q) return hideDrop();
    clear(searchDrop);
    dropItems = [];
    const ql = q.toLowerCase();
    const hits = (library.papers || [])
      .filter((p) => (p.title || "").toLowerCase().includes(ql))
      .slice(0, 8);
    for (const p of hits) {
      const run = () => { hideDrop(); jumpToPaper(p.paper_id); };
      const row = el("div", { class: "map-search-item" }, [
        el("span", { class: "map-search-item-title", text: p.title }),
        el("span", { class: "map-side-meta", text: [p.year, p.journal].filter(Boolean).join(" · ") }),
      ]);
      row.addEventListener("pointerdown", (e) => { e.preventDefault(); run(); }); // 先于 blur 生效
      searchDrop.append(row);
      dropItems.push({ run });
    }
    const elemRun = () => { searchByElement(q); };
    const elemRow = el("div", { class: "map-search-item map-search-elem", text: `按要素「${q}」筛选` });
    elemRow.addEventListener("pointerdown", (e) => { e.preventDefault(); elemRun(); });
    searchDrop.append(elemRow);
    dropItems.push({ run: elemRun });
    searchDrop.hidden = false;
  }

  searchInput.addEventListener("input", () => {
    if (dropTimer) clearTimeout(dropTimer);
    dropTimer = setTimeout(() => { dropTimer = null; updateDrop(); }, 200);
  });

  searchInput.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      e.stopPropagation(); // 不再冒泡到全局 Esc(否则会顺手把面板也关了)
      searchInput.value = "";
      hideDrop();
      clearSearch();
      searchInput.blur();
      return;
    }
    if (e.key !== "Enter") return;
    if (dropTimer) { clearTimeout(dropTimer); dropTimer = null; updateDrop(); } // 防抖未落地就回车:先同步刷新
    const v = searchInput.value.trim();
    if (!v) return;
    if (/^s\d+$/i.test(v)) { // 论文号精确输入仍直达
      hideDrop();
      const id = v.toUpperCase();
      const n = S.byId.get(id) || S.nodes.find((x) => String(x.id).toUpperCase() === id);
      if (!n) return showToast(`库中没有 ${id}`);
      clearSearch();
      S.selectedId = n.id;
      focusNode(n);
      S.dirty = true;
      return;
    }
    if (!searchDrop.hidden && dropItems.length) return dropItems[0].run(); // 回车 = 下拉第一项
    searchByElement(v);
  });

  function onKeydown(e) {
    if (e.key !== "Escape") return;
    if (!closeup.hidden) return closeCloseup();
    if (S.dimSet) return clearSearch();
    if (side.classList.contains("open") || S.selectedId || S.haloId) return clearSelection();
  }
  window.addEventListener("keydown", onKeydown);

  // ---------- 镜头切换 / 重新布局 ----------
  lensSel.addEventListener("change", async () => {
    const target = lensSel.value, prev = S.lens;
    lensSel.disabled = true; relayoutBtn.disabled = true;
    hideDrop();
    try {
      const p = await getJSON(`/map?lens=${encodeURIComponent(target)}`);
      prepareLens(p);
      closePanel();
      maybeDescribe(); // 进入镜头后:缺描述的区后台静默补
    } catch (err) {
      lensSel.value = prev;
      showToast(err.code === 503
        ? `「${LENS_NAMES[target] || target}」镜头需要先构建要素索引(点右上角状态角标)`
        : "镜头加载失败:" + err.message);
    }
    lensSel.disabled = false; relayoutBtn.disabled = false;
  });

  relayoutBtn.addEventListener("click", async () => {
    const name = LENS_NAMES[S.lens] || S.lens;
    if (!window.confirm(`重新布局会全量重排「${name}」镜头的点位(老点位置会变)。继续?`)) return;
    lensSel.disabled = true; relayoutBtn.disabled = true;
    try {
      const p = await postJSON(`/map/relayout?lens=${encodeURIComponent(S.lens)}`, {});
      prepareLens(p);
      closePanel();
      showToast("已重新布局");
    } catch (err) {
      showToast("重新布局失败:" + err.message);
    }
    lensSel.disabled = false; relayoutBtn.disabled = false;
  });

  // ---------- 提示条 ----------
  let toastTimer = null;
  function showToast(msg) {
    toast.textContent = msg;
    toast.hidden = false;
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toast.hidden = true; }, 2800);
  }

  // ---------- 画布交互 ----------
  let drag = null;
  canvas.addEventListener("pointerdown", (e) => {
    hideDrop(); // 点画布:收起搜索下拉
    drag = { x: e.clientX, y: e.clientY, ox: S.vw.ox, oy: S.vw.oy, moved: false };
    try { canvas.setPointerCapture(e.pointerId); } catch (err) { /* 非指针环境忽略 */ }
  });
  canvas.addEventListener("pointermove", (e) => {
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    if (drag) {
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      if (Math.hypot(dx, dy) > 4) drag.moved = true;
      if (drag.moved) {
        S.anim = null;
        S.vw = { s: S.vw.s, ox: drag.ox + dx, oy: drag.oy + dy };
        hideTooltip();
        S.dirty = true;
      }
      return;
    }
    updateHover(mx, my, e.clientX, e.clientY);
  });
  canvas.addEventListener("pointerup", (e) => {
    const wasDrag = drag && drag.moved;
    drag = null;
    if (wasDrag) return;
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    const n = nodeAt(mx, my);
    if (n) return showPaper(n);
    const gi = instGroupAt(mx, my);
    if (gi) return showInstGroup(gi);
    const c = clusterAt(mx, my);
    if (c) return showRegion(c);
    clearSelection(); // 点空白:清选中、收面板(搜索高亮用 Esc 清)
  });
  canvas.addEventListener("pointercancel", () => { drag = null; });
  canvas.addEventListener("pointerleave", () => { if (!drag) hideTooltip(); });
  canvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    const rect = canvas.getBoundingClientRect();
    zoomAt(e.clientX - rect.left, e.clientY - rect.top, Math.exp(-e.deltaY * 0.0015));
  }, { passive: false });

  // ---------- 状态记忆:节流保存 / 启动恢复 ----------
  let saveTimer = null;
  function saveNow() {
    try {
      sessionStorage.setItem(STATE_KEY, JSON.stringify({
        lens: S.lens, scale: S.vw.s, panX: S.vw.ox, panY: S.vw.oy, selectedId: S.selectedId,
      }));
    } catch (err) { /* sessionStorage 不可用(隐私模式等):跳过 */ }
  }
  function scheduleSave() {
    if (saveTimer || S.disposed) return;
    saveTimer = setTimeout(() => { saveTimer = null; saveNow(); }, 400);
  }

  // ---------- 启动:尺寸 → 数据 → 状态恢复 → 渲染循环 ----------
  const ro = new ResizeObserver(() => resize());
  ro.observe(stage);
  resize();
  prepareLens(payload);

  if (savedState && savedState.lens === S.lens) { // 镜头没回退才恢复视口/选中
    const { scale, panX, panY, selectedId } = savedState;
    if ([scale, panX, panY].every((v) => typeof v === "number" && isFinite(v)) && scale > 0) {
      S.vw = { s: scale, ox: panX, oy: panY };
      S.anim = null;
    }
    if (selectedId && S.byId.has(selectedId)) S.selectedId = selectedId;
    S.dirty = true;
  }
  maybeDescribe();

  // 导入闭环:import.js 置位 → 读后即清 → 数据已就绪,自动打开着陆卡
  let arriveFlag = false;
  try {
    arriveFlag = sessionStorage.getItem(ARRIVE_KEY) === "1";
    if (arriveFlag) sessionStorage.removeItem(ARRIVE_KEY);
  } catch (err) { arriveFlag = false; }
  if (arriveFlag && batch.length) showArrivals();

  // 详情页「在地图上看这篇」的一次性定位(读后即清)
  try {
    const fp = sessionStorage.getItem("mapFocusPaper");
    if (fp) {
      sessionStorage.removeItem("mapFocusPaper");
      const fn = S.byId.get(fp);
      if (fn) showPaper(fn);
      else showToast("当前镜头里找不到这篇论文");
    }
  } catch (err) { /* sessionStorage 不可用:忽略 */ }

  function tick(now) {
    if (S.disposed) return;
    if (S.anim) {
      const k = Math.min(1, (now - S.anim.t0) / S.anim.dur);
      const ease = 1 - Math.pow(1 - k, 3);
      S.vw = {
        s: lerp(S.anim.from.s, S.anim.to.s, ease),
        ox: lerp(S.anim.from.ox, S.anim.to.ox, ease),
        oy: lerp(S.anim.from.oy, S.anim.to.oy, ease),
      };
      if (k >= 1) S.anim = null;
      S.dirty = true;
    }
    if (S.dirty) { draw(); S.dirty = false; scheduleSave(); }
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);

  // 离开 #/map 时自我清理(app.js 的 route() 不知道视图内部有 rAF 和全局监听)。
  function onHashChange() {
    const name = (location.hash || "#/map").replace(/^#\//, "").split("/").filter(Boolean)[0] || "map";
    if (name !== "map" && teardown) { teardown(); teardown = null; }
  }
  window.addEventListener("hashchange", onHashChange);

  teardown = () => {
    S.disposed = true;
    if (saveTimer) { clearTimeout(saveTimer); saveTimer = null; }
    saveNow(); // 离开前把最终视口落 sessionStorage(状态记忆)
    if (dropTimer) { clearTimeout(dropTimer); dropTimer = null; }
    ro.disconnect();
    window.removeEventListener("keydown", onKeydown);
    window.removeEventListener("hashchange", onHashChange);
    if (toastTimer) clearTimeout(toastTimer);
    view.classList.remove("map-full");
  };
}
