"""本机交互：日志、目录浏览、系统文件夹选择框、资源管理器定位、组件安装。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from ... import config as cfg_mod
from .common import is_inside

if TYPE_CHECKING:
    from ..app import AppState


# ---------------------------------------------------------------- 日志

def logs_list(state: AppState) -> dict[str, Any]:
    """GET /api/logs：列出日志文件。"""
    log_dir = cfg_mod.ROOT / "logs"
    files: list[dict[str, Any]] = []
    if log_dir.exists():
        for path in sorted(log_dir.rglob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)[:200]:
            stat = path.stat()
            files.append({
                "name": path.relative_to(log_dir).as_posix(),
                "size_kb": round(stat.st_size / 1024, 1),
                "mtime": int(stat.st_mtime),
            })
    return {"dir": str(log_dir), "files": files}


def logs_tail(state: AppState, payload: dict[str, Any]) -> dict[str, Any]:
    """GET /api/logs/tail：读某个日志的尾部。"""
    log_dir = cfg_mod.ROOT / "logs"
    name = str(payload.get("name") or "").strip()
    lines = max(10, min(2000, int(payload.get("lines") or 200)))
    if not name:
        candidates = sorted(log_dir.rglob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True) if log_dir.exists() else []
        if not candidates:
            return {"error": "还没有日志文件"}
        target = candidates[0]
    else:
        target = (log_dir / name).resolve()
        if not str(target).startswith(str(log_dir.resolve())):
            return {"error": "只能看项目 logs 目录里的文件"}
        if not target.exists():
            return {"error": f"日志不存在：{name}"}
    content = target.read_text(encoding="utf-8", errors="replace").splitlines()
    return {"name": target.relative_to(log_dir).as_posix(), "lines": content[-lines:], "total": len(content)}


# ---------------------------------------------------------------- 文件浏览

def fs_list(state: AppState, payload: dict[str, Any]) -> dict[str, Any]:
    """GET /api/fs/list：列目录（给页面里的文件浏览器用）。path 为空时返回盘符。"""
    from ...pipelines.sing import AUDIO_SUFFIXES

    ext = str(payload.get("ext") or "").strip().lower()
    wanted_suffixes = {f".{ext.lstrip('.')}"} if ext else AUDIO_SUFFIXES

    raw = str(payload.get("path") or "").strip()
    if not raw:
        drives = []
        for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
            root = Path(f"{letter}:\\")
            try:
                if root.exists():
                    drives.append({"name": f"{letter}:", "path": str(root)})
            except OSError:
                continue
        return {"path": "", "parent": None, "dirs": drives, "files": []}

    target = Path(raw).expanduser()
    if not target.is_absolute():
        target = (cfg_mod.ROOT / target).resolve()
    if not target.exists():
        return {"error": f"目录不存在：{target}"}
    if not target.is_dir():
        return {"error": f"不是目录：{target}"}

    dirs: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    try:
        for entry in sorted(target.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            try:
                if entry.is_dir():
                    dirs.append({"name": entry.name, "path": str(entry)})
                elif entry.suffix.lower() in wanted_suffixes:
                    files.append({"name": entry.name, "path": str(entry),
                                  "size_mb": round(entry.stat().st_size / 1024 / 1024, 1)})
            except OSError:
                continue
    except PermissionError:
        return {"error": f"没有权限读这个目录：{target}"}

    parent = str(target.parent) if target.parent != target else None
    return {"path": str(target), "parent": parent, "dirs": dirs, "files": files}


def pick_folder(state: AppState, payload: dict[str, Any]) -> dict[str, Any]:
    """POST /api/pick-folder：在服务端弹原生文件夹选择框（只对本机有意义）。"""
    from ...utils import folder_pick

    if payload.get("dry_run"):
        return {"ok": True, "available": folder_pick.available(), "dry_run": True}
    if not folder_pick.available():
        return {"ok": False, "error": "这台机器没有 PowerShell，选不了文件夹，手动填路径吧"}
    try:
        picked = folder_pick.pick_folder(
            str(payload.get("title") or "选择文件夹"),
            str(payload.get("initial") or "") or None,
        )
    except TimeoutError as exc:
        return {"ok": False, "error": str(exc)}
    if picked is None:
        return {"ok": True, "cancelled": True}
    return {"ok": True, "path": str(picked)}


def reveal(state: AppState, path: str) -> None:
    """POST /api/reveal：在资源管理器里定位文件（只在本机、只对项目目录内生效）。"""
    import subprocess

    target = Path(path)
    allowed = [state.work_dir.resolve(), Path(state.cfg["project"]["output_dir"]).resolve()]
    resolved = target.resolve()
    if not any(is_inside(resolved, root) for root in allowed):
        raise PermissionError("只能打开项目目录里的文件")
    if resolved.is_dir():
        subprocess.Popen(["explorer", str(resolved)])
    else:
        subprocess.Popen(["explorer", "/select,", str(resolved)])


# ---------------------------------------------------------------- 组件安装

def assets_list(state: AppState) -> dict[str, Any]:
    """GET /api/assets：清单里每一项的安装状态。"""
    import importlib.util

    from ...plan import assets as assets_mod

    manifest = assets_mod.load_manifest()
    groups = []
    for group in ("runtimes", "models", "bundles"):
        items = []
        for item in manifest.get(group, []):
            source = str(item.get("source") or "")
            installed = None
            if source.startswith("pip install"):
                module = str(item.get("module") or "")
                installed = bool(module) and importlib.util.find_spec(module) is not None
            items.append({
                "id": item.get("id"),
                "label": item.get("label"),
                "size_mb": item.get("size_mb"),
                "vram_gb": item.get("vram_gb"),
                "source": source,
                "note": item.get("note"),
                "pip": source.startswith("pip install"),
                "installed": installed,
            })
        groups.append({"group": group, "items": items})
    return {"groups": groups}


def install_asset(state: AppState, payload: dict[str, Any]) -> dict[str, Any]:
    """POST /api/assets/install：按清单里的 pip 命令装一个组件（后台任务）。"""
    import shlex
    import sys

    from ...plan import assets as assets_mod
    from ...utils import proc

    asset_id = str(payload.get("id") or "").strip()
    if not asset_id:
        raise ValueError("缺少组件 id")

    manifest = assets_mod.load_manifest()
    target = None
    for group in ("runtimes", "models", "bundles"):
        for item in manifest.get(group, []):
            if item.get("id") == asset_id:
                target = item
                break
    if not target:
        raise ValueError(f"清单里没有这个组件：{asset_id}")

    source = str(target.get("source") or "")
    if not source.startswith("pip install"):
        raise ValueError("这个组件不是 pip 安装的，请按清单里的说明手动准备")

    # "pip install audio-separator[gpu]（无显卡用 [cpu]）" → 去掉中文说明
    command = source.split("（")[0].strip()
    args = shlex.split(command)[2:]  # 去掉 pip install

    def task(job):
        state.jobs.update(job, progress=0.05, message=f"安装 {target.get('label')}")
        proc.run([sys.executable, "-m", "pip", "install", *args], timeout=3600)
        return {"id": asset_id, "installed": True}

    job = state.jobs.submit("install", f"安装组件：{target.get('label')}", task, payload=payload)
    return job.as_dict()
