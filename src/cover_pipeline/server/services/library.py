"""资源库：列表、详情、收藏、删除、重建索引。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from ...library.index import human_size
from .common import ffmpeg_duration

if TYPE_CHECKING:
    from ..app import AppState

PLAYABLE_SUFFIXES = {".wav", ".mp3", ".flac", ".m4a", ".ogg"}


def list_payload(state: AppState, kind: str | None, text: str, page: int, size: int) -> dict[str, Any]:
    """GET /api/library：分页列表，附人类可读的大小。"""
    items = state.library.list(kind, text, limit=size, page=page)
    for item in items:
        item["size_human"] = human_size(item["size_bytes"])
    total = state.library.count(kind, text)
    return {
        "items": items, "page": page, "size": size, "total": total,
        "pages": max(1, (total + size - 1) // size),
    }


def stats(state: AppState) -> dict[str, Any]:
    """GET /api/library/stats。"""
    return state.library.stats()


def favorites(state: AppState) -> dict[str, Any]:
    """GET /api/library/favorites。"""
    items = state.library.favorites()
    for item in items:
        item["size_human"] = human_size(item.get("size_bytes") or 0)
    return {"items": items}


def item(state: AppState, path: str) -> dict[str, Any] | None:
    """GET /api/library/item：单个条目详情（音频补时长）。"""
    detail = state.library.detail(path)
    if not detail:
        return None
    target = Path(path)
    if target.is_file() and target.suffix.lower() in PLAYABLE_SUFFIXES:
        try:
            detail["duration"] = round(ffmpeg_duration(target), 1)
        except Exception:
            detail["duration"] = None
        detail["playable"] = True
    else:
        detail["playable"] = False
    return detail


def delete(state: AppState, path: str) -> dict[str, Any]:
    """POST /api/library/delete：移到回收站。"""
    trash = state.work_dir / "_trash"
    moved = state.library.delete(path, trash)
    if not moved:
        raise FileNotFoundError(path)
    return {"ok": True, "moved_to": str(moved)}


def set_favorite(state: AppState, path: str, on: bool) -> dict[str, Any]:
    """POST /api/library/favorite。"""
    state.library.set_favorite(path, on)
    return {"ok": True, "favorite": on}


def batch(state: AppState, action: str, paths: list[Any], on: bool = True) -> dict[str, Any]:
    """POST /api/library/batch：批量删除 / 收藏。"""
    done = 0
    for item_path in paths:
        try:
            if action == "delete":
                delete(state, str(item_path))
            elif action == "favorite":
                state.library.set_favorite(str(item_path), bool(on))
            done += 1
        except Exception:
            continue
    return {"ok": True, "done": done, "total": len(paths)}


def scan(state: AppState) -> dict[str, Any]:
    """POST /api/library/scan：重建索引（后台任务）。"""
    def task(job):
        state.jobs.update(job, progress=0.1, message="扫描资源库")
        counts = state.library.scan(state.cfg)
        return {"counts": counts, "stats": state.library.stats()}

    job = state.jobs.submit("scan", "重建资源库索引", task)
    return job.as_dict()
