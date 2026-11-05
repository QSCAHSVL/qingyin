/* 页内文件夹 / 文件浏览器（非交互会话里系统对话框弹不出来） */

import { $, api, closeModal, el, openModal, toast } from "../core.js";

/* ------------------------------------------------------------------ 选文件夹 */
/* ------------------------------------------------------------------ 选文件夹（页内浏览器） */
export async function openPicker(selector, title, mode = "dir", ext = "") {
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

/* ------------------------------------------------------------------ 选文件夹：事件委托 */
// 用 document 级委托，按钮后加/重渲染都不影响
document.addEventListener("click", (event) => {
  const btn = event.target.closest("[data-pick]");
  if (!btn) return;
  event.preventDefault();
  openPicker(btn.dataset.pick, btn.dataset.title || "选择文件夹");
});
window.openPicker = openPicker;
