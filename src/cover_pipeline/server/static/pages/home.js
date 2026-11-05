/* 首页：环境指标、一键配置、一键翻唱 */

import { $, api, el, net, toast } from "../core.js";
import { go } from "../nav.js";
import { renderSingResult } from "../pages/sing.js";

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

export async function refreshMetrics(force = false) {
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
    net.connFailures = 0;
    $("#conn").textContent = "已连接";
    $("#conn").style.color = "var(--ok)";
  } catch (err) {
    if (!(err && err.name === "AbortError")) net.connFailures += 1;
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

export async function loadHome() {
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

let setupLoaded = false;

export async function detectEnv() {
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

export async function runSetup() {
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
export async function runOneclick() {
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
