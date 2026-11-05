/* 入口：import 各页面模块 + 绑定所有按钮事件 + 启动 */

import { $, $$, api, on, toast } from "./core.js";
import { go } from "./nav.js";
import { pages } from "./router.js";
import { loadHome, detectEnv, refreshMetrics, runSetup, runOneclick } from "./pages/home.js";
import { doSearch } from "./pages/search.js";
import { startSing } from "./pages/sing.js";
import { loadJobs } from "./pages/jobs.js";
import { loadLibrary, scanLibrary, batchAction, updateBatchBar, libState } from "./pages/library.js";
import { runFix, renderFixOptions } from "./pages/fix.js";
import { loadPlan, loadCurrentPlan, showAllPlans } from "./pages/plan.js";
import { loadLogs, showLog } from "./pages/logs.js";
import { loadSettings, saveSettings, loadSendConfig, saveSendConfig, startBackup } from "./pages/settings.js";
import { loadTrain, previewTrain, startTrain, saveTrainConfig, fillTemplate, importModel } from "./pages/train.js";
import { openPicker } from "./ui/picker.js";

/* ------------------------------------------------------------------ 绑定 */
$("#oneclick-go").addEventListener("click", runOneclick);
$("#setup-detect").addEventListener("click", detectEnv);
$("#setup-run").addEventListener("click", runSetup);
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
$("#lib-q").addEventListener("input", () => loadLibrary(libState.kind, 1));
$("#lib-size").addEventListener("change", () => loadLibrary(libState.kind, 1));
$$("#page-library button[data-kind]").forEach((b) => b.addEventListener("click", () => loadLibrary(b.dataset.kind, 1)));
$("#page-prev").addEventListener("click", () => loadLibrary(libState.kind, Math.max(1, libState.page - 1)));
$("#page-next").addEventListener("click", () => loadLibrary(libState.kind, Math.min(libState.pages, libState.page + 1)));
$("#page-go").addEventListener("click", () => {
  const target = Number($("#page-jump").value) || 1;
  loadLibrary(libState.kind, Math.min(libState.pages, Math.max(1, target)));
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
  libState.selected = new Set();
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
