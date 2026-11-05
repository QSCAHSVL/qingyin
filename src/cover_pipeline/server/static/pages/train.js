/* 训练：素材预检、参数、启动、版本管理 */

import { $, api, closeModal, el, openModal, toast } from "../core.js";
import { loadLibrary } from "../pages/library.js";
import { openPicker } from "../ui/picker.js";

/* ------------------------------------------------------------------ 训练 */
let trainJobId = null;

export async function previewTrain() {
  const data = $("#train-data").value.trim();
  const box = $("#train-preview");
  box.innerHTML = "";
  if (!data) {
    toast("先填素材目录", "err");
    return;
  }
  const btn = $("#train-preview-btn");
  btn.classList.add("loading");
  try {
    const info = await api(`/api/train/preview?data=${encodeURIComponent(data)}`);
    if (info.error) {
      toast(info.error, "err");
      return;
    }
    const rows = [
      ["素材", `${info.files} 个文件，共 ${info.minutes} 分钟`],
      ["预计切段", `${info.segments_est} 段（每段 3 秒）`],
      ["预计耗时", `约 ${info.estimate_minutes} 分钟（${info.epochs} 轮）`],
      ["训练命令", info.command_configured ? "已配置" : "未配置（点下面「训练命令」填）"],
    ];
    rows.forEach(([label, value]) => {
      const row = el("div", "step");
      const body = el("div", "body");
      body.appendChild(el("div", "title", label));
      body.appendChild(el("div", "desc", String(value)));
      row.appendChild(body);
      box.appendChild(row);
    });
    (info.warnings || []).forEach((w) => box.appendChild(el("div", "hint", w)));
    if (!$("#train-epochs").value || Number($("#train-epochs").value) === 80) {
      $("#train-epochs").value = info.epochs || 80;
      $("#train-batch").value = info.batch_size || 4;
    }
    if (!$("#train-model-name").value) $("#train-model-name").value = info.model_name || "";
  } catch (err) {
    toast(err.message, "err");
  } finally {
    btn.classList.remove("loading");
  }
}

export async function startTrain() {
  const data = $("#train-data").value.trim();
  const name = $("#train-name").value.trim();
  if (!data || !name) {
    toast("素材目录和音色名都要填", "err");
    return;
  }
  const btn = $("#train-start");
  btn.classList.add("loading");
  try {
    const job = await api("/api/train", {
      method: "POST",
      body: JSON.stringify({
        data,
        name,
        epochs: Number($("#train-epochs").value) || 80,
        batch_size: Number($("#train-batch").value) || 4,
        sample_rate: Number($("#train-rate").value) || 40000,
        clean: $("#train-clean").checked,
        model_name: $("#train-model-name").value.trim(),
      }),
    });
    trainJobId = job.id;
    $("#train-progress").classList.remove("hidden");
    $("#train-result").innerHTML = "";
    pollTrain();
  } catch (err) {
    toast(err.message, "err");
    btn.classList.remove("loading");
  }
}

async function pollTrain() {
  if (!trainJobId) return;
  const job = await api(`/api/jobs/${trainJobId}`);
  const bar = $("#train-progress .bar");
  const label = $("#train-progress span");
  bar.style.width = `${Math.round((job.progress || 0) * 100)}%`;
  label.textContent = `${job.message || job.status}`;
  if (job.status === "succeeded") {
    $("#train-progress").classList.add("hidden");
    $("#train-start").classList.remove("loading");
    const version = job.result && job.result.version;
    toast(version ? `训练完成：${version.voice} ${version.version}` : "训练完成", "ok");
    if (version) {
      $("#train-result").appendChild(
        el("div", "hint", `已登记 ${version.voice} ${version.version}（当前生效）；不满意可去「资源库 → 音色」切回旧版。`)
      );
    }
    loadTrainVersions();
    return;
  }
  if (job.status === "failed" || job.status === "cancelled") {
    $("#train-progress").classList.add("hidden");
    $("#train-start").classList.remove("loading");
    toast(`训练结束：${job.error || job.status}`, "err");
    return;
  }
  setTimeout(pollTrain, 2000);
}

export async function importModel() {
  const body = el("div");
  const row = el("div", "form-row");
  const nameField = el("label", "field");
  nameField.textContent = "音色名";
  const nameInput = el("input");
  nameInput.placeholder = "例如 yuzhou";
  nameField.appendChild(nameInput);
  const pathField = el("label", "field");
  pathField.style.flex = "1 1 320px";
  pathField.textContent = "模型文件（.pth）";
  const pathInput = el("input");
  pathInput.placeholder = "D:\\models\\xxx.pth";
  pathField.appendChild(pathInput);
  const pickBtn = el("button", "ghost", "选择…");
  pickBtn.addEventListener("click", () => openPicker("#import-path", "选择模型文件", "file", "pth"));
  row.appendChild(nameField);
  row.appendChild(pathField);
  row.appendChild(pickBtn);
  body.appendChild(row);
  const tip = el("div", "muted");
  tip.textContent = "导入会复制到 models/<音色>/versions/vN，并登记成一个版本。";
  tip.style.marginTop = "8px";
  body.appendChild(tip);
  pathInput.id = "import-path";

  const okBtn = el("button", "primary", "导入");
  okBtn.addEventListener("click", async () => {
    const voice = nameInput.value.trim();
    const path = pathInput.value.trim();
    if (!voice || !path) { toast("音色名和文件都要填", "err"); return; }
    try {
      const res = await api("/api/models/import", {
        method: "POST",
        body: JSON.stringify({ voice, path }),
      });
      toast(`已导入 ${res.version || ""}`, "ok");
      closeModal();
      loadTrainVersions();
      loadLibrary();
    } catch (err) {
      toast(err.message, "err");
    }
  });
  const cancelBtn = el("button", "ghost", "取消");
  cancelBtn.addEventListener("click", closeModal);
  openModal("导入音色模型", [body], [cancelBtn, okBtn]);
}

