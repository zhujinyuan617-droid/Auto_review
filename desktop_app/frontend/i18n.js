// /assets/i18n.js — 双语核心(spec map §11)。不 import api.js(避免循环依赖),用裸 fetch。
import { ZH } from "/assets/i18n/zh.js";
import { EN } from "/assets/i18n/en.js";

const DICTS = { zh: ZH, en: EN };
let lang = localStorage.getItem("ui_language") || "zh";
if (!DICTS[lang]) lang = "zh";

export function getLang() { return lang; }

export function t(key, params) {
  let s = (DICTS[lang] || {})[key];
  if (s == null) s = ZH[key];               // 缺英文 → 回落中文
  if (s == null) { console.warn("[i18n] missing key:", key); return key; }
  if (params) for (const [k, v] of Object.entries(params)) s = s.split("{" + k + "}").join(String(v));
  return s;
}

// 静态 DOM(index.html 导航等):data-i18n=文本,data-i18n-title=title 属性
export function applyStatic(root) {
  const scope = root || document;
  scope.querySelectorAll("[data-i18n]").forEach((n) => { n.textContent = t(n.getAttribute("data-i18n")); });
  scope.querySelectorAll("[data-i18n-title]").forEach((n) => { n.setAttribute("title", t(n.getAttribute("data-i18n-title"))); });
  document.documentElement.lang = lang;
  document.title = t("app.title");
}

// 启动同步:app_settings 为准,localStorage 只是镜像(spec §11.1)
export async function initLang() {
  try {
    const r = await fetch("/settings/language");
    if (!r.ok) return;
    const remote = (await r.json()).ui_language;
    if (remote && remote !== lang && DICTS[remote]) {
      localStorage.setItem("ui_language", remote);
      location.reload();
    }
  } catch (err) { /* 后端没起也能用镜像 */ }
}

export async function setLang(next) {
  if (!DICTS[next] || next === lang) return;
  try {
    await fetch("/settings/language", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ui_language: next }),
    });
  } catch (err) { /* 后端失败仍允许本地切换;下次 initLang 再对账 */ }
  localStorage.setItem("ui_language", next);
  location.reload();   // 全站文案重渲染:重载最简单可靠
}
