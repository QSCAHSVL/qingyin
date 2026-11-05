"""训练：配置回填、素材预检、提交训练、保存训练配置。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..app import AppState


def config(state: AppState) -> dict[str, Any]:
    """GET /api/train/config：当前训练相关配置（给训练页回填）。"""
    train_cfg = state.cfg.get("train") or {}
    return {
        "command": str(train_cfg.get("command") or ""),
        "has_command": bool(str(train_cfg.get("command") or "").strip()),
        "model_name": str(train_cfg.get("model_name") or ""),
        "output_dirs": list(train_cfg.get("output_dirs") or []),
        "epochs": int(train_cfg.get("epochs", 80) or 80),
        "batch_size": int(train_cfg.get("batch_size", 4) or 4),
        "sample_rate": int(train_cfg.get("sample_rate", 40000) or 40000),
        "clean": bool(train_cfg.get("clean", True)),
    }


def preview(state: AppState, payload: dict[str, Any]) -> dict[str, Any]:
    """GET/POST /api/train/preview：训练参数预检，不执行。"""
    from ...pipelines import train as train_pipeline

    data = str(payload.get("data") or "").strip()
    if not data:
        return {"error": "请填写素材目录"}
    info = train_pipeline.preview(Path(data).expanduser(), state.cfg)
    info["ready"] = bool(info["files"]) and info["command_configured"]
    if not info["command_configured"]:
        info["warnings"].append("还没配置训练命令（train.command），填好才能真的开跑")
    return info


def submit_train(state: AppState, payload: dict[str, Any]) -> dict[str, Any]:
    """POST /api/train：提交一次训练任务。"""
    from ...pipelines import train as train_pipeline

    data = str(payload.get("data") or "").strip()
    name = str(payload.get("name") or "").strip()
    if not data:
        raise ValueError("请填写素材目录")
    if not name:
        raise ValueError("请填写音色名（训练出来的模型用这个名字）")

    cfg = dict(state.cfg)
    train_cfg = dict(cfg.get("train") or {})
    for key, cast in (("epochs", int), ("batch_size", int), ("sample_rate", int)):
        if payload.get(key) not in (None, ""):
            train_cfg[key] = cast(payload[key])
    if payload.get("clean") is not None:
        train_cfg["clean"] = bool(payload["clean"])
    if payload.get("model_name"):
        train_cfg["model_name"] = str(payload["model_name"])
    cfg["train"] = train_cfg

    if not str(train_cfg.get("command") or "").strip():
        raise RuntimeError("还没配置训练命令：先到「训练」页填 train.command，或手动改 configs/local.yaml")

    def task(job):
        def progress(value: float, message: str) -> None:
            state.jobs.update(job, progress=value, message=message)

        result = train_pipeline.run(Path(data).expanduser(), name, cfg, on_progress=progress)
        try:
            state.library.scan(state.cfg)
        except Exception:
            pass
        return result

    job = state.jobs.submit("train", f"训练音色 {name}", task, gpu=True, payload=payload)
    return job.as_dict()


def save_config(state: AppState, payload: dict[str, Any]) -> dict[str, Any]:
    """POST /api/train/config：写训练相关配置到 local.yaml。"""
    from ...plan.writer import patch_local

    updates: dict[str, Any] = {}
    command = str(payload.get("command") or "").strip()
    if command:
        updates["command"] = command
    for key in ("model_name",):
        value = str(payload.get(key) or "").strip()
        if value:
            updates[key] = value
    for key in ("epochs", "batch_size", "sample_rate"):
        if payload.get(key) not in (None, ""):
            updates[key] = int(payload[key])
    dirs = payload.get("output_dirs")
    if isinstance(dirs, list) and dirs:
        updates["output_dirs"] = [str(d) for d in dirs]
    if not updates:
        return {"ok": False, "errors": ["没有要保存的内容"]}

    patch_local({"train": updates})
    return {"ok": True, "written": updates, "requires_restart": False,
            "note": "已写入 configs/local.yaml；下次训练直接生效。"}
