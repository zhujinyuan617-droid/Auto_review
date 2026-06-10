import { getJSON, postJSON } from "/assets/api.js";
import { el, clear, loading, errorState } from "/assets/ui.js";

// 知识地图首页(SP-Map §1/§2/§4 前端面)。
//
// 渲染决定:vendored 的 force-graph 是力导向「模拟」库(坐标由它自己迭代算),
// 而本视图的坐标全部来自后端 /map 的缓存布局(静态、要稳定)。261 个点的散点
// + 同区凸包,用原生 canvas 直接画最合适:零新依赖、老点位置一像素不漂。
// 时间镜头后端只给 {id, year, lit},横轴年代分带、同年纵排在这里(前端)布点。
// 特写外环按任务简化方案:同区内 size(核心度)最高的 8 篇,不算共享要素边。

const LENS_NAMES = { topic: "主题", method: "方法", material: "材料", time: "时间", institution: "机构" };

// 灰点原因按镜头说人话(spec 对方法/材料镜头的原文是「该篇要素未构建」)。
const UNLIT_REASON = {
  topic: "该篇无主题标签",
  method: "该篇要素未构建",
  material: "该篇要素未构建",
  time: "该篇年份未知",
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
const REL_FALLBACK = "#8a7aa8";

let teardown = null; // 上一次挂载的清理(重进/离开路由时执行,防 rAF 与监听泄漏)

export async function render(view) {
  if (teardown) { teardown(); teardown = null; }
  loading(view);
  let payload, library, coverage, arrivals;
  try {
    [payload, library, coverage, arrivals] = await Promise.all([
      getJSON("/map?lens=topic"),
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
  };

  // ---------- DOM 骨架(全屏画布 + 悬浮件) ----------
  clear(view);
  view.classList.add("map-full");
  const stage = el("div", { class: "map-stage" });
  const canvas = el("canvas", { class: "map-canvas" });

  const lensSel = el("select", { class: "map-lens", title: "切换镜头(分区依据)" });
  for (const l of payload.lenses || Object.keys(LENS_NAMES)) {
    lensSel.append(el("option", { value: l }, LENS_NAMES[l] || l));
  }
  lensSel.value = "topic";
  const relayoutBtn = el("button", { class: "map-btn", text: "重新布局", title: "全量重排当前镜头(老点会动)" });
  const topleft = el("div", { class: "map-overlay map-topleft" }, [lensSel, relayoutBtn]);

  const searchInput = el("input", {
    class: "map-search",
    placeholder: "搜论文 Sxx 或要素名,回车;Esc 清除高亮",
  });
  const searchChip = el("span", { class: "map-chip", hidden: "" });
  const topcenter = el("div", { class: "map-overlay map-topcenter" }, [searchInput, searchChip]);

  const statusBadge = el("div", { class: "map-overlay map-status" });
  const nPapers = coverage ? coverage.papers : (payload.nodes || []).length;
  statusBadge.textContent = coverage
    ? `${nPapers} 篇 · 要素 ${coverage.with_elements}/${coverage.papers}`
    : `${nPapers} 篇`;

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
  function timeLayout(raw) {
    // 横轴 = 年代(线性);同年内按 id 字典序均匀纵排;未知年份靠最左一列。
    const years = [...new Set(raw.filter((n) => n.year != null).map((n) => n.year))].sort((a, b) => a - b);
    const minY = years[0], maxY = years[years.length - 1];
    const span = Math.max(1, (maxY || 0) - (minY || 0));
    const xOf = (year) => 0.10 + 0.85 * ((year - minY) / span);
    const groups = new Map();
    for (const n of raw) {
      const key = n.year == null ? "unknown" : n.year;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(n);
    }
    const nodes = [];
    for (const [key, list] of groups) {
      list.sort((a, b) => (a.id < b.id ? -1 : 1));
      list.forEach((n, i) => {
        nodes.push({
          ...n,
          x: key === "unknown" ? 0.03 : xOf(key),
          y: 0.10 + 0.80 * ((i + 1) / (list.length + 1)),
          cluster: "decade:" + (key === "unknown" ? "unknown" : Math.floor(key / 10) * 10),
          size: 0,
        });
      });
    }
    const ids = [...new Set(nodes.map((n) => n.cluster))].sort();
    const clusters = ids.map((d) => ({
      id: d,
      label: d === "decade:unknown" ? "未知年份" : d.replace("decade:", "") + " 年代",
      n: nodes.filter((n) => n.cluster === d).length,
    }));
    return { nodes, clusters };
  }

  function prepareLens(p) {
    S.lens = p.lens;
    S.hasBackendClusters = p.lens !== "time" && Array.isArray(p.clusters);
    let nodes, clusters;
    if (p.lens === "time") {
      ({ nodes, clusters } = timeLayout(p.nodes || []));
    } else {
      nodes = (p.nodes || []).map((n) => ({ ...n }));
      clusters = (p.clusters || []).map((c) => ({ ...c }));
    }
    clusters.slice().sort((a, b) => (String(a.id) < String(b.id) ? -1 : 1))
      .forEach((c, i) => { c.color = PALETTE[i % PALETTE.length]; });
    for (const c of clusters) c.members = [];
    const byCluster = new Map(clusters.map((c) => [c.id, c]));
    const maxSize = Math.max(1e-9, ...nodes.map((n) => n.size || 0));
    for (const n of nodes) {
      n.r = p.lens === "time" ? 4.5 : 3 + Math.sqrt(Math.max(0, n.size || 0) / maxSize) * 7;
      let c = byCluster.get(n.cluster);
      if (!c && n.cluster != null) { // payload 防御:点引用了未登记的区
        c = { id: n.cluster, label: String(n.cluster), n: 0, color: PALETTE[byCluster.size % PALETTE.length], members: [] };
        byCluster.set(n.cluster, c);
        clusters.push(c);
      }
      if (c) c.members.push(n);
    }
    for (const c of clusters) c.members.sort((a, b) => (b.size || 0) - (a.size || 0));
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

    // 同区凸包淡色底(粗描边 + 填充 = 外扩圆角的廉价实现)
    for (const c of S.clusters) {
      if (!c.members.length) { c._hull = null; continue; }
      const hull = convexHull(c.members.map((n) => [SX(n.x), SY(n.y)]));
      c._hull = hull;
      const hovered = S.hover && S.hover.type === "cluster" && S.hover.cluster === c;
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
    // 点
    for (const n of S.nodes) {
      const x = SX(n.x), y = SY(n.y);
      const c = S.clusterById.get(n.cluster);
      let alpha = n.lit ? 0.92 : 0.38;
      if (S.dimSet && !S.dimSet.has(n.id)) alpha = 0.10;
      ctx.globalAlpha = alpha;
      ctx.beginPath();
      ctx.arc(x, y, n.r, 0, 2 * Math.PI);
      ctx.fillStyle = n.lit ? (c && c.color) || GREY : GREY;
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
      if (area < 2200 && !hovered) continue;
      const px = Math.max(12, Math.min(19, 10 + Math.sqrt(c.members.length) * 1.6));
      ctx.font = `700 ${px}px 'Segoe UI','Microsoft YaHei',sans-serif`;
      const w = ctx.measureText(c.label).width;
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
      ctx.strokeText(c.label, cx, cy);
      ctx.fillStyle = shade(c.color || GREY);
      ctx.fillText(c.label, cx, cy);
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

  function updateHover(mx, my, clientX, clientY) {
    const n = nodeAt(mx, my);
    const c = n ? null : clusterAt(mx, my);
    const prev = S.hover;
    S.hover = n ? { type: "node", node: n } : c ? { type: "cluster", cluster: c } : null;
    const same = ((prev && prev.node) || null) === ((S.hover && S.hover.node) || null)
      && ((prev && prev.cluster) || null) === ((S.hover && S.hover.cluster) || null);
    if (!same) S.dirty = true;
    canvas.style.cursor = S.hover ? "pointer" : "default";
    if (n) {
      const t = (titles[n.id] && titles[n.id].title) || "";
      showTooltip(clientX, clientY,
        `${n.id}${t ? " · " + t.slice(0, 60) : ""}${n.lit ? "" : "(" + (UNLIT_REASON[S.lens] || "未点亮") + ")"}`);
    } else if (c) {
      showTooltip(clientX, clientY, `${c.label} · ${c.members.length} 篇`);
    } else {
      hideTooltip();
    }
  }

  // ---------- 右侧滑出卡 ----------
  function openPanel(titleText, build) {
    sideTitle.textContent = titleText;
    clear(sideBody);
    build(sideBody);
    side.classList.add("open");
  }
  function closePanel() { side.classList.remove("open"); }
  sideClose.addEventListener("click", closePanel);

  function showArrivals() {
    openPanel(`新文献着陆(${batch.length} 篇)`, (body) => {
      for (const a of batch) {
        const rec = titles[a.paper_id] || {};
        const head = a.isolated
          ? el("div", {}, [el("b", { text: a.paper_id }), " ⚠ 空白地带(与现有库关联弱)"])
          : el("div", {}, [el("b", { text: a.paper_id }), ` → 落入「${a.cluster_label || a.cluster || "?"}」`]);
        const row = el("div", { class: "map-row" }, [
          head,
          rec.title ? el("div", { class: "map-side-meta", text: rec.title.slice(0, 64) }) : null,
          a.neighbors && a.neighbors.length
            ? el("div", { class: "map-side-meta", text: "最近邻 " + a.neighbors.map((x) => x.paper_id).join(", ") })
            : null,
        ]);
        row.addEventListener("click", () => {
          const n = S.byId.get(a.paper_id);
          if (!n) return showToast(`当前镜头里找不到 ${a.paper_id}`);
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

  function showRegion(c) {
    focusCluster(c);
    openPanel(`${c.label}(${c.members.length} 篇)`, (body) => {
      const routeSlot = el("div");
      body.append(routeSlot);
      if (S.hasBackendClusters) {
        const btn = el("button", { class: "map-btn", text: "阅读路线" });
        btn.addEventListener("click", async () => {
          btn.disabled = true;
          try {
            const r = await getJSON(`/map/route?lens=${encodeURIComponent(S.lens)}&cluster=${encodeURIComponent(c.id)}`);
            clear(routeSlot);
            const box = el("div", { class: "map-route" }, [el("div", { text: r.hint || "建议从这几篇入手:" })]);
            for (const pid of r.start_with || []) {
              const t = (titles[pid] && titles[pid].title) || "";
              const item = el("div", { class: "map-route-item", text: `${pid} ${t.slice(0, 46)}` });
              item.addEventListener("click", () => { const n = S.byId.get(pid); if (n) showPaper(n); });
              box.append(item);
            }
            routeSlot.append(box);
          } catch (err) {
            showToast("路线获取失败:" + err.message);
          }
          btn.disabled = false;
        });
        body.append(el("div", { class: "map-paper-actions" }, [btn]));
      }
      for (const n of c.members) { // 已按核心度(size)降序
        const t = (titles[n.id] && titles[n.id].title) || "";
        const row = el("div", { class: "map-row" }, [
          el("div", {}, [el("b", { text: n.id }), n.lit ? null : el("span", { class: "map-side-meta", text: " (未点亮)" })]),
          el("div", { class: "map-side-meta", text: t.slice(0, 70) || "(无标题)" }),
        ]);
        row.addEventListener("click", () => showPaper(n));
        body.append(row);
      }
    });
  }

  function showPaper(n) {
    S.selectedId = n.id;
    S.haloId = null;
    S.dirty = true;
    focusNode(n);
    const rec = titles[n.id] || {};
    openPanel(n.id, (body) => {
      body.append(
        el("div", { class: "map-paper-title", text: rec.title || "(无标题)" }),
        el("div", { class: "map-side-meta", text: [rec.year, rec.journal].filter(Boolean).join(" · ") }),
      );
      const b1 = el("button", { class: "map-btn", text: "进拆解页" });
      b1.addEventListener("click", () => { location.hash = `#/papers/${n.id}/decompose`; });
      const b2 = el("button", { class: "map-btn", text: "在检索屏选中" });
      // 检索屏暂不读 hash 参数(elements_search.js 非本视图所有);先带 id 跳转,联动留待该屏支持。
      b2.addEventListener("click", () => { location.hash = `#/elements/${n.id}`; });
      const b3 = el("button", { class: "map-btn", text: "关系特写" });
      b3.addEventListener("click", () => openCloseup(n.id));
      body.append(el("div", { class: "map-paper-actions" }, [b1, b2, b3]));

      const elemBox = el("div");
      elemBox.append(el("p", { class: "muted", text: "要素加载中…" }));
      body.append(elemBox);
      getJSON(`/papers/${encodeURIComponent(n.id)}/elements`)
        .then((d) => {
          clear(elemBox);
          const groups = d.groups || [];
          if (!groups.length) {
            elemBox.append(el("p", { class: "muted", text: "该篇要素未构建。" }));
            return;
          }
          for (const g of groups) {
            elemBox.append(el("h4", { class: "map-facet-head", text: g.facet }));
            for (const it of g.items || []) {
              const q = String(it.quote || "");
              elemBox.append(el("div", { class: "map-elem" }, [
                el("span", { class: "tag", text: it.display_name || it.element_id }),
                q ? el("div", { class: "map-quote", text: "“" + q.slice(0, 80) + (q.length > 80 ? "…" : "") + "”" }) : null,
              ]));
            }
          }
        })
        .catch((err) => {
          clear(elemBox);
          elemBox.append(el("p", { class: "muted", text: err.code === 503 ? "要素索引未构建(到「找 → 全库统计」构建)。" : "要素加载失败:" + err.message }));
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

  function buildCloseup(card, pid) {
    clear(card);
    const rec = titles[pid] || {};
    const closeBtn = el("button", { class: "map-side-close", text: "×", title: "关闭" });
    closeBtn.addEventListener("click", closeCloseup);
    card.append(el("div", { class: "map-closeup-head" }, [
      el("div", {}, [
        el("b", { text: pid + " 关系特写" }),
        el("div", { class: "map-side-meta", text: (rec.title || "").slice(0, 70) }),
      ]),
      closeBtn,
    ]));

    // 内环 = /network 中与焦点相连的 AI 判边;外环 = 当前镜头同区 size 最高 8 篇(简化方案)
    const incident = (S.netCache.edges || []).filter((e2) => e2.a === pid || e2.b === pid);
    const innerMap = new Map();
    for (const e2 of incident) {
      const nid = e2.a === pid ? e2.b : e2.a;
      if (nid && !innerMap.has(nid)) innerMap.set(nid, e2.relation || "");
    }
    const inner = [...innerMap.entries()].slice(0, 12).map(([id, rel]) => ({ id, rel }));
    const me = S.byId.get(pid);
    const myCluster = me ? S.clusterById.get(me.cluster) : null;
    const innerIds = new Set(inner.map((x) => x.id));
    const outer = (myCluster ? myCluster.members : [])
      .filter((n) => n.id !== pid && !innerIds.has(n.id))
      .slice(0, 8)
      .map((n) => ({ id: n.id, rel: null }));

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
        const t = ((titles[item.id] && titles[item.id].title) || "").slice(0, 18);
        const g = svgEl("g", { class: "map-closeup-node" }, [
          svgEl("circle", { cx: x, cy: y, r: isInner ? 13 : 10, fill: "#fff", stroke: color, "stroke-width": 2 }),
          svgEl("text", { x, y: y + 3, "text-anchor": "middle", "font-size": 9, fill: "#1f2328" }, [item.id]),
          svgEl("text", { x, y: y + (isInner ? 26 : 22), "text-anchor": "middle", "font-size": 9, fill: "#656d76" }, [t]),
        ]);
        g.addEventListener("click", () => buildCloseup(card, item.id)); // 点邻居切焦点
        svg.append(g);
      });
    }
    ring(outer, 218, false);
    ring(inner, 126, true);
    svg.append(
      svgEl("circle", { cx, cy, r: 17, fill: ACCENT }),
      svgEl("text", { x: cx, y: cy + 3, "text-anchor": "middle", "font-size": 9, fill: "#fff" }, [pid]),
    );
    card.append(svg);

    const legend = el("div", { class: "map-legend" });
    const item = (color, label, dashed) =>
      el("span", {}, [el("i", { style: dashed ? `border:1px dashed ${color};background:none` : `background:${color}` }), label]);
    legend.append(
      item(REL_COLORS.supports, "支持"),
      item(REL_COLORS.contradicts, "矛盾"),
      item(REL_COLORS.complements, "互补"),
      item("#98a2b3", "同区核心(当前镜头 size top-8)", true),
    );
    card.append(legend);
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

  searchInput.addEventListener("keydown", async (e) => {
    if (e.key === "Escape") {
      e.stopPropagation(); // 不再冒泡到全局 Esc(否则会顺手把面板也关了)
      searchInput.value = "";
      clearSearch();
      searchInput.blur();
      return;
    }
    if (e.key !== "Enter") return;
    const v = searchInput.value.trim();
    if (!v) return;
    if (/^s\d+$/i.test(v)) { // 论文号:高亮 + 聚焦
      const id = v.toUpperCase();
      const n = S.byId.get(id) || S.nodes.find((x) => String(x.id).toUpperCase() === id);
      if (!n) return showToast(`库中没有 ${id}`);
      clearSearch();
      S.selectedId = n.id;
      focusNode(n);
      S.dirty = true;
      return;
    }
    try { // 要素名:取首个命中要素 → 高亮所有含它的论文,其余压暗
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
      showToast(err.code === 503 ? "要素索引未构建,先到「找 → 全库统计」构建" : "检索失败:" + err.message);
    }
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
    try {
      const p = await getJSON(`/map?lens=${encodeURIComponent(target)}`);
      prepareLens(p);
      closePanel();
    } catch (err) {
      lensSel.value = prev;
      showToast(err.code === 503
        ? `「${LENS_NAMES[target] || target}」镜头需要先构建要素索引(到「找 → 全库统计」)`
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

  // ---------- 启动:尺寸 → 数据 → 渲染循环 ----------
  const ro = new ResizeObserver(() => resize());
  ro.observe(stage);
  resize();
  prepareLens(payload);

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
    if (S.dirty) { draw(); S.dirty = false; }
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
    ro.disconnect();
    window.removeEventListener("keydown", onKeydown);
    window.removeEventListener("hashchange", onHashChange);
    if (toastTimer) clearTimeout(toastTimer);
    view.classList.remove("map-full");
  };
}
