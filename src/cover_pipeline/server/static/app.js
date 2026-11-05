/* cover-pipeline v4 前端：原生 JS，不打包不编译 */

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));
const el = (tag, cls, text) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
};

async function api(path, options = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  const text = await res.text();
  let data = {};
  try { data = JSON.parse(text); } catch { data = { error: text }; }
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  // 任何一次成功请求都把页脚标成已连接（不用每个页面各写一遍）
  const conn = $("#conn");
  if (conn) {
    conn.textContent = "已连接";
    conn.style.color = "var(--ok)";
  }
  connFailures = 0;
  return data;
}

function toast(message, kind = "") {
  const node = el("div", "toast " + kind);
  const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", kind === "err" ? "#i-alert" : kind === "ok" ? "#i-check" : "#i-alert");
  icon.appendChild(use);
  node.appendChild(icon);
  node.appendChild(el("span", null, message));
  $("#toasts").appendChild(node);
  setTimeout(() => node.remove(), 3600);
}

/* ------------------------------------------------------------------ 弹窗 */
let modalReturnFocus = null;

function openModal(title, bodyNodes, footNodes) {
  modalReturnFocus = document.activeElement;
  $("#modal-title").textContent = title;
  const body = $("#modal-body");
  body.innerHTML = "";
  (bodyNodes || []).forEach((n) => body.appendChild(n));
  const foot = $("#modal-foot");
  foot.innerHTML = "";
  (footNodes || []).forEach((n) => foot.appendChild(n));
  $("#modal").classList.remove("hidden");
  document.body.style.overflow = "hidden";
  const focusable = $("#modal-box-focus") || $("#modal").querySelector("button, input, select, textarea, a[href]");
  if (focusable) focusable.focus({ preventScroll: true });
}
function closeModal() {
  $("#modal").classList.add("hidden");
  document.body.style.overflow = "";
  if (modalReturnFocus && modalReturnFocus.focus) modalReturnFocus.focus({ preventScroll: true });
}
$("#modal-close").addEventListener("click", closeModal);
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });

/* 键盘：Esc 关弹层；/ 聚焦搜索；Ctrl+Enter 提交当前页主操作 */
document.addEventListener("keydown", (e) => {
  const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName || "");
  if (e.key === "Escape") {
    if (!$("#modal").classList.contains("hidden")) { closeModal(); return; }
  }
  if (e.key === "/" && !typing) {
    e.preventDefault();
    const target = document.querySelector(".page.active input[type=search]") || $("#lib-q");
    if (target) target.focus();
    return;
  }
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
    const active = document.querySelector(".page.active");
    const btn = active && active.querySelector("button.primary");
    if (btn) { e.preventDefault(); btn.click(); }
  }
});

/* ------------------------------------------------------------------ 路由 */
const DEBUG = new URLSearchParams(location.search).has("debug");
if (DEBUG) {
  window.addEventListener("error", (e) => {
    document.title = "JSERR: " + (e.message || "unknown");
  });
  window.addEventListener("unhandledrejection", (e) => {
    document.title = "JSREJ: " + ((e.reason && e.reason.message) || e.reason || "unknown");
  });
}

const pages = ["home", "search", "sing", "train", "jobs", "library", "fix", "plan", "logs", "settings"];
function go(page) {
  if (!pages.includes(page)) return;
  $$("#nav a[data-page]").forEach((a) => a.classList.toggle("active", a.dataset.page === page));
  $$(".page").forEach((p) => p.classList.toggle("active", p.id === `page-${page}`));
  if (page === "jobs") loadJobs();
  if (page === "library") {
    const kindParam = new URLSearchParams(location.search).get("kind");
    const targetKind = kindParam && ["model", "song", "output", "source", "voice", "favorite"].includes(kindParam)
      ? kindParam : libKind;
    loadLibrary(targetKind, 1);
  }
  if (page === "fix") loadFix();
  if (page === "plan") { loadPlan(); loadCurrentPlan(); }
  if (page === "train") loadTrain();
  if (page === "logs") loadLogs();
  if (page === "settings") { loadSettings(); loadSendConfig(); }
  if (page === "home") {
    loadHome();
  }
  if (page === "search") loadProviders();
  location.hash = page;
}
$$("#nav a[data-page]").forEach((a) => a.addEventListener("click", () => go(a.dataset.page)));

/* ------------------------------------------------------------------ 首页 */
function metricCard(label, value, sub, ratio) {
  const card = el("div", "card metric");
  card.appendChild(el("div", "label", label));
  card.appendChild(el("div", "value", value));
  if (sub) card.appendChild(el("div", "sub", sub));
  if (ratio !== undefined && ratio !== null) {
    const meter = el("div", "meter" + (ratio > 0.9 ? " err" : ratio > 0.75 ? " warn" : ""));
    const bar = el("i");
    bar.style.width = `${Math.min(100, Math.round(ratio * 100))}%`;
    meter.appendChild(bar);
    card.appendChild(meter);
  }
  return card;
}

let metricsReady = false;
let metricsProbedAt = null;

async function refreshMetrics(force = false) {
  try {
    const res = await api(`/api/resources${force ? "?refresh=1" : ""}`);
    renderMetrics(res);
    metricsReady = true;
    metricsProbedAt = new Date();
    const stamp = $("#home-metrics-time");
    if (stamp) {
      const hh = String(metricsProbedAt.getHours()).padStart(2, "0");
      const mm = String(metricsProbedAt.getMinutes()).padStart(2, "0");
      stamp.textContent = `指标检测于今天 ${hh}:${mm}${force ? "（刚刷新）" : ""}`;
    }
    connFailures = 0;
    $("#conn").textContent = "已连接";
    $("#conn").style.color = "var(--ok)";
  } catch (err) {
    if (!(err && err.name === "AbortError")) connFailures += 1;
  }
}

function updateSetupRunHint() {
  const btn = $("#setup-run");
  const hint = $("#setup-run-hint");
  if (!btn) return;
  const enabled = !btn.disabled;
  if (hint) hint.textContent = enabled ? "检测完成，可以确认配置" : "先检测环境，再确认配置";
  btn.title = enabled ? "按检测结果写入配置" : "先点「检测环境」";
}

