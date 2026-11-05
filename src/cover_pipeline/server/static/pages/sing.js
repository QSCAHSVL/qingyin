/* 翻唱：参数、分轨确认、任务轮询、结果渲染 */

import { $, api, closeModal, el, openModal, toast } from "../core.js";

/* ------------------------------------------------------------------ 翻唱 */
let singJobId = null;

export async function startSing() {
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

export function renderSingResult(box, result) {
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


/* 任务页 watchJob 完成后要把「当前翻唱任务」写回来：走 setter，别跨模块改 let */
export function setSingJobId(value) { singJobId = value; }
