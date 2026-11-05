/* 资源库：模型 / 歌曲 / 成品 / 音色、分页、批量操作 */

import { $, $$, api, el, toast } from "../core.js";
import { watchJob } from "../pages/jobs.js";

/* ------------------------------------------------------------------ 资源库 */

export const libState = { kind: "model", page: 1, pages: 1, selected: new Set() };

export async function loadLibrary(kind, page) {
  libState.kind = kind || libState.kind;
  libState.page = page || 1;
  libState.selected = new Set();
  $$("#page-library button[data-kind]").forEach((b) => b.classList.toggle("active", b.dataset.kind === libState.kind));
  const q = $("#lib-q").value.trim();
  const size = Number($("#lib-size").value) || 20;
  if (libState.kind !== "voice") {
    const heads = $$("#lib-table thead th");
    if (heads.length >= 5) {
      heads[1].textContent = "名字";
      heads[2].textContent = "大小";
      heads[3].textContent = "路径";
      heads[4].textContent = "操作";
    }
  }
  const tbody = $("#lib-table tbody");
  tbody.innerHTML = "";
  for (let i = 0; i < 6; i += 1) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 5;
    td.appendChild(el("div", "skeleton skeleton-row"));
    tr.appendChild(td);
    tbody.appendChild(tr);
  }

  if (libState.kind === "voice") {
    renderVoices(tbody);
    $("#lib-summary").textContent = "训练完成后会自动登记新版本；切回旧版不影响已有成品。";
    $("#page-info").textContent = "";
    return;
  }

  let items = [];
  let total = 0;
  if (libState.kind === "favorite") {
    const data = await api("/api/library/favorites");
    items = data.items;
    total = items.length;
    libState.pages = 1;
  } else {
    const data = await api(`/api/library?kind=${libState.kind}&q=${encodeURIComponent(q)}&page=${libState.page}&size=${size}`);
    items = data.items;
    total = data.total;
    libState.pages = data.pages;
    libState.page = data.page;
  }

  const infoEl = $("#page-info");
  const summaryEl = $("#lib-summary");
  if (infoEl) infoEl.textContent = `第 ${libState.page} / ${libState.pages} 页`;
  if (summaryEl) summaryEl.textContent = `共 ${total} 个文件（本页 ${items.length} 个）`;

  tbody.innerHTML = "";
  items.forEach((item) => {
    try {
      tbody.appendChild(libRow(item));
    } catch (err) {
      if (summaryEl) summaryEl.textContent += `  [行渲染出错：${err.message}]`;
    }
  });
  $("#page-prev").disabled = libState.page <= 1;
  $("#page-next").disabled = libState.page >= libState.pages;
  $("#page-jump").value = libState.page;
  updateBatchBar();
  const stats = await api("/api/library/stats");
  if (summaryEl) summaryEl.textContent += `　合计 ${(stats.total_bytes / 1024 / 1024).toFixed(0)} MB`;
}

function libRow(item) {
  const tr = el("tr");
  const checkCell = el("td");
  const cb = el("input");
  cb.type = "checkbox";
  cb.addEventListener("change", () => {
    if (cb.checked) libState.selected.add(item.path); else libState.selected.delete(item.path);
    updateBatchBar();
  });
  checkCell.appendChild(cb);
  tr.appendChild(checkCell);

  const nameCell = el("td");
  const link = el("a", "link", (item.favorite ? "★ " : "") + item.name);
  link.href = "#";
  link.addEventListener("click", async (e) => {
    e.preventDefault();
    try {
      await api("/api/reveal", { method: "POST", body: JSON.stringify({ path: item.path }) });
    } catch (err) { toast(err.message, "err"); }
  });
  nameCell.appendChild(link);
  tr.appendChild(nameCell);
  tr.appendChild(el("td", null, item.size_human || `${((item.size_bytes || 0) / 1024 / 1024).toFixed(1)}MB`));
  tr.appendChild(el("td", "muted small-path", item.path));

  const actions = el("td", "row-actions");
  const fav = el("button", "small ghost", item.favorite ? "★" : "☆");
  fav.title = item.favorite ? "取消收藏" : "收藏";
  fav.addEventListener("click", async () => {
    await api("/api/library/favorite", { method: "POST", body: JSON.stringify({ path: item.path, on: !item.favorite }) });
    toast(item.favorite ? "已取消收藏" : "已收藏", "ok");
    loadLibrary(libState.kind, libState.page);
  });
  const open = el("button", "small ghost", "定位");
  open.title = "在资源管理器里打开";
  open.addEventListener("click", async () => {
    try { await api("/api/reveal", { method: "POST", body: JSON.stringify({ path: item.path }) }); }
    catch (err) { toast(err.message, "err"); }
  });
  const del = el("button", "small ghost", "删除");
  del.addEventListener("click", async () => {
    if (!confirm(`删除「${item.name}」？会挪到 work/_trash。`)) return;
    await api("/api/library/delete", { method: "POST", body: JSON.stringify({ path: item.path }) });
    toast("已挪到回收站", "ok");
    loadLibrary(libState.kind, libState.page);
  });
  actions.appendChild(fav);
  actions.appendChild(open);
  actions.appendChild(del);
  tr.appendChild(actions);
  return tr;
}