function renderMetricPlaceholders() {
  const box = $("#home-metrics");
  if (!box || box.children.length === 4) return;
  box.innerHTML = "";
  ["显存", "内存", "磁盘", "资源库"].forEach((label) => {
    const card = el("div", "card metric");
    card.appendChild(el("div", "label", label));
    card.appendChild(el("div", "value muted", "—"));
    card.appendChild(el("div", "sub", "未检测 · 点「检测环境」"));
    box.appendChild(card);
  });
}

function renderMetrics(res) {
  const box = $("#home-metrics");
  if (!box) return;
  const hasReal = box.children.length === 4 && box.querySelector(".value.muted") === null;
  if (hasReal) {
    updateMetrics(box, res);
    return;
  }
  box.innerHTML = "";
  const v = res.vram || {};
  const vramText = v.total_gb ? `${v.used_gb.toFixed(1)} / ${v.total_gb.toFixed(0)} G` : "无独显";
  box.appendChild(metricCard("显存", vramText, v.total_gb ? `空闲 ${v.free_gb.toFixed(1)} G` : "只能跑 CPU", v.total_gb ? v.used_gb / v.total_gb : null));
  const m = res.memory || {};
  box.appendChild(metricCard("内存", `${(m.total_gb || 0).toFixed(0)} G`, `可用 ${(m.available_gb || 0).toFixed(1)} G`,
    m.total_gb ? 1 - (m.available_gb || 0) / m.total_gb : null));
  const d = res.disk || {};
  box.appendChild(metricCard("磁盘", `${(d.free_gb || 0).toFixed(0)} G 空闲`, `${d.drive || ""}`, d.total_gb ? 1 - d.free_gb / d.total_gb : null));
  const lib = res.library || {};
  box.appendChild(metricCard("资源库", lib.total || "0B", `${lib.items || 0} 个文件`));
  updateMetrics(box, res);
}

async function loadHome() {
  // 指标默认不自动探测：没检测过就显示占位，等用户点「检测环境」/「刷新指标」
  if (metricsReady) {
    await refreshMetrics(false);
  } else {
    renderMetricPlaceholders();
    $("#conn").textContent = "未检测";
    $("#conn").style.color = "var(--text-3)";
  }

  try {
    const ob = await api("/api/onboarding");
    const steps = $("#home-steps");
    steps.innerHTML = "";
    $("#home-progress-text").textContent = `${ob.done}/${ob.total}${metricsReady ? "" : " · 指标未检测"}`;
    ob.steps.forEach((step, index) => {
      const node = el("div", "step" + (step.done ? " done" : ""));
      node.appendChild(el("div", "dot", step.done ? "✓" : String(index + 1)));
      const body = el("div", "body");
      body.appendChild(el("div", "title", step.title));
      body.appendChild(el("div", "desc", step.desc));
      if (!step.done && step.hint) body.appendChild(el("div", "hint", step.hint));
      node.appendChild(body);
      if (!step.done) {
        const btn = el("button", "small go", "去处理");
        btn.addEventListener("click", () => {
          const target = { doctor: "home", link: "home", plan: "plan", train: "library", search: "search" }[step.action] || "home";
          go(target);
          if (step.action === "link") autoLink();
        });
        node.appendChild(btn);
      }
      steps.appendChild(node);
    });
  } catch { /* ignore */ }

  try {
    const probe = await api("/api/probe");
    $("#home-probe").textContent = probe.summary;
  } catch { /* ignore */ }
}

/* 环境一键配置 */
let setupJobId = null;
let connFailures = 0;

let setupLoaded = false;

async function detectEnv() {
  const btn = $("#setup-detect");
  if (btn) btn.classList.add("loading");
  try {
    await Promise.all([loadSetup(true), refreshMetrics(true)]);
    toast("环境检测完成", "ok");
  } finally {
    if (btn) btn.classList.remove("loading");
  }
}

async function loadSetup(force = false) {
  const summary = $("#setup-summary");
  const box = $("#setup-steps");
  if (!summary) return;
  if (setupLoaded && !force) return;
  setupLoaded = true;
  summary.textContent = "检测中…";
  box.innerHTML = "";
  try {
    const sep = $("#setup-separation") ? $("#setup-separation").value : "auto";
    const data = await api(`/api/setup/plan?separation=${sep}${force ? "&refresh=1" : ""}`);
    const steps = data.steps.steps || [];
    const env = data.probe || {};
    const envBits = [];
    envBits.push(env.vram_gb ? `显卡 ${env.vram_gb}G` : "无独显");
    envBits.push(`磁盘剩 ${Math.round(env.disk_free_gb || 0)}G`);
    envBits.push(env.ffmpeg ? "ffmpeg 就绪" : "缺 ffmpeg");
    if (env.local_rvc) envBits.push("本机有 RVC");
    if (env.local_uvr) envBits.push("本机有 UVR");
    summary.textContent = `${envBits.join("｜")}　推荐方案：${data.plan ? data.plan.name : "无"}`;
    $("#setup-total").textContent = steps.length ? `共 ${steps.length} 步，约 ${(data.steps.total_mb / 1024).toFixed(1)}G` : "已配置好";
    if (data.steps.warning) $("#setup-hint").textContent = data.steps.warning;
    const runBtn = $("#setup-run");
    if (!steps.length) {
      runBtn.disabled = true;
      runBtn.textContent = "环境已就绪";
      updateSetupRunHint();
      return;
    }
    runBtn.disabled = false;
    updateSetupRunHint();
    steps.forEach((step) => {
      const row = el("div", "step");
      const body = el("div", "body");
      body.appendChild(el("div", "title", `${step.label}${step.size_mb ? `　${step.size_mb}MB` : ""}`));
      if (step.kind === "pip" && step.commands) body.appendChild(el("div", "desc", step.commands.slice(2).join(" ")));
      else if (step.kind === "download") body.appendChild(el("div", "desc", step.target || ""));
      if (step.note) body.appendChild(el("div", "hint", step.note));
      row.appendChild(body);
      box.appendChild(row);
    });
  } catch (err) {
    setupLoaded = false;
    summary.textContent = `检查失败：${err.message}`;
  }
}

