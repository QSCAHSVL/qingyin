"""找歌：平台搜索、下载、一键翻唱。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..app import AppState


def providers(state: AppState) -> dict[str, Any]:
    """GET /api/search/providers：可用的搜索来源。"""
    from ...sources import online

    return {"providers": online.providers()}


def search(state: AppState, text: str, limit: int = 12, sources: list[str] | None = None) -> dict[str, Any]:
    """GET /api/search。"""
    from ...sources import online

    return {"query": text, "items": online.search(text, limit, sources)}


def submit_search_download(state: AppState, payload: dict[str, Any]) -> dict[str, Any]:
    """POST /api/search/download：先下载，按需接着翻唱。"""
    from ...sources import online

    item = {
        "url": str(payload.get("url") or ""),
        "title": str(payload.get("title") or "在线素材"),
        "source": str(payload.get("source") or "bilibili"),
        "id": str(payload.get("id") or ""),
        "quality": str(payload.get("quality") or "standard"),
    }
    name = str(payload.get("name") or item["title"])[:40]
    also_sing = bool(payload.get("sing"))
    quality = str(payload.get("quality") or "standard")

    def task(job):
        cache = Path(state.cfg["project"]["work_dir"]) / "_cache"
        state.jobs.update(job, progress=0.05, message="下载中")
        path = online.download(
            item, cache,
            on_progress=lambda text: state.jobs.update(job, message=text),
            ffmpeg_dir=state.cfg.get("tools", {}).get("ffmpeg_dir"),
            cancel_event=job.cancel_event,
            quality=quality,
        )
        result: dict[str, Any] = {"downloaded": str(path), "name": name}
        if also_sing:
            from ...pipelines import sing as sing_pipeline

            state.jobs.update(job, progress=0.2, message="开始翻唱")
            sung = sing_pipeline.run(str(path), name, state.cfg, force=False, full=bool(payload.get("full")))
            result.update(sung)
            try:
                state.library.scan(state.cfg)
            except Exception:
                pass
        return result

    job = state.jobs.submit("search", f"在线素材：{name}", task, gpu=also_sing, payload=payload)
    return job.as_dict()


def submit_oneclick(state: AppState, payload: dict[str, Any]) -> dict[str, Any]:
    """POST /api/oneclick、/api/agent/sing：搜一首、挑最能下的、下完直接唱。"""
    from ...sources import online

    query = str(payload.get("query") or "").strip()
    if not query:
        raise ValueError("给个歌名")
    full = bool(payload.get("full"))

    def task(job):
        state.jobs.update(job, progress=0.02, message="在线找歌")
        items = [item for item in online.search(query, 12) if item.get("playable")]
        if not items:
            raise RuntimeError("没找到能直接下载的结果，去「找歌」页手动挑一个，或用自己的文件")
        chosen = items[0]
        state.jobs.update(job, progress=0.05, message=f"选了：{chosen['title'][:30]}")
        cache = Path(state.cfg["project"]["work_dir"]) / "_cache"
        path = online.download(
            chosen, cache,
            on_progress=lambda text: state.jobs.update(job, message=text),
            ffmpeg_dir=state.cfg.get("tools", {}).get("ffmpeg_dir"),
            cancel_event=job.cancel_event,
        )
        from ...pipelines import sing as sing_pipeline

        name = re.sub(r"[\\/:*?\"<>|]+", "_", chosen["title"])[:40]
        state.jobs.update(job, progress=0.25, message=f"开始翻唱：{name}")
        result = sing_pipeline.run(
            str(path), name, state.cfg, force=False, full=full, cancel_event=job.cancel_event
        )
        try:
            state.library.scan(state.cfg)
        except Exception:
            pass
        return {**result, "picked": chosen}

    job = state.jobs.submit("oneclick", f"一键翻唱：{query}", task, gpu=True, payload=payload)
    return job.as_dict()
