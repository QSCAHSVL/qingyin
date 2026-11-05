/* 找歌：多平台搜索、链接识别、下载 / 直接翻唱 */

import { $, api, el, openModal, toast } from "../core.js";
import { watchJob } from "../pages/jobs.js";

/* ------------------------------------------------------------------ 找歌 */
let enabledSources = ["bilibili", "netease", "qqmusic", "itunes"];
let providerMeta = {};

export async function loadProviders() {
  if (Object.keys(providerMeta).length) { renderSourceChips(); return; }
  try {
    const data = await api("/api/search/providers");
    data.providers.forEach((p) => { providerMeta[p.id] = p; });
    renderSourceChips();
  } catch { /* ignore */ }
}

function renderSourceChips() {
  const box = $("#search-sources");
  box.innerHTML = "";
  Object.values(providerMeta).forEach((p) => {
    const on = enabledSources.includes(p.id);
    const chip = el("button", "chip" + (on ? " active" : ""), `${p.label}${p.playable ? "" : "（仅信息）"}`);
    chip.addEventListener("click", () => {
      enabledSources = on ? enabledSources.filter((x) => x !== p.id) : [...enabledSources, p.id];
      renderSourceChips();
      if ($("#search-input").value.trim()) doSearch();
    });
    box.appendChild(chip);
  });
}

export async function doSearch() {
  const q = $("#search-input").value.trim();
  const box = $("#search-results");
  if (!q) return;
  if (/^https?:\/\//i.test(q)) { renderLinkResult(q); return; }
  box.innerHTML = "<div class='empty'>搜索中…</div>";
  try {
    const sources = enabledSources.join(",");
    const data = await api(`/api/search?q=${encodeURIComponent(q)}&sources=${encodeURIComponent(sources)}`);
    box.innerHTML = "";
    if (!data.items.length) { box.appendChild(el("div", "empty", "没搜到，换个说法试试")); return; }
    data.items.forEach((item) => box.appendChild(resultRow(item)));
  } catch (err) {
    box.innerHTML = "";
    box.appendChild(el("div", "empty", `搜索失败：${err.message}`));
  }
}

function resultRow(item) {
  const row = el("div", "result");
  const meta = el("div", "meta");
  meta.appendChild(el("div", "t", item.title || "(无标题)"));
  const tags = el("div", "s");
  const label = (providerMeta[item.source] || {}).label || item.source;
  tags.appendChild(el("span", "tag blue", label));
  tags.appendChild(el("span", "tag", item.duration || "--:--"));
  if (item.author) tags.appendChild(el("span", "tag", /^\d+$/.test(item.author) ? `UP ${item.author}` : item.author));
  if (item.play > 0) {
    const play = item.play >= 10000 ? `${(item.play / 10000).toFixed(1)}万播放` : `${item.play} 播放`;
    tags.appendChild(el("span", "tag", play));
  }
  if (item.playable === false) tags.appendChild(el("span", "tag", "仅信息"));
  if (item.quality) tags.appendChild(el("span", "tag", item.quality === "high" ? "高音质" : "标准"));
  meta.appendChild(tags);
  row.appendChild(meta);

  if (item.playable === false) {
    const open = el("a", "small", "打开页面");
    open.href = item.url;
    open.target = "_blank";
    open.style.padding = "6px 12px";
    row.appendChild(open);
    const tip = el("button", "small ghost", "怎么用？");
    tip.addEventListener("click", () => openModal("这个平台只给信息", [
      el("p", "muted", item.note || "版权音频需要你自己准备：用本地已有文件、在 B 站找同一首，或从自己买过的曲库选。"),
    ]));
    row.appendChild(tip);
    return row;
  }

  const download = el("button", "small", "下载");
  download.addEventListener("click", () => submitDownload(item, false, download));
  const sing = el("button", "small primary", "下载并翻唱");
  sing.addEventListener("click", () => submitDownload(item, true, sing));
  row.appendChild(download);
  row.appendChild(sing);
  return row;
}

function renderLinkResult(url) {
  const box = $("#search-results");
  box.innerHTML = "";
  box.appendChild(resultRow({ source: "bilibili", title: url, url, duration: "--:--", playable: true }));
}

async function submitDownload(item, alsoSing, button) {
  button.disabled = true;
  button.textContent = alsoSing ? "提交中…" : "下载中…";
  try {
    const job = await api("/api/search/download", {
      method: "POST",
      body: JSON.stringify({
        url: item.url, title: item.title, source: item.source, id: item.id,
        name: item.title, sing: alsoSing, full: $("#sing-full").checked,
        quality: $("#search-quality") ? $("#search-quality").value : "standard",
      }),
    });
    toast(alsoSing ? "开始下载并翻唱，去「任务」看进度" : "开始下载", "ok");
    watchJob(job.id, alsoSing ? "sing" : null);
  } catch (err) {
    toast(`提交失败：${err.message}`, "err");
    button.disabled = false;
    button.textContent = alsoSing ? "下载并翻唱" : "下载";
  }
}