async function runSetup() {
  const btn = $("#setup-run");
  btn.disabled = true;
  btn.classList.add("loading");
  try {
    const sep = $("#setup-separation") ? $("#setup-separation").value : "auto";
    const job = await api("/api/setup/run", { method: "POST", body: JSON.stringify({ separation: sep }) });
    setupJobId = job.id;
    $("#setup-progress").classList.remove("hidden");
    pollSetup();
  } catch (err) {
    toast(err.message, "err");
    btn.disabled = false;
    btn.classList.remove("loading");
  }
}

async function pollSetup() {
  if (!setupJobId) return;
  const job = await api(`/api/jobs/${setupJobId}`);
  const bar = $("#setup-progress .bar");
  const label = $("#setup-progress span");
  bar.style.width = `${Math.round((job.progress || 0) * 100)}%`;
  label.textContent = `${job.status}｜${job.message || ""}`;
  if (job.status === "succeeded") {
    $("#setup-progress").classList.add("hidden");
    toast("环境配置完成", "ok");
    const btn = $("#setup-run");
    btn.classList.remove("loading");
    btn.disabled = true;
    btn.textContent = "配置完成";
    updateSetupRunHint();
    loadSetup();
    loadHome();
    return;
  }
  if (job.status === "failed" || job.status === "cancelled") {
    $("#setup-progress").classList.add("hidden");
    toast(`配置失败：${job.error || job.message}`, "err");
    const btn = $("#setup-run");
    btn.classList.remove("loading");
    btn.disabled = false;
    updateSetupRunHint();
    return;
  }
  setTimeout(pollSetup, 1500);
}

function updateMetrics(box, res) {
  const cards = box.children;
  const v = res.vram || {};
  const m = res.memory || {};
  const d = res.disk || {};
  const lib = res.library || {};
  const values = [
    [v.total_gb ? `${v.used_gb.toFixed(1)} / ${v.total_gb.toFixed(0)} G` : "无独显", v.total_gb ? `空闲 ${v.free_gb.toFixed(1)} G` : "只能跑 CPU", v.total_gb ? v.used_gb / v.total_gb : null],
    [`${(m.total_gb || 0).toFixed(0)} G`, `可用 ${(m.available_gb || 0).toFixed(1)} G`, m.total_gb ? 1 - (m.available_gb || 0) / m.total_gb : null],
    [`${(d.free_gb || 0).toFixed(0)} G 空闲`, `${d.drive || ""}`, d.total_gb ? 1 - d.free_gb / d.total_gb : null],
    [lib.total || "0B", `${lib.items || 0} 个文件`, null],
  ];
  cards.forEach((card, index) => {
    const [value, sub, ratio] = values[index] || [];
    const valueEl = card.querySelector(".value");
    const subEl = card.querySelector(".sub");
    if (valueEl && value !== undefined) valueEl.textContent = value;
    if (subEl && sub !== undefined) subEl.textContent = sub;
    const meter = card.querySelector(".meter");
    if (meter && ratio !== null && ratio !== undefined) {
      meter.className = "meter" + (ratio > 0.9 ? " err" : ratio > 0.75 ? " warn" : "");
      const bar = meter.querySelector("i");
      if (bar) bar.style.width = `${Math.min(100, Math.round(ratio * 100))}%`;
    }
  });
}

async function autoLink() {
  try {
    const res = await api("/api/link", { method: "POST", body: "{}" });
    toast(res.ok ? "已识别本机 RVC / UVR" : "没找全，去配置里填路径", res.ok ? "ok" : "err");
    loadHome();
  } catch (err) { toast(`识别失败：${err.message}`, "err"); }
}

/* 一键翻唱 */
let oneclickJob = null;
async function runOneclick() {
  const query = $("#oneclick-input").value.trim();
  if (!query) { toast("先输个歌名", "err"); return; }
  $("#oneclick-result").innerHTML = "";
  try {
    const job = await api("/api/oneclick", {
      method: "POST",
      body: JSON.stringify({ query, full: $("#oneclick-full").checked }),
    });
    oneclickJob = job.id;
    $("#oneclick-progress").classList.remove("hidden");
    pollOneclick();
  } catch (err) { toast(err.message, "err"); }
}

async function pollOneclick() {
  if (!oneclickJob) return;
  const job = await api(`/api/jobs/${oneclickJob}`);
  const bar = $("#oneclick-progress .bar");
  const label = $("#oneclick-progress span");
  bar.style.width = `${Math.round((job.progress || 0) * 100)}%`;
  label.textContent = `${job.status}｜${job.message || ""}`;
  if (job.status === "succeeded") {
    $("#oneclick-progress").classList.add("hidden");
    renderSingResult($("#oneclick-result"), job.result || {});
    loadHome();
    return;
  }
  if (job.status === "failed" || job.status === "cancelled") {
    $("#oneclick-progress").classList.add("hidden");
    toast(`没成：${job.error || job.message}`, "err");
    return;
  }
  setTimeout(pollOneclick, 1500);
}

/* ------------------------------------------------------------------ 找歌 */
let enabledSources = ["bilibili", "netease", "qqmusic", "itunes"];
let providerMeta = {};

