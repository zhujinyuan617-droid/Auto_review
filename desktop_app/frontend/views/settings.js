import { getJSON, postJSON, delJSON } from "/assets/api.js";
import { el, clear, loading, errorState } from "/assets/ui.js";

export async function render(view) {
  loading(view);
  let state;
  let manifest;
  try {
    state = await getJSON("/settings/apikey");
    manifest = await getJSON("/settings/setup-manifest");
  } catch (err) {
    return errorState(view, err.message, () => render(view));
  }
  clear(view);
  view.append(el("h2", { text: "设置" }));
  view.append(apiKeySection(view, state.configured));
  view.append(manifestSection(manifest));
}

function apiKeySection(view, configured) {
  const box = el("div", { class: "card-box section" }, [el("h3", { text: "API Key" })]);
  const status = el("p", { class: "muted", text: configured ? "已配置(已存入系统钥匙串)" : "未配置" });
  box.append(status);
  box.append(el("p", { class: "muted", text: "已接入引擎:此处保存的 key 会注入引擎(env 覆盖优先)。" }));

  const input = el("input", { class: "search", type: "password", placeholder: "粘贴 DeepSeek API key…" });
  const saveBtn = el("button", { text: "保存" });
  saveBtn.addEventListener("click", async () => {
    const key = input.value.trim();
    if (!key) { status.textContent = "key 不能为空"; return; }
    try {
      await postJSON("/settings/apikey", { api_key: key });
      input.value = "";
      render(view);
    } catch (err) {
      status.className = "error";
      status.textContent = err.code === 400 ? "key 无效(空白)" : "保存失败:" + err.message;
    }
  });

  const delBtn = el("button", { text: "删除" });
  delBtn.addEventListener("click", async () => {
    try {
      await delJSON("/settings/apikey");
      render(view);
    } catch (err) {
      status.className = "error";
      status.textContent = "删除失败:" + err.message;
    }
  });

  box.append(el("div", { class: "section" }, [input]), saveBtn, " ", delBtn);
  return box;
}

function manifestSection(manifest) {
  const box = el("div", { class: "card-box section" }, [el("h3", { text: "安装清单" })]);
  const items = manifest.will_install || [];
  const ul = el("ul");
  for (const it of items) ul.append(el("li", { text: `${it.name} —— ${it.purpose}` }));
  box.append(ul);
  if (manifest.optional_later) box.append(el("p", { class: "muted", text: manifest.optional_later }));
  if (manifest.note) box.append(el("p", { class: "muted", text: manifest.note }));
  return box;
}
