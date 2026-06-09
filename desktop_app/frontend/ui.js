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
