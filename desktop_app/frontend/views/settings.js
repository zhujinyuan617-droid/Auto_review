import { getJSON, postJSON, putJSON, delJSON } from "/assets/api.js";
import { el, clear, loading, errorState } from "/assets/ui.js";
import { t, getLang, setLang } from "/assets/i18n.js";

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
  view.append(el("h2", { text: t("settings.title") }));
  view.append(languageSection());
  view.append(apiKeySection(view, state.configured));
  view.append(parallelSection(view, parallel));
  view.append(manifestSection(manifest));
}

function languageSection() {
  const box = el("div", { class: "card-box section" }, [el("h3", { text: t("settings.language_title") })]);
  box.append(el("p", { class: "muted", text: t("settings.language_hint") }));
  for (const [code, labelKey] of [["zh", "settings.language_zh"], ["en", "settings.language_en"]]) {
    const btn = el("button", { text: (getLang() === code ? "✓ " : "") + t(labelKey) });
    btn.addEventListener("click", () => setLang(code));
    box.append(btn, " ");
  }
  return box;
}

function apiKeySection(view, configured) {
  const box = el("div", { class: "card-box section" }, [el("h3", { text: "API Key" })]);
  const status = el("p", { class: "muted", text: configured ? t("settings.apikey_configured") : t("settings.apikey_not_configured") });
  box.append(status);
  box.append(el("p", { class: "muted", text: t("settings.apikey_hint") }));

  const input = el("input", { class: "search", type: "password", placeholder: t("settings.apikey_placeholder") });
  const saveBtn = el("button", { text: t("common.save") });
  saveBtn.addEventListener("click", async () => {
    const key = input.value.trim();
    if (!key) { status.textContent = t("settings.apikey_empty"); return; }
    try {
      await postJSON("/settings/apikey", { api_key: key });
      input.value = "";
      render(view);
    } catch (err) {
      status.className = "error";
      status.textContent = err.code === 400 ? t("settings.apikey_invalid") : t("settings.save_fail") + err.message;
    }
  });

  const delBtn = el("button", { text: t("common.delete") });
  delBtn.addEventListener("click", async () => {
    try {
      await delJSON("/settings/apikey");
      render(view);
    } catch (err) {
      status.className = "error";
      status.textContent = t("settings.delete_fail") + err.message;
    }
  });

  box.append(el("div", { class: "section" }, [input]), saveBtn, " ", delBtn);
  return box;
}

function parallelSection(view, parallel) {
  const box = el("div", { class: "card-box section" }, [el("h3", { text: t("settings.parallel_title") })]);
  box.append(el("p", {
    class: "muted",
    text: t("settings.parallel_hint", { flash: parallel.limits.flash, pro: parallel.limits.pro }),
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

  const saveBtn = el("button", { text: t("common.save") });
  saveBtn.addEventListener("click", async () => {
    const flash = parseInt(flashInput.value, 10);
    const pro = parseInt(proInput.value, 10);
    if (!Number.isInteger(flash) || !Number.isInteger(pro)) {
      status.className = "error";
      status.textContent = t("settings.parallel_int_required");
      return;
    }
    try {
      await putJSON("/settings/parallel", { flash, pro });
      render(view);
    } catch (err) {
      status.className = "error";
      status.textContent = (err.code === 400 || err.code === 422)
        ? t("settings.parallel_out_of_range")
        : t("settings.save_fail") + err.message;
    }
  });

  box.append(el("div", { class: "section" }, [el("label", { text: t("settings.parallel_flash_label") }), flashInput]));
  box.append(el("div", { class: "section" }, [el("label", { text: t("settings.parallel_pro_label") }), proInput]));
  box.append(saveBtn, " ", status);
  return box;
}

function manifestSection(manifest) {
  const box = el("div", { class: "card-box section" }, [el("h3", { text: t("settings.manifest_title") })]);
  const items = manifest.will_install || [];
  const ul = el("ul");
  for (const it of items) ul.append(el("li", { text: `${it.name} —— ${it.purpose}` }));
  box.append(ul);
  if (manifest.optional_later) box.append(el("p", { class: "muted", text: manifest.optional_later }));
  if (manifest.note) box.append(el("p", { class: "muted", text: manifest.note }));
  return box;
}
