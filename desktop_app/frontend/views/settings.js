import { getJSON, postJSON, putJSON, delJSON } from "/assets/api.js";
import { el, clear, loading, errorState } from "/assets/ui.js";

export async function render(view) {
  loading(view);
  let state;
  let manifest;
  let parallel;
  try {
    state = await getJSON("/settings/apikey");
    manifest = await getJSON("/settings/setup-manifest");
    parallel = await getJSON("/settings/parallel");
  } catch (err) {
    return errorState(view, err.message, () => render(view));
  }
  clear(view);
  view.append(el("h2", { text: "设置" }));
  view.append(apiKeySection(view, state.configured));
  view.append(parallelSection(view, parallel));
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

function parallelSection(view, parallel) {
  const box = el("div", { class: "card-box section" }, [el("h3", { text: "AI 并行数" })]);
  box.append(el("p", {
    class: "muted",
    text: `批量任务(全库构建、补抽等)同时发起的 AI 调用数,按所用模型档位取值。` +
      `账号并发上限:flash ${parallel.limits.flash} / pro ${parallel.limits.pro};` +
      `超过上限只会被限流,不会更快。`,
  }));

  const flashInput = el("input", {
    class: "search", type: "number",
    value: String(parallel.flash), min: "1", max: String(parallel.limits.flash),
  });
  const proInput = el("input", {
    class: "search", type: "number",
    value: String(parallel.pro), min: "1", max: String(parallel.limits.pro),
  });
  const status = el("p", { class: "muted", text: "" });

  const saveBtn = el("button", { text: "保存" });
  saveBtn.addEventListener("click", async () => {
    const flash = parseInt(flashInput.value, 10);
    const pro = parseInt(proInput.value, 10);
    if (!Number.isInteger(flash) || !Number.isInteger(pro)) {
      status.className = "error";
      status.textContent = "请输入整数";
      return;
    }
    try {
      await putJSON("/settings/parallel", { flash, pro });
      render(view);
    } catch (err) {
      status.className = "error";
      status.textContent = (err.code === 400 || err.code === 422)
        ? "数值越界(上限见上方说明,且至少为 1)"
        : "保存失败:" + err.message;
    }
  });

  box.append(el("div", { class: "section" }, [el("label", { text: "flash 并行数:" }), flashInput]));
  box.append(el("div", { class: "section" }, [el("label", { text: "pro 并行数:" }), proInput]));
  box.append(saveBtn, " ", status);
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
