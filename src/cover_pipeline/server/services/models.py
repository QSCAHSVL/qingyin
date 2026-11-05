"""音色模型版本：列表、切换、导入、删除。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..app import AppState


def voices(state: AppState) -> dict[str, Any]:
    """GET /api/models：按音色分组的版本列表。"""
    from ...models import list_models

    return {"voices": list_models(state.cfg)}


def activate(state: AppState, voice: str, version: str) -> dict[str, Any]:
    """POST /api/models/activate：切换生效版本。"""
    from ...models import activate_version

    info = activate_version(state.cfg, voice, version)
    return {"ok": True, **info}


def import_model(state: AppState, raw_path: str, voice: str = "") -> dict[str, Any]:
    """POST /api/models/import：把一个 .pth 登记成新版本。"""
    from ...models import register

    source = Path(str(raw_path or "")).expanduser()
    name = str(voice or source.stem)
    info = register(state.cfg, name, source, {"note": "手动导入"})
    return {"ok": True, **info}


def delete_model(state: AppState, voice: str, version: str) -> dict[str, Any]:
    """POST /api/models/delete：删掉某个版本（当前在用的不能删）。"""
    from ...models import delete_version

    ok = delete_version(state.cfg, voice, version)
    return {"ok": ok}
