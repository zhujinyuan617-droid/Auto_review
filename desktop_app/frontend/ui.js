// DOM helpers. el() builds a node; the state helpers give every view the same
// loading / empty / error treatment so a failure never leaves a blank panel.
import { t } from "/assets/i18n.js";

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
  node.append(el("p", { class: "muted", text: t("common.loading") }));
}

export function empty(node, message) {
  clear(node);
  node.append(el("p", { class: "muted", text: message }));
}

export function errorState(node, message, onRetry) {
  clear(node);
  node.append(el("p", { class: "error", text: t("common.error_prefix") + message }));
  if (onRetry) {
    const button = el("button", { text: t("common.retry") });
    button.addEventListener("click", onRetry);
    node.append(button);
  }
}

export function placeholder(node) {
  clear(node);
  node.append(el("p", { class: "muted", text: t("common.wip") }));
}

// facet 的人话标签(一份映射四处共用:检索树/共现/区画像/机构面貌/论文卡;
// 标签走 i18n 词典(facet.*))。proposed:* = AI 抽取自创、未人工转正的临时类。
const FACETS = ["topic", "material", "simulation", "measurement", "characterization",
                "preparation", "analysis", "condition", "finding", "institution"];

export function facetLabel(id) {
  const k = String(id || "");
  if (FACETS.includes(k)) return t("facet." + k);
  if (k.startsWith("proposed:")) return t("facet.proposed_prefix") + k.slice(9);
  return k;
}