async function renderVoices(tbody) {
  tbody.innerHTML = "";
  const heads = $$("#lib-table thead th");
  if (heads.length >= 5) {
    heads[1].textContent = "音色 / 版本";
    heads[2].textContent = "大小";
    heads[3].textContent = "训练信息";
    heads[4].textContent = "操作";
  }
  let data;
  try {
    data = await api("/api/models");
  } catch (err) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 5;
    td.appendChild(el("div", "empty", `读取模型版本失败：${err.message}`));
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }
  if (!data.voices.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 5;
    td.appendChild(el("div", "empty", "还没有版本记录。训练完成后会自动登记；也可以 cover models import --path xxx.pth 手动加。"));
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }
  data.voices.forEach((voice) => {
    voice.versions.forEach((ver) => {
      const tr = el("tr");
      tr.appendChild(el("td"));
      const nameCell = el("td");
      nameCell.appendChild(el("strong", null, voice.voice));
      nameCell.appendChild(el("span", "muted", `  ${ver.version}`));
      tr.appendChild(nameCell);
      tr.appendChild(el("td", null, ver.size_mb ? `${ver.size_mb}MB` : "-"));
      const info = [ver.created_at ? ver.created_at.slice(0, 10) : null, ver.epochs ? `${ver.epochs} 轮` : null]
        .filter(Boolean).join(" · ");
      tr.appendChild(el("td", "muted", info || "-"));
      const actions = el("td", "row-actions");
      if (ver.active) {
        actions.appendChild(el("span", "pill ok", "当前"));
      } else {
        const use = el("button", "small", "设为当前");
        use.addEventListener("click", async () => {
          use.classList.add("loading");
          try {
            await api("/api/models/activate", {
              method: "POST",
              body: JSON.stringify({ voice: voice.voice, version: ver.version }),
            });
            toast(`已切到 ${voice.voice} ${ver.version}`, "ok");
            loadLibrary("voice");
          } catch (err) {
            toast(err.message, "err");
          } finally {
            use.classList.remove("loading");
          }
        });
        actions.appendChild(use);
      }
      tr.appendChild(actions);
      tbody.appendChild(tr);
    });
  });
}

export function updateBatchBar() {
  const bar = $("#lib-batch");
  const count = libState.selected.size;
  $("#lib-selected-text").textContent = `已选 ${count} 项`;
  bar.classList.toggle("hidden", count === 0);
}

export async function batchAction(action, extra = {}) {
  const paths = [...libSelected];
  if (!paths.length) return;
  if (action === "delete" && !confirm(`删除这 ${paths.length} 项？会挪到 work/_trash。`)) return;
  await api("/api/library/batch", {
    method: "POST",
    body: JSON.stringify({ action, paths, ...extra }),
  });
  toast(`已处理 ${paths.length} 项`, "ok");
  loadLibrary(libState.kind, libState.page);
}

export async function scanLibrary() {
  const job = await api("/api/library/scan", { method: "POST", body: "{}" });
  toast("正在重建索引", "ok");
  watchJob(job.id, null);
}
