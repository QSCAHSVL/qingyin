/* 诊断：症状选择、方案对比、结果渲染 */

import { $, api, el, toast } from "../core.js";

/* ------------------------------------------------------------------ 诊断 */
let fixJobId = null;
let recipeCache = null;
let fixSelection = {};

export async function loadFix() {
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

export function renderFixOptions() {
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

export async function runFix() {
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
