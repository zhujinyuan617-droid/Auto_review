// DOM helpers. el() builds a node; the state helpers give every view the same
// loading / empty / error treatment so a failure never leaves a blank panel.
export function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (v != null) node.setAttribute(k, v);
  }
  for (const child of [].concat(children)) {
    if (child == null) continue;
    node.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return node;
}

export function clear(node) { node.replaceChildren(); }

export function loading(node) {
  clear(node);
  node.append(el("p", { class: "muted", text: "加载中…" }));
}

export function empty(node, message) {
  clear(node);
  node.append(el("p", { class: "muted", text: message }));
}

export function errorState(node, message, onRetry) {
  clear(node);
  node.append(el("p", { class: "error", text: "出错:" + message }));
  if (onRetry) {
    const button = el("button", { text: "重试" });
    button.addEventListener("click", onRetry);
    node.append(button);
  }
}

export function placeholder(node) {
  clear(node);
  node.append(el("p", { class: "muted", text: "(开发中)" }));
}

// facet 的人话标签(一份映射四处共用:检索树/共现/区画像/机构面貌/论文卡;
// 双语版面批次会把这里换成词典查表)。proposed:* = AI 抽取自创、未人工转正的临时类。
const FACET_LABELS = {
  topic: "主题", material: "材料", simulation: "模拟方法", measurement: "测量",
  characterization: "表征", preparation: "制备", analysis: "分析",
  condition: "条件", finding: "发现", institution: "机构",
};

export function facetLabel(id) {
  const k = String(id || "");
  if (FACET_LABELS[k]) return FACET_LABELS[k];
  if (k.startsWith("proposed:")) return "AI提议:" + k.slice(9);
  return k;
}
