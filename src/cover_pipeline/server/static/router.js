/* 页面路由：hash 切换、导航高亮、按页触发首次加载 */

import { $$ } from "./core.js";
import { setNavigator } from "./nav.js";
import { loadHome } from "./pages/home.js";
import { loadProviders } from "./pages/search.js";
import { loadJobs } from "./pages/jobs.js";
import { loadLibrary, libState } from "./pages/library.js";
import { loadFix } from "./pages/fix.js";
import { loadPlan, loadCurrentPlan } from "./pages/plan.js";
import { loadTrain } from "./pages/train.js";
import { loadLogs } from "./pages/logs.js";
import { loadSettings, loadSendConfig } from "./pages/settings.js";

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

export const pages = ["home", "search", "sing", "train", "jobs", "library", "fix", "plan", "logs", "settings"];
function go(page) {
  if (!pages.includes(page)) return;
  $$("#nav a[data-page]").forEach((a) => a.classList.toggle("active", a.dataset.page === page));
  $$(".page").forEach((p) => p.classList.toggle("active", p.id === `page-${page}`));
  if (page === "jobs") loadJobs();
  if (page === "library") {
    const kindParam = new URLSearchParams(location.search).get("kind");
    const targetKind = kindParam && ["model", "song", "output", "source", "voice", "favorite"].includes(kindParam)
      ? kindParam : libState.kind;
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

setNavigator(go);
