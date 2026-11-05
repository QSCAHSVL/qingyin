/* 方案：推荐、应用、撤销、组件安装 */

import { $, api, closeModal, el, openModal, toast } from "../core.js";
import { loadHome } from "../pages/home.js";

/* ------------------------------------------------------------------ 方案 */
export async function showAllPlans() {
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

export async function loadPlan() {
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

export async function loadCurrentPlan() {
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
