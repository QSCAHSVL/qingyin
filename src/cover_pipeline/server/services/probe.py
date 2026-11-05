"""硬件与环境探测：探测缓存、资源占用、首次使用引导。"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ... import probe as probe_mod
from ...library.index import human_size
from .common import gpu_used_gb

if TYPE_CHECKING:
    from ..app import AppState


def cached_probe(state: AppState, force: bool = False) -> dict[str, Any]:
    """硬件探测比较贵（nvidia-smi + 扫目录），默认缓存 60 秒。

    界面默认不自动探测，用户点「检测环境」时才带 refresh=1 强制刷新。
    """
    import time as _time

    now = _time.time()
    if not force and state.probe_cache and now - state.probe_at < 60:
        return state.probe_cache
    snapshot = probe_mod.probe(state.cfg)
    state.probe_cache = snapshot
    state.probe_at = now
    return snapshot


def snapshot_payload(state: AppState) -> dict[str, Any]:
    """GET /api/probe：原始探测结果 + 一句话摘要。"""
    snapshot = cached_probe(state)
    return {"probe": snapshot, "summary": probe_mod.summary(snapshot)}


def resources(state: AppState, force: bool = False) -> dict[str, Any]:
    """显存 / 内存 / 磁盘 / 库容量 / 任务数 / 运行时长。"""
    _ = force  # 兼容旧调用；探测本身已带缓存
    snapshot = cached_probe(state)
    stats = state.library.stats()
    gpu = snapshot.get("gpu") or []
    vram_total = max((g.get("vram_gb", 0) for g in gpu), default=0)
    vram_used = gpu_used_gb()
    return {
        "gpu": gpu,
        "vram": {"total_gb": vram_total, "used_gb": vram_used, "free_gb": max(0.0, vram_total - vram_used)},
        "memory": snapshot.get("memory", {}),
        "disk": snapshot.get("disk", {}),
        "library": {
            "items": stats["items"],
            "total": human_size(stats["total_bytes"]),
            "by_kind": {
                kind: {"count": item["count"], "size": human_size(item["bytes"])}
                for kind, item in stats["by_kind"].items()
            },
        },
        "jobs": {"active": state.jobs.active_count(), "total": len(state.jobs.list())},
        "uptime_seconds": int(time.time() - state.started_at),
    }


def onboarding(state: AppState) -> dict[str, Any]:
    """首页的五个步骤：环境、接本机工具、选方案、备模型、出第一首。"""
    from ...core import convert
    from ...plan.writer import current_plan

    snapshot = cached_probe(state)
    local = snapshot.get("local", {})
    plan = current_plan()
    model = convert.resolve_model_path(state.cfg)
    outputs = list(Path(state.cfg["project"]["work_dir"]).glob("*/4-成品/*.wav"))
    steps = [
        {
            "id": "env",
            "title": "检查环境",
            "desc": "确认 ffmpeg 和显卡能用",
            "done": bool(snapshot["ffmpeg"]["available"]),
            "hint": "缺 ffmpeg：winget install Gyan.FFmpeg",
            "action": "doctor",
        },
        {
            "id": "link",
            "title": "接上本机 RVC / UVR",
            "desc": "不用重装，直接用机器上已有的",
            "done": bool(local.get("rvc", {}).get("ok") and local.get("uvr", {}).get("ok")),
            "hint": "点「自动检测」；装在别处可以手动填路径",
            "action": "link",
        },
        {
            "id": "plan",
            "title": "选一套方案",
            "desc": "按显卡和习惯推荐参数",
            "done": bool(plan),
            "hint": "不知道选什么就用推荐的那套",
            "action": "plan",
        },
        {
            "id": "model",
            "title": "准备音色模型",
            "desc": "训练一个，或用现有的 .pth",
            "done": bool(model),
            "hint": "没有模型只能跑分离和混音",
            "action": "train",
        },
        {
            "id": "first",
            "title": "出第一首",
            "desc": "搜一首歌，直接翻唱",
            "done": bool(outputs),
            "hint": "去「找歌」页搜一个，点「下载并翻唱」",
            "action": "search",
        },
    ]
    return {"steps": steps, "done": sum(1 for s in steps if s["done"]), "total": len(steps)}
