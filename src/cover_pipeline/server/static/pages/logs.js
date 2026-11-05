/* 日志：文件列表与服务端日志尾部 */

import { $, api } from "../core.js";

/* ------------------------------------------------------------------ 日志 */
let logFiles = [];

export async function loadLogs() {
  const sel = $("#log-file");
  let data;
  try {
    data = await api("/api/logs");
  } catch (err) {
    $("#log-body").textContent = `读取日志列表失败：${err.message}`;
    return;
  }
  logFiles = data.files || [];
  sel.innerHTML = "";
  if (!logFiles.length) {
    $("#log-body").textContent = "还没有日志文件（跑一次任务就会生成）";
    return;
  }
  logFiles.forEach((file) => {
    const opt = document.createElement("option");
    opt.value = file.name;
    const when = new Date(file.mtime * 1000).toLocaleString("zh-CN", { hour12: false });
    opt.textContent = `${file.name}（${file.size_kb}KB · ${when}）`;
    sel.appendChild(opt);
  });
  await showLog(sel.value);
}

export async function showLog(name) {
  const lines = $("#log-lines").value || 300;
  try {
    const data = await api(`/api/logs/tail?name=${encodeURIComponent(name)}&lines=${lines}`);
    if (data.error) { $("#log-body").textContent = data.error; return; }
    $("#log-body").textContent = data.lines.join("\n") || "（空）";
    $("#log-body").scrollTop = $("#log-body").scrollHeight;
  } catch (err) {
    $("#log-body").textContent = `读取失败：${err.message}`;
  }
}
