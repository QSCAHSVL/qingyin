/* 设置：数据目录、发布配置、备份 */

import { $, api, el, toast } from "../core.js";

/* ------------------------------------------------------------------ 发布与备份 */
export async function loadSendConfig() {
  try {
    const data = await api("/api/settings");
    const send = data.send || {};
    $("#set-send-enabled").checked = !!send.enabled;
    $("#set-send-target").value = send.target || "";
    $("#set-send-account").value = send.account || "main";
  } catch { /* 忽略 */ }
}

export async function saveSendConfig() {
  try {
    const res = await api("/api/settings/send", {
      method: "POST",
      body: JSON.stringify({
        enabled: $("#set-send-enabled").checked,
        target: $("#set-send-target").value.trim(),
        account: $("#set-send-account").value,
      }),
    });
    if (!res.ok) { toast((res.errors || ["保存失败"]).join("；"), "err"); return; }
    toast("发布配置已保存", "ok");
    $("#set-backup-hint").textContent = res.note || "";
  } catch (err) {
    toast(err.message, "err");
  }
}

export async function startBackup() {
  const btn = $("#set-backup");
  btn.classList.add("loading");
  try {
    const job = await api("/api/backup", { method: "POST", body: "{}" });
    toast("备份开始跑了", "ok");
    const timer = setInterval(async () => {
      const j = await api(`/api/jobs/${job.id}`);
      $("#set-backup-hint").textContent = `备份中：${j.message || j.status}`;
      if (["succeeded", "failed", "cancelled"].includes(j.status)) {
        clearInterval(timer);
        btn.classList.remove("loading");
        if (j.status === "succeeded" && j.result) {
          $("#set-backup-hint").textContent = `已备份 ${j.result.files} 个文件（${j.result.size_mb}MB）→ ${j.result.path}`;
          toast("备份完成", "ok");
        } else {
          $("#set-backup-hint").textContent = `备份失败：${j.error || j.status}`;
        }
      }
    }, 1500);
  } catch (err) {
    btn.classList.remove("loading");
    toast(err.message, "err");
  }
}

/* ------------------------------------------------------------------ 设置 */
export async function loadSettings() {
  let data;
  try {
    data = await api("/api/settings");
  } catch (err) {
    toast(`读取设置失败：${err.message}`, "err");
    return;
  }
  $("#set-work").value = data.project.work_dir || "";
  $("#set-output").value = data.project.output_dir || "";
  $("#set-models").value = data.project.models_dir || "";

  const describe = (key) => {
    const usage = (data.usage || {})[key] || {};
    const resolved = (data.resolved || {})[key] || "";
    const state = usage.exists ? `${usage.files} 个文件，${usage.size_mb} MB` : "目录还没创建";
    return `${resolved}　·　${state}`;
  };
  $("#conn").textContent = "已连接";
  $("#conn").style.color = "var(--ok)";
  $("#set-work-info").textContent = describe("work_dir");
  $("#set-output-info").textContent = describe("output_dir");
  $("#set-models-info").textContent = describe("models_dir");

  const box = $("#set-service");
  box.innerHTML = "";
  const items = [
    ["版本", data.version],
    ["服务地址", `http://127.0.0.1:${location.port || "7801"}`, true],
    ["项目根目录", data.root, true],
    ["磁盘", `剩 ${data.disk.free_gb} G / 共 ${data.disk.total_gb} G`],
  ];
  items.forEach(([label, value, mono]) => {
    const card = el("div", "card metric");
    card.appendChild(el("div", "label", label));
    card.appendChild(el("div", "value" + (mono ? " mono" : ""), String(value)));
    box.appendChild(card);
  });
}

export async function saveSettings() {
  const btn = $("#set-save");
  btn.classList.add("loading");
  try {
    const res = await api("/api/settings", {
      method: "POST",
      body: JSON.stringify({
        work_dir: $("#set-work").value.trim(),
        output_dir: $("#set-output").value.trim(),
        models_dir: $("#set-models").value.trim(),
      }),
    });
    if (!res.ok) {
      toast((res.errors || ["保存失败"]).join("；"), "err");
      return;
    }
    toast("已保存，重启卿音后生效", "ok");
    $("#set-hint").textContent = res.note || "";
    await loadSettings();
  } catch (err) {
    toast(err.message, "err");
  } finally {
    btn.classList.remove("loading");
  }
}
