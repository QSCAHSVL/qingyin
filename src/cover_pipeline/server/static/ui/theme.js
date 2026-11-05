/* 主题：跟随系统 / 宣纸 / 墨 */

import { $ } from "../core.js";

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
