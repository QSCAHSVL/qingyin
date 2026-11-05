/* 任务：列表、日志尾巴、重跑 */

import { $, api, el, toast } from "../core.js";
import { loadHome } from "../pages/home.js";
import { renderSingResult, setSingJobId } from "../pages/sing.js";

/* ------------------------------------------------------------------ 任务 */
export async function loadJobs() {
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

export function watchJob(jobId, kind) {
  const timer = setInterval(async () => {
    try {
      const job = await api(`/api/jobs/${jobId}`);
      if (job.status === "succeeded") {
        clearInterval(timer);
        toast("任务完成", "ok");
        if (kind === "sing") {
          setSingJobId(jobId);
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