async function deleteModelVersion(voice, version) {
  if (!confirm(`删除 ${voice} ${version}？文件会一起删掉。`)) return;
  try {
    await api("/api/models/delete", {
      method: "POST",
      body: JSON.stringify({ voice, version }),
    });
    toast("已删除", "ok");
    loadTrainVersions();
    loadLibrary();
  } catch (err) {
    toast(err.message, "err");
  }
}

async function loadTrainVersions() {
  const box = $("#train-versions");
  box.innerHTML = "";
  let data;
  try {
    data = await api("/api/models");
  } catch (err) {
    box.appendChild(el("div", "hint", `读取版本失败：${err.message}`));
    return;
  }
  if (!data.voices.length) {
    box.appendChild(el("div", "muted", "还没有训练记录。"));
    return;
  }
  data.voices.forEach((voice) => {
    voice.versions.forEach((ver) => {
      const row = el("div", "step" + (ver.active ? " done" : ""));
      const dot = el("div", "dot", ver.active ? "✓" : "");
      row.appendChild(dot);
      const body = el("div", "body");
      body.appendChild(el("div", "title", `${voice.voice} ${ver.version}${ver.active ? "（当前）" : ""}`));
      const bits = [];
      if (ver.epochs) bits.push(`${ver.epochs} 轮`);
      if (ver.created_at) bits.push(ver.created_at.slice(0, 10));
      if (ver.size_mb) bits.push(`${ver.size_mb}MB`);
      body.appendChild(el("div", "desc", bits.join(" · ") || "-"));
      row.appendChild(body);
      if (!ver.active) {
        const del = el("button", "small ghost", "删除");
        del.addEventListener("click", () => deleteModelVersion(voice.voice, ver.version));
        row.appendChild(del);
      }
      box.appendChild(row);
    });
  });
}

export async function loadTrain() {
  $("#conn").textContent = "已连接";
  $("#conn").style.color = "var(--ok)";
  await loadTrainVersions();
  try {
    const conf = await api("/api/train/config");
    if (conf.command) $("#train-command").value = conf.command;
    if (conf.model_name) $("#train-model-name").value = conf.model_name;
    if (conf.output_dirs && conf.output_dirs.length) {
      $("#train-output-dirs").value = conf.output_dirs.join(";");
    }
    $("#train-epochs").value = conf.epochs || 80;
    $("#train-batch").value = conf.batch_size || 4;
    $("#train-rate").value = String(conf.sample_rate || 40000);
    $("#train-clean").checked = conf.clean !== false;
    $("#train-config-summary").textContent = conf.has_command
      ? "训练命令（已配置，可改）"
      : "训练命令（还没配，点开填一条）";
    if (!conf.has_command) $("#train-config-card").open = true;
  } catch (err) {
    $("#train-config-hint").textContent = `读取训练配置失败：${err.message}`;
  }
}

export function fillTemplate(kind) {
  const rvcDir = "E:\\AI-Companion\\tools\\RVC";
  const rvcPy = "E:\\AI-Companion\\tools\\RVC\\.venv\\Scripts\\python.exe";
  if (kind === "rvc") {
    $("#train-command").value =
      `${rvcPy} ${rvcDir}\\infer\\train.py --exp_name {name} --data {dataset} --epochs {epochs}`;
  } else {
    $("#train-command").value =
      `python train_model.py --data {dataset} --epochs {epochs} --batch {batch} --exp-name {name} --model-name {model_name}`;
  }
  $("#train-config-card").open = true;
}

export async function saveTrainConfig() {
  const dirs = $("#train-output-dirs").value.split(";").map((s) => s.trim()).filter(Boolean);
  try {
    const res = await api("/api/train/config", {
      method: "POST",
      body: JSON.stringify({
        command: $("#train-command").value.trim(),
        model_name: $("#train-model-name").value.trim(),
        output_dirs: dirs,
      }),
    });
    if (!res.ok) {
      toast((res.errors || ["保存失败"]).join("；"), "err");
      return;
    }
    toast("训练命令已保存", "ok");
    $("#train-config-hint").textContent = res.note || "";
  } catch (err) {
    toast(err.message, "err");
  }
}