async function loadProviders() {
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

async function doSearch() {
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

/* ------------------------------------------------------------------ 翻唱 */
let singJobId = null;

async function startSing() {
  const payload = { input: $("#sing-input").value.trim(), song: $("#sing-song").value.trim() };
  if (!payload.input && !payload.song) { toast("先填文件、文件夹或歌名", "err"); return; }

  let plan;
  try {
    plan = await api("/api/sing/plan", { method: "POST", body: JSON.stringify(payload) });
  } catch (err) { toast(`读取失败：${err.message}`, "err"); return; }

  if (plan.kind === "folder") {
    if (!plan.tracks.length) { toast("文件夹里没找到音频文件", "err"); return; }
    showTrackPicker(plan);
    return;
  }
  if (plan.kind === "file") {
    showTrackPicker({ ...plan, hint: "确认是这首就开始" });
    return;
  }
  submitSing({ input: payload.song || payload.input, name: $("#sing-name").value.trim() });
}

function showTrackPicker(plan) {
  const list = el("div", "steps");
  const boxes = [];
  plan.tracks.forEach((track) => {
    const row = el("label", "step");
    const cb = el("input");
    cb.type = "checkbox";
    cb.checked = true;
    cb.style.marginTop = "6px";
    boxes.push({ cb, track });
    row.appendChild(cb);
    const body = el("div", "body");
    body.appendChild(el("div", "title", track.name));
    const info = [track.duration ? `${track.duration}s` : null, track.size_mb ? `${track.size_mb}MB` : null, track.path]
      .filter(Boolean).join(" · ");
    body.appendChild(el("div", "desc", info));
    row.appendChild(body);
    list.appendChild(row);
  });

  const allBtn = el("button", "small", "全选");
  allBtn.addEventListener("click", () => boxes.forEach((b) => { b.cb.checked = true; update(); }));
  const noneBtn = el("button", "small ghost", "全不选");
  noneBtn.addEventListener("click", () => boxes.forEach((b) => { b.cb.checked = false; update(); }));
  const goBtn = el("button", "primary", "");
  const update = () => {
    const n = boxes.filter((b) => b.cb.checked).length;
    goBtn.textContent = `开始翻唱（已选 ${n} 首）`;
    goBtn.disabled = n === 0;
  };
  boxes.forEach((b) => b.cb.addEventListener("change", update));
  update();
  goBtn.addEventListener("click", () => {
    const chosen = boxes.filter((b) => b.cb.checked).map((b) => b.track);
    closeModal();
    submitTracks(chosen);
  });

  openModal(plan.kind === "folder" ? "这个文件夹里有这些曲目" : "确认要翻唱这首", [
    plan.hint ? el("p", "muted", plan.hint) : el("p"),
    list,
  ], [allBtn, noneBtn, el("span", "muted", "选好后点右边开始"), goBtn]);
}

async function submitTracks(tracks) {
  $("#sing-result").innerHTML = "";
  try {
    const job = await api("/api/sing/tracks", {
      method: "POST",
      body: JSON.stringify({ tracks, full: $("#sing-full").checked, force: $("#sing-force").checked }),
    });
    singJobId = job.id;
    $("#sing-progress").classList.remove("hidden");
    pollSing();
  } catch (err) { toast(`提交失败：${err.message}`, "err"); }
}

async function submitSing(payload) {
  $("#sing-result").innerHTML = "";
  try {
    const job = await api("/api/sing", {
      method: "POST",
      body: JSON.stringify({
        ...payload,
        name: payload.name || $("#sing-name").value.trim(),
        full: $("#sing-full").checked,
        force: $("#sing-force").checked,
      }),
    });
    singJobId = job.id;
    $("#sing-progress").classList.remove("hidden");
    pollSing();
  } catch (err) { toast(`提交失败：${err.message}`, "err"); }
}

async function pollSing() {
  if (!singJobId) return;
  const job = await api(`/api/jobs/${singJobId}`);
  const bar = $("#sing-progress .bar");
  const label = $("#sing-progress span");
  bar.style.width = `${Math.round((job.progress || 0) * 100)}%`;
  label.textContent = `${job.status}｜${job.message || ""}`;
  if (job.status === "succeeded") {
    $("#sing-progress").classList.add("hidden");
    renderSingResult($("#sing-result"), job.result || {});
    return;
  }
  if (job.status === "failed" || job.status === "cancelled") {
    $("#sing-progress").classList.add("hidden");
    toast(`没成：${job.error || job.message}`, "err");
    return;
  }
  setTimeout(pollSing, 1200);
}

function renderSingResult(box, result) {
  box.innerHTML = "";
  const files = [];
  if (result.parts && result.parts.length) files.push(...result.parts);
  if (result.final) files.push(result.final);
  (result.tracks || []).forEach((t) => {
    if (t.final) files.push(t.final);
    if (t.parts) files.push(...t.parts);
  });
  if (!files.length) {
    box.appendChild(el("div", "empty", "没有产物，去「任务」看看日志"));
    return;
  }
  files.forEach((file, index) => {
    const card = el("div", "card");
    card.appendChild(el("h3", null, `成品 ${index + 1}/${files.length}`));
    const audio = el("audio");
    audio.controls = true;
    audio.src = `/api/audio?path=${encodeURIComponent(file)}`;
    card.appendChild(audio);
    card.appendChild(el("div", "muted", file));
    box.appendChild(card);
  });
}

/* ------------------------------------------------------------------ 任务 */
async function loadJobs() {
  const data = await api("/api/jobs");
  const tbody = $("#jobs-table tbody");
  tbody.innerHTML = "";
  $("#jobs-count").textContent = `共 ${data.jobs.length} 个`;
  data.jobs.forEach((job) => {
    const tr = el("tr");
    tr.appendChild(el("td", null, job.label));
    const status = el("td");
    const cls = job.status === "succeeded" ? "ok" : job.status === "failed" ? "err" : job.status === "cancelled" ? "" : "run";
    status.appendChild(el("span", "pill " + cls, job.status));
    tr.appendChild(status);
    tr.appendChild(el("td", null, `${Math.round((job.progress || 0) * 100)}%`));
    tr.appendChild(el("td", null, job.message || ""));
    const seconds = job.ended_at && job.started_at ? Math.round(job.ended_at - job.started_at)
      : job.started_at ? Math.round(Date.now() / 1000 - job.started_at) : 0;
    tr.appendChild(el("td", null, seconds ? `${seconds}s` : "-"));
    const actionCell = el("td");
    if (["queued", "running"].includes(job.status)) {
      const cancel = el("button", "small ghost", "取消");
      cancel.addEventListener("click", async (e) => {
        e.stopPropagation();
        cancel.disabled = true;
        await api(`/api/jobs/${job.id}/cancel`, { method: "POST", body: "{}" });
        toast("已请求取消", "ok");
        loadJobs();
      });
      actionCell.appendChild(cancel);
    }
    tr.appendChild(actionCell);
    tr.addEventListener("click", async () => {
      const text = await fetch(`/api/jobs/${job.id}/log`).then((r) => r.text());
      $("#job-log").textContent = text || "（没有日志）";
    });
    tbody.appendChild(tr);
  });
}

function watchJob(jobId, kind) {
  const timer = setInterval(async () => {
    try {
      const job = await api(`/api/jobs/${jobId}`);
      if (job.status === "succeeded") {
        clearInterval(timer);
        toast("任务完成", "ok");
        if (kind === "sing") {
          singJobId = jobId;
          $("#sing-progress").classList.remove("hidden");
          renderSingResult($("#sing-result"), job.result || {});
        }
        loadHome();
      } else if (job.status === "failed" || job.status === "cancelled") {
        clearInterval(timer);
        toast(`任务结束：${job.error || job.status}`, "err");
      }
    } catch { /* ignore */ }
  }, 2000);
}

/* ------------------------------------------------------------------ 资源库 */
let libKind = "model";
let libPage = 1;
let libPages = 1;
let libSelected = new Set();

async function loadLibrary(kind, page) {
  libKind = kind || libKind;
  libPage = page || 1;
  libSelected = new Set();
  $$("#page-library button[data-kind]").forEach((b) => b.classList.toggle("active", b.dataset.kind === libKind));
  const q = $("#lib-q").value.trim();
  const size = Number($("#lib-size").value) || 20;
  if (libKind !== "voice") {
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

  if (libKind === "voice") {
    renderVoices(tbody);
    $("#lib-summary").textContent = "训练完成后会自动登记新版本；切回旧版不影响已有成品。";
    $("#page-info").textContent = "";
    return;
  }

  let items = [];
  let total = 0;
  if (libKind === "favorite") {
    const data = await api("/api/library/favorites");
    items = data.items;
    total = items.length;
    libPages = 1;
  } else {
    const data = await api(`/api/library?kind=${libKind}&q=${encodeURIComponent(q)}&page=${libPage}&size=${size}`);
    items = data.items;
    total = data.total;
    libPages = data.pages;
    libPage = data.page;
  }

  const infoEl = $("#page-info");
  const summaryEl = $("#lib-summary");
  if (infoEl) infoEl.textContent = `第 ${libPage} / ${libPages} 页`;
  if (summaryEl) summaryEl.textContent = `共 ${total} 个文件（本页 ${items.length} 个）`;

  tbody.innerHTML = "";
  items.forEach((item) => {
    try {
      tbody.appendChild(libRow(item));
    } catch (err) {
      if (summaryEl) summaryEl.textContent += `  [行渲染出错：${err.message}]`;
    }
  });
  $("#page-prev").disabled = libPage <= 1;
  $("#page-next").disabled = libPage >= libPages;
  $("#page-jump").value = libPage;
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
    if (cb.checked) libSelected.add(item.path); else libSelected.delete(item.path);
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
    loadLibrary(libKind, libPage);
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
    loadLibrary(libKind, libPage);
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

function updateBatchBar() {
  const bar = $("#lib-batch");
  const count = libSelected.size;
  $("#lib-selected-text").textContent = `已选 ${count} 项`;
  bar.classList.toggle("hidden", count === 0);
}

async function batchAction(action, extra = {}) {
  const paths = [...libSelected];
  if (!paths.length) return;
  if (action === "delete" && !confirm(`删除这 ${paths.length} 项？会挪到 work/_trash。`)) return;
  await api("/api/library/batch", {
    method: "POST",
    body: JSON.stringify({ action, paths, ...extra }),
  });
  toast(`已处理 ${paths.length} 项`, "ok");
  loadLibrary(libKind, libPage);
}

async function scanLibrary() {
  const job = await api("/api/library/scan", { method: "POST", body: "{}" });
  toast("正在重建索引", "ok");
  watchJob(job.id, null);
}
/* ------------------------------------------------------------------ 诊断 */
let fixJobId = null;
let recipeCache = null;
let fixSelection = {};

async function loadFix() {
  const recipes = await api("/api/recipes");
  recipeCache = recipes;
  const symptom = $("#fix-symptom");
  if (!symptom.options.length) {
    recipes.recipes.forEach((item) => {
      const opt = el("option", null, item.symptom);
      opt.value = item.id;
      symptom.appendChild(opt);
    });
  }
  const songs = await api("/api/library?kind=song");
  const songBox = $("#fix-song");
  if (!songBox.options.length) {
    songs.items.forEach((item) => {
      const opt = el("option", null, item.name);
      opt.value = item.name;
      songBox.appendChild(opt);
    });
  }
  renderFixOptions();
}

function renderFixOptions() {
  if (!recipeCache) return;
  const current = $("#fix-symptom").value;
  const item = recipeCache.recipes.find((r) => r.id === current) || recipeCache.recipes[0];
  const box = $("#fix-options");
  box.innerHTML = "";
  if (!item) return;
  fixSelection = {};
  item.options.forEach((opt) => {
    const row = el("label", "step");
    const cb = el("input");
    cb.type = "checkbox";
    cb.checked = opt.id === item.selected;
    cb.style.marginTop = "6px";
    fixSelection[opt.id] = cb;
    row.appendChild(cb);
    const body = el("div", "body");
    const marks = [];
    if (opt.id === item.selected && !String(opt.name).includes("推荐")) marks.push("推荐");
    if (opt.experimental) marks.push("实验性");
    body.appendChild(el("div", "title", opt.name + (marks.length ? `（${marks.join("、")}）` : "")));
    body.appendChild(el("div", "desc", opt.how || ""));
    body.appendChild(el("div", "hint", `代价 ${opt.cost || "?"}｜风险 ${opt.risk || "?"}`));
    if (opt.evidence) body.appendChild(el("div", "muted", "证据：" + opt.evidence));
    row.appendChild(body);
    box.appendChild(row);
  });
  $("#fix-results").innerHTML = "";
}

async function runFix() {
  const chosen = Object.entries(fixSelection).filter(([, cb]) => cb.checked).map(([id]) => id);
  if (!chosen.length) { toast("至少选一个解法", "err"); return; }
  const payload = {
    song: $("#fix-song").value,
    symptom: $("#fix-symptom").value,
    recipes: chosen,
    seconds: Number($("#fix-seconds").value) || 60,
  };
  try {
    const job = await api("/api/fix", { method: "POST", body: JSON.stringify(payload) });
    fixJobId = job.id;
    $("#fix-progress").classList.remove("hidden");
    pollFix();
  } catch (err) { toast(err.message, "err"); }
}

async function pollFix() {
  if (!fixJobId) return;
  const job = await api(`/api/jobs/${fixJobId}`);
  const bar = $("#fix-progress .bar");
  const label = $("#fix-progress span");
  bar.style.width = `${Math.round((job.progress || 0) * 100)}%`;
  label.textContent = `${job.status}｜${job.message || ""}`;
  if (job.status === "succeeded") {
    $("#fix-progress").classList.add("hidden");
    renderFixResults(job.result || {});
    return;
  }
  if (job.status === "failed" || job.status === "cancelled") {
    $("#fix-progress").classList.add("hidden");
    toast(`失败：${job.error || job.message}`, "err");
    return;
  }
  setTimeout(pollFix, 1500);
}

function renderFixResults(result) {
  const box = $("#fix-results");
  box.innerHTML = "";
  (result.outputs || []).forEach((item) => {
    const card = el("div", "plan" + (item.id === result.recommended ? " best" : ""));
    const title = el("h4", null, item.name);
    if (item.id === result.recommended) title.appendChild(el("span", "badge", "推荐"));
    if (item.experimental) title.appendChild(el("span", "tag", "实验性"));
    card.appendChild(title);
    card.appendChild(el("div", "muted", item.how || ""));
    card.appendChild(el("div", "kv", `代价 ${item.cost || "?"}｜风险 ${item.risk || "?"}`));
    const audio = el("audio");
    audio.controls = true;
    audio.src = `/api/audio?path=${encodeURIComponent(item.path)}`;
    card.appendChild(audio);
    const adopt = el("button", "small" + (item.id === result.recommended ? " primary" : ""), "用这个");
    adopt.addEventListener("click", async () => {
      await api("/api/fix/adopt", {
        method: "POST",
        body: JSON.stringify({
          song: $("#fix-song").value,
          symptom: result.symptom,
          recipe: item.id,
          candidates: (result.outputs || []).map((o) => o.id),
        }),
      });
      adopt.textContent = "已记录";
      adopt.disabled = true;
      toast("已记下这个选择", "ok");
    });
    card.appendChild(adopt);
    box.appendChild(card);
  });
}

/* ------------------------------------------------------------------ 方案 */
async function showAllPlans() {
  let data;
  try {
    data = await api("/api/plans/available");
  } catch (err) {
    toast(err.message, "err");
    return;
  }
  const box = el("div");
  data.plans.forEach((plan) => {
    const row = el("div", "step");
    const body = el("div", "body");
    body.appendChild(el("div", "title", plan.name));
    body.appendChild(el("div", "desc", plan.id));
    row.appendChild(body);
    box.appendChild(row);
  });
  const applyBtn = el("button", "primary", "用这套参数");
  applyBtn.addEventListener("click", () => {
    $("#prefer").value = "stability";
    closeModal();
    loadPlan();
  });
  const closeBtn = el("button", "ghost", "关闭");
  closeBtn.addEventListener("click", closeModal);
  openModal("全部方案", [box], [closeBtn, applyBtn]);
}

async function loadPlan() {
  const params = new URLSearchParams({
    prefer: $("#prefer").value,
    train: $("#will-train").value,
    disk: $("#disk").value,
    patience: $("#patience").value,
    max_vram: $("#max-vram").value,
  });
  const box = $("#plan-cards");
  box.innerHTML = "<div class='empty'>正在体检并推荐…</div>";
  try {
    const data = await api(`/api/plan?${params.toString()}`);
    box.innerHTML = "";
    if (!data.plans.length) {
      box.appendChild(el("div", "empty", "没有匹配的方案，放宽显存预算或等待时间试试"));
      return;
    }
    data.plans.forEach((item) => box.appendChild(planCard(item)));
    renderAssets(data.assets);
    const excludedBox = $("#excluded-box");
    const excludedList = $("#excluded-list");
    excludedList.innerHTML = "";
    if (data.excluded && data.excluded.length) {
      excludedBox.classList.remove("hidden");
      data.excluded.forEach((x) => {
        const row = el("div", null, `${x.id}：${x.reason}`);
        excludedList.appendChild(row);
      });
    } else {
      excludedBox.classList.add("hidden");
    }
  } catch (err) {
    box.innerHTML = "";
    box.appendChild(el("div", "empty", `推荐失败：${err.message}`));
  }
}

async function loadCurrentPlan() {
  try {
    const data = await api("/api/plan/current");
    const plan = data.plan;
    $("#current-plan").textContent = plan ? `当前方案：${plan.name || plan.id}（${plan.applied_at || ""}）` : "当前方案：未设置";
  } catch { /* ignore */ }
}

function renderAssets(assets) {
  const box = $("#assets-list");
  const summary = $("#assets-summary");
  box.innerHTML = "";
  if (!assets) {
    if (summary) summary.textContent = "这套方案还要准备什么？";
    return;
  }
  const bundle = assets.bundle || {};
  const total = (assets.total_mb || 0) / 1024;
  if (summary) {
    summary.textContent = assets.items && assets.items.length
      ? `还要准备 ${assets.items.length} 个文件，约 ${total.toFixed(1)}G（${bundle.label || ""}）`
      : `不需要额外下载（${bundle.label || "复用本机环境"}）`;
  }
  if (assets.note) box.appendChild(el("div", "muted", assets.note));
  (assets.items || []).forEach((item) => {
    const row = el("div", "step");
    const body = el("div", "body");
    body.appendChild(el("div", "title", `${item.label}　${item.size_mb}MB`));
    if (item.source) body.appendChild(el("div", "desc", item.source));
    if (item.note) body.appendChild(el("div", "hint", item.note));
    row.appendChild(body);
    box.appendChild(row);
  });
  if (assets.warning) box.appendChild(el("div", "hint", assets.warning));
  if (assets.needs_pip && assets.needs_pip.length) {
    box.appendChild(el("div", "muted", `pip 需要装：${assets.needs_pip.join("、")}`));
  }
}

function planCard(item) {
  const p = item.plan || {};
  const est = p.estimate || {};
  const sep = (p.params || {}).separate || {};
  const conv = (p.params || {}).convert || {};
  const train = (p.params || {}).train || {};
  const card = el("div", "plan" + (item.recommended ? " best" : ""));
  const title = el("h4", null, item.name);
  if (item.recommended) title.appendChild(el("span", "badge", "推荐"));
  card.appendChild(title);
  card.appendChild(el("div", "kv", `分离 ${sep.local_model || sep.model || "-"}｜转换 ${(conv.backend || "").toUpperCase()}`));
  card.appendChild(el("div", "kv", `${train.epochs ? `训练 ${train.epochs} 轮约 ${est.train_minutes} 分钟` : "不训练"}｜单曲约 ${est.per_song_minutes} 分钟`));
  card.appendChild(el("div", "kv", `显存峰值 ${est.vram_peak_gb}G｜每首占盘 ${est.disk_per_song_mb}MB`));
  if (p.explain) card.appendChild(el("div", "muted", p.explain));
  const list = el("ul");
  (p.pros || []).forEach((t) => list.appendChild(el("li", "pro", "＋ " + t)));
  (p.cons || []).forEach((t) => list.appendChild(el("li", "con", "－ " + t)));
  (item.notes || []).forEach((t) => list.appendChild(el("li", null, "· " + t)));
  card.appendChild(list);
  const actions = el("div", "actions");
  const btn = el("button", item.recommended ? "primary" : "", "用这套");
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    btn.textContent = "写入中…";
    try {
      await api("/api/plan/apply", { method: "POST", body: JSON.stringify({ id: item.id }) });
      btn.textContent = "已写入";
      toast("配置已更新", "ok");
      loadCurrentPlan();
      loadHome();
    } catch (err) {
      btn.textContent = "失败";
      toast(err.message, "err");
    }
  });
  actions.appendChild(btn);
  card.appendChild(actions);
  return card;
}

/* ------------------------------------------------------------------ 选文件夹 */
/* ------------------------------------------------------------------ 日志 */
let logFiles = [];

async function loadLogs() {
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

async function showLog(name) {
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

/* ------------------------------------------------------------------ 选文件夹（页内浏览器） */
async function openPicker(selector, title, mode = "dir", ext = "") {
  const input = $(selector);
  if (!input) return;
  const start = input.value.trim();

  const body = el("div");
  const pathLine = el("div", "row");
  const pathInput = el("input");
  pathInput.type = "text";
  pathInput.style.flex = "1";
  pathInput.placeholder = "C:\\ 或 D:\\某个目录";
  const upBtn = el("button", "small ghost", "上一级");
  const sysBtn = el("button", "small ghost", "用系统对话框");
  pathLine.appendChild(pathInput);
  pathLine.appendChild(upBtn);
  pathLine.appendChild(sysBtn);
  body.appendChild(pathLine);

  const list = el("div", "steps");
  list.style.maxHeight = "46vh";
  list.style.overflow = "auto";
  body.appendChild(list);

  const state = { path: start, parent: null };

  const render = async (path) => {
    list.innerHTML = "";
    let data;
    try {
      data = await api(`/api/fs/list?path=${encodeURIComponent(path || "")}${ext ? "&ext=" + ext : ""}`);
    } catch (err) {
      list.appendChild(el("div", "hint", err.message));
      return;
    }
    if (data.error) {
      list.appendChild(el("div", "hint", data.error));
      return;
    }
    state.path = data.path;
    state.parent = data.parent;
    pathInput.value = data.path || "";
    upBtn.disabled = !data.parent;

    (data.dirs || []).forEach((dir) => {
      const row = el("div", "step");
      const bodyCell = el("div", "body");
      bodyCell.appendChild(el("div", "title", dir.name));
      row.appendChild(bodyCell);
      row.style.cursor = "pointer";
      row.addEventListener("click", () => render(dir.path));
      list.appendChild(row);
    });
    (data.files || []).forEach((file) => {
      const row = el("div", "step");
      const bodyCell = el("div", "body");
      bodyCell.appendChild(el("div", "title", file.name));
      bodyCell.appendChild(el("div", "desc", `${file.size_mb} MB`));
      row.appendChild(bodyCell);
      row.style.cursor = "pointer";
      row.addEventListener("click", () => {
        input.value = file.path;
        input.dispatchEvent(new Event("change", { bubbles: true }));
        closeModal();
        toast("已选择文件", "ok");
      });
      list.appendChild(row);
    });
    if (!(data.dirs || []).length && !(data.files || []).length) {
      list.appendChild(el("div", "muted", "这个目录是空的"));
    }
  };

  upBtn.addEventListener("click", () => { if (state.parent) render(state.parent); });
  pathInput.addEventListener("keydown", (e) => { if (e.key === "Enter") render(pathInput.value.trim()); });
  sysBtn.addEventListener("click", async () => {
    try {
      const res = await api("/api/pick-folder", {
        method: "POST",
        body: JSON.stringify({ title: title || "选择文件夹", initial: state.path || "" }),
      });
      if (!res.ok) { toast(res.error || "系统对话框打不开", "err"); return; }
      if (res.cancelled) return;
      input.value = res.path;
      input.dispatchEvent(new Event("change", { bubbles: true }));
      closeModal();
      toast("已选择", "ok");
    } catch (err) {
      toast(err.message, "err");
    }
  });

  const chooseBtn = el("button", "primary", mode === "file" ? "选这个目录" : "选择此文件夹");
  chooseBtn.addEventListener("click", () => {
    if (!state.path) { toast("先进到某个目录", "err"); return; }
    input.value = state.path;
    input.dispatchEvent(new Event("change", { bubbles: true }));
    closeModal();
    toast("已选择", "ok");
  });
  const cancelBtn = el("button", "ghost small", "取消");
  cancelBtn.addEventListener("click", closeModal);

  openModal(title || "选择文件夹", [body], [cancelBtn, chooseBtn]);
  await render(start);
}

/* ------------------------------------------------------------------ 发布与备份 */
async function loadSendConfig() {
  try {
    const data = await api("/api/settings");
    const send = data.send || {};
    $("#set-send-enabled").checked = !!send.enabled;
    $("#set-send-target").value = send.target || "";
    $("#set-send-account").value = send.account || "main";
  } catch { /* 忽略 */ }
}

async function saveSendConfig() {
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

async function startBackup() {
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

/* ------------------------------------------------------------------ 训练 */
let trainJobId = null;

async function previewTrain() {
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

async function startTrain() {
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

async function importModel() {
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

async function loadTrain() {
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

function fillTemplate(kind) {
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

async function saveTrainConfig() {
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

/* ------------------------------------------------------------------ 设置 */
async function loadSettings() {
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

async function saveSettings() {
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

/* ------------------------------------------------------------------ 选文件夹：事件委托 */
// 用 document 级委托，按钮后加/重渲染都不影响
document.addEventListener("click", (event) => {
  const btn = event.target.closest("[data-pick]");
  if (!btn) return;
  event.preventDefault();
  openPicker(btn.dataset.pick, btn.dataset.title || "选择文件夹");
});
window.openPicker = openPicker;

/* ------------------------------------------------------------------ 主题 */
const THEMES = ["auto", "light", "dark"];
const THEME_LABEL = { auto: "主题：跟随系统", light: "主题：宣纸", dark: "主题：墨" };

function applyTheme(mode) {
  const root = document.documentElement;
  if (mode === "auto") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", mode);
  const btn = $("#theme-toggle");
  if (btn) btn.textContent = THEME_LABEL[mode] || THEME_LABEL.auto;
  try { localStorage.setItem("cover-theme", mode); } catch (err) { /* 隐私模式忽略 */ }
}

function currentTheme() {
  const param = new URLSearchParams(location.search).get("theme");
  if (param && THEMES.includes(param)) return param;
  try { return localStorage.getItem("cover-theme") || "auto"; } catch (err) { return "auto"; }
}

const themeBtn = $("#theme-toggle");
if (themeBtn) {
  applyTheme(currentTheme());
  themeBtn.addEventListener("click", () => {
    const next = THEMES[(THEMES.indexOf(currentTheme()) + 1) % THEMES.length];
    applyTheme(next);
  });
}

/* ------------------------------------------------------------------ 绑定 */
$("#oneclick-go").addEventListener("click", runOneclick);
$("#setup-detect").addEventListener("click", detectEnv);
$("#setup-run").addEventListener("click", runSetup);
// 训练页 / 设置页按钮绑定（on() 包一层，元素不存在也不报错）
function on(id, handler) {
  const node = $(id);
  if (node) node.addEventListener("click", handler);
}
on("#train-preview-btn", previewTrain);
on("#train-start", startTrain);
on("#train-save-config", saveTrainConfig);
on("#train-fill-rvc", () => fillTemplate("rvc"));
on("#train-fill-own", () => fillTemplate("own"));
on("#set-save", saveSettings);
on("#set-send-save", saveSendConfig);
on("#set-backup", startBackup);
on("#log-refresh", loadLogs);
$("#log-file").addEventListener("change", (e) => showLog(e.target.value));
$("#log-lines").addEventListener("change", () => showLog($("#log-file").value));
on("#plan-all", showAllPlans);
on("#train-import", importModel);
on("#set-reset", loadSettings);

$("#metrics-refresh").addEventListener("click", async () => {
  await refreshMetrics(true);
  toast("指标已刷新", "ok");
});
$("#oneclick-input").addEventListener("keydown", (e) => { if (e.key === "Enter") runOneclick(); });
$("#search-go").addEventListener("click", doSearch);
$("#search-input").addEventListener("keydown", (e) => { if (e.key === "Enter") doSearch(); });
$("#search-hint").addEventListener("click", () => { $("#search-input").value = "千年食谱颂"; doSearch(); });
$("#sing-start").addEventListener("click", startSing);
$("#jobs-refresh").addEventListener("click", loadJobs);
$("#lib-scan").addEventListener("click", scanLibrary);
$("#lib-q").addEventListener("input", () => loadLibrary(libKind, 1));
$("#lib-size").addEventListener("change", () => loadLibrary(libKind, 1));
$$("#page-library button[data-kind]").forEach((b) => b.addEventListener("click", () => loadLibrary(b.dataset.kind, 1)));
$("#page-prev").addEventListener("click", () => loadLibrary(libKind, Math.max(1, libPage - 1)));
$("#page-next").addEventListener("click", () => loadLibrary(libKind, Math.min(libPages, libPage + 1)));
$("#page-go").addEventListener("click", () => {
  const target = Number($("#page-jump").value) || 1;
  loadLibrary(libKind, Math.min(libPages, Math.max(1, target)));
});
$("#lib-all").addEventListener("change", (e) => {
  $$("#lib-table tbody input[type=checkbox]").forEach((cb) => {
    cb.checked = e.target.checked;
    cb.dispatchEvent(new Event("change"));
  });
});
$("#lib-fav").addEventListener("click", () => batchAction("favorite", { on: true }));
$("#lib-unfav").addEventListener("click", () => batchAction("favorite", { on: false }));
$("#lib-del").addEventListener("click", () => batchAction("delete"));
$("#lib-clear").addEventListener("click", () => {
  libSelected = new Set();
  $$("#lib-table tbody input[type=checkbox]").forEach((cb) => { cb.checked = false; });
  $("#lib-all").checked = false;
  updateBatchBar();
});
$("#fix-run").addEventListener("click", runFix);
$("#fix-symptom").addEventListener("change", renderFixOptions);
$("#load-plan").addEventListener("click", loadPlan);
$("#clear-plan").addEventListener("click", async () => {
  if (!confirm("把方案参数恢复成默认值？")) return;
  await api("/api/plan/clear", { method: "POST", body: "{}" });
  toast("已恢复默认", "ok");
  loadCurrentPlan();
  loadHome();
});

(async function boot() {
  try {
    const health = await api("/api/health");
    $("#foot-version").textContent = `v${health.version}`;
  } catch { /* ignore */ }
  const initial = location.hash.replace("#", "");
  go(pages.includes(initial) ? initial : "home");
  const kindParam = new URLSearchParams(location.search).get("kind");
  if (kindParam && pages.includes("library")) { /* 允许 ?kind=voice 直达资源库分类 */ }

  // 调试用：?autoclick=[data-pick="#set-work"] 载入后自动点一下
  const autoClick = new URLSearchParams(location.search).get("autoclick");
  if (autoClick) {
    const target = document.querySelector(autoClick);
    if (target) target.click();
  }

  const pickTarget = new URLSearchParams(location.search).get("pick");
  if (pickTarget) openPicker("#" + pickTarget, "选择文件夹");
  const preset = new URLSearchParams(location.search).get("q");
  if (preset) {
    $("#search-input").value = preset;
    go("search");
    doSearch();
  }
})();
