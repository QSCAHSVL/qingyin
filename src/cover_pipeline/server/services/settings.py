"""设置：数据目录与占用、发布配置、免责声明、Agent 接入信息。"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ... import __version__
from ... import config as cfg_mod

if TYPE_CHECKING:
    from ..app import AppState


def settings(state: AppState) -> dict[str, Any]:
    """GET /api/settings：当前数据目录、占用和磁盘余量。"""
    project = state.cfg.get("project", {})
    resolved: dict[str, str] = {}
    usage: dict[str, dict[str, Any]] = {}
    for key in ("work_dir", "output_dir", "models_dir"):
        raw = project.get(key)
        path = Path(str(raw)).expanduser()
        if not path.is_absolute():
            path = (cfg_mod.ROOT / path).resolve()
        resolved[key] = str(path)
        files = 0
        size = 0
        if path.exists():
            for item in path.rglob("*"):
                if item.is_file():
                    files += 1
                    try:
                        size += item.stat().st_size
                    except OSError:
                        pass
        usage[key] = {"exists": path.exists(), "files": files, "size_mb": round(size / 1024 / 1024, 1)}

    disk = shutil.disk_usage(cfg_mod.ROOT)
    return {
        "project": {k: str(project.get(k, "")) for k in ("work_dir", "output_dir", "models_dir")},
        "resolved": resolved,
        "usage": usage,
        "root": str(cfg_mod.ROOT),
        "disk": {"total_gb": round(disk.total / 1024 ** 3, 1), "free_gb": round(disk.free / 1024 ** 3, 1)},
        "send": {
            "enabled": bool((state.cfg.get("send") or {}).get("enabled")),
            "target": str((state.cfg.get("send") or {}).get("target") or ""),
            "account": str((state.cfg.get("send") or {}).get("account") or "main"),
        },
        "version": __version__,
    }


def save_settings(state: AppState, payload: dict[str, Any]) -> dict[str, Any]:
    """POST /api/settings：校验并写入三个数据目录（重启后生效）。"""
    from ...plan.writer import set_project_paths

    updates: dict[str, str] = {}
    problems: list[str] = []
    for key in ("work_dir", "output_dir", "models_dir"):
        raw = str(payload.get(key) or "").strip()
        if not raw:
            continue
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = (cfg_mod.ROOT / path).resolve()
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".cover_write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{key}：{path} 写不了（{exc}）")
            continue
        updates[key] = str(path)

    if problems:
        return {"ok": False, "errors": problems}
    if not updates:
        return {"ok": False, "errors": ["没有填写任何路径"]}

    set_project_paths(updates)
    return {
        "ok": True,
        "written": updates,
        "requires_restart": True,
        "note": "已写入 configs/local.yaml；重启卿音后生效。换目录后旧索引不会跟着走，需要到资源库点「重建索引」。",
    }


def save_send_config(state: AppState, payload: dict[str, Any]) -> dict[str, Any]:
    """POST /api/settings/send：保存外发配置（默认关闭）。"""
    from ...plan.writer import patch_local

    updates: dict[str, Any] = {}
    if payload.get("enabled") is not None:
        updates["enabled"] = bool(payload["enabled"])
    if payload.get("target") is not None:
        updates["target"] = str(payload["target"]).strip()
    if payload.get("account") is not None:
        updates["account"] = str(payload["account"]).strip() or "main"
    if not updates:
        return {"ok": False, "errors": ["没有要保存的内容"]}
    patch_local({"send": updates})
    return {"ok": True, "written": updates, "note": "已写入 local.yaml；下次出成品时生效。"}


# ---------------------------------------------------------------- 免责声明

def disclaimer(state: AppState) -> dict[str, Any]:
    """GET /api/disclaimer。"""
    flag = cfg_mod.ROOT / ".disclaimer-ack"
    return {"acknowledged": flag.exists(), "version": "1"}


def ack_disclaimer(state: AppState) -> dict[str, Any]:
    """POST /api/disclaimer/ack。"""
    import time as _time

    flag = cfg_mod.ROOT / ".disclaimer-ack"
    flag.write_text(_time.strftime("%Y-%m-%d %H:%M:%S"), encoding="utf-8")
    return {"ok": True}


# ---------------------------------------------------------------- Agent 接入

def agent_key(state: AppState) -> str:
    """外部 Agent 调 /api/agent/* 用的 key：优先配置，其次 work_dir 里的文件。"""
    key_file = state.work_dir / "_agent_key.txt"
    configured = str((state.cfg.get("server") or {}).get("api_key") or "").strip()
    if configured:
        return configured
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()
    key = "cp_" + uuid.uuid4().hex
    key_file.write_text(key, encoding="utf-8")
    return key


def agent_info(state: AppState) -> dict[str, Any]:
    """GET /api/agent/info：给外部 Agent 的接入信息。"""
    return {
        "base": f"http://127.0.0.1:{state.port}",
        "api_key": agent_key(state),
        "endpoints": {
            "sing": "POST /api/agent/sing  {query, name?, full?}",
            "status": "GET /api/agent/status?id=<job_id>",
            "search": "GET /api/search?q=",
        },
        "hint": "外部 Agent 用 X-Api-Key 头调用；也可以直接用 /api/sing 等公开接口。",
    }
