/* 卿音前端 core：DOM 查询 / HTTP / 提示条 / 弹层 / 小工具（第 7 轮从 app.js 拆出） */

export const net = { connFailures: 0 };

/* cover-pipeline v4 前端：原生 JS，不打包不编译 */

export const $ = (sel) => document.querySelector(sel);
export const $$ = (sel) => Array.from(document.querySelectorAll(sel));
export const el = (tag, cls, text) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
};

export async function api(path, options = {}) {
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
  net.connFailures = 0;
  return data;
}

export function toast(message, kind = "") {
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

export function openModal(title, bodyNodes, footNodes) {
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
export function closeModal() {
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

/* 元素不存在也不报错的事件绑定（训练页 / 设置页用） */
export function on(id, handler) {
  const node = $(id);
  if (node) node.addEventListener("click", handler);
}
