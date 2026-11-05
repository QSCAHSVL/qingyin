"""方案：按硬件推荐参数方案、一键配置环境、应用/撤销方案、接本机 RVC/UVR。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...plan import Profile, apply_plan, load_plans, recommend, recommend_assets
from .probe import cached_probe

if TYPE_CHECKING:
    from ..app import AppState


def recommend_payload(state: AppState, profile: Profile) -> dict[str, Any]:
    """GET /api/plan：方案卡列表 + 排除原因 + 配套组件推荐。"""
    snapshot = cached_probe(state)
    scored = recommend(snapshot, profile)
    available_plans = [s for s in scored if not s.excluded_reason]
    assets = recommend_assets(
        snapshot, profile, available_plans[0].plan if available_plans else None
    )
    return {
        "assets": assets,
        "profile": profile.as_dict(),
        "plans": [
            {
                "id": s.id,
                "name": s.name,
                "score": s.score,
                "recommended": s.recommended,
                "plan": s.plan,
                "notes": s.notes,
            }
            for s in scored
            if not s.excluded_reason
        ],
        "excluded": [
            {"id": s.id, "reason": s.excluded_reason} for s in scored if s.excluded_reason
        ],
    }


def available(state: AppState) -> dict[str, Any]:
    """GET /api/plans/available：所有方案，不做推荐排序。"""
    return {"plans": [{"id": p.get("id"), "name": p.get("name")} for p in load_plans()]}


def current(state: AppState) -> dict[str, Any]:
    """GET /api/plan/current：当前生效的方案。"""
    from ...plan.writer import current_plan

    return {"plan": current_plan()}


def apply_by_id(state: AppState, plan_id: str) -> dict[str, Any] | None:
    """POST /api/plan/apply：写进配置。方案不存在时返回 None（适配层给 400）。"""
    target = next((p for p in load_plans() if str(p.get("id")) == plan_id), None)
    if not target:
        return None
    from ...plan.writer import apply_tools

    snapshot = cached_probe(state)
    apply_tools(snapshot.get("local", {}))
    path_written = apply_plan(target)
    return {"ok": True, "path": str(path_written), "plan": plan_id}


def clear(state: AppState) -> dict[str, Any]:
    """POST /api/plan/clear：撤销方案，恢复默认。"""
    from ...plan.writer import clear_plan

    written = clear_plan()
    return {"ok": True, "path": str(written)}


def setup_plan(state: AppState, payload: dict[str, Any]) -> dict[str, Any]:
    """探测环境并给出配置步骤（GET /api/setup/plan 与 POST 共用）。"""
    from ...setup import plan_setup

    snapshot = cached_probe(state)
    profile = Profile(
        prefer=str(payload.get("prefer") or "stability"),
        will_train=str(payload.get("train") or "unsure"),
        max_vram_gb=payload.get("max_vram") or None,
    )
    plans = recommend(snapshot, profile)
    available_plans = [p for p in plans if not p.excluded_reason]
    best = available_plans[0] if available_plans else None
    assets = recommend_assets(snapshot, profile, best.plan if best else None)
    steps = plan_setup(
        snapshot, profile, state.cfg, best.plan if best else None,
        separation=str(payload.get("separation") or "auto"),
    )
    return {
        "plan": {"id": best.id, "name": best.name, "plan": best.plan} if best else None,
        "assets": assets,
        "steps": steps,
        "probe": {
            "vram_gb": max((g.get("vram_gb", 0) for g in snapshot.get("gpu") or []), default=0),
            "disk_free_gb": (snapshot.get("disk") or {}).get("free_gb", 0),
            "ffmpeg": (snapshot.get("ffmpeg") or {}).get("available", False),
            "local_rvc": (snapshot.get("local", {}).get("rvc") or {}).get("ok", False),
            "local_uvr": (snapshot.get("local", {}).get("uvr") or {}).get("ok", False),
        },
    }


def submit_setup(state: AppState, payload: dict[str, Any]) -> dict[str, Any]:
    """POST /api/setup/run：确认后真的装依赖 / 下模型 / 写配置。"""
    from ...setup import execute, plan_setup

    snapshot = cached_probe(state)
    profile = Profile(
        prefer=str(payload.get("prefer") or "stability"),
        will_train=str(payload.get("train") or "unsure"),
        max_vram_gb=payload.get("max_vram") or None,
    )
    plans = recommend(snapshot, profile)
    available_plans = [p for p in plans if not p.excluded_reason]
    best = available_plans[0] if available_plans else None
    setup = plan_setup(
        snapshot, profile, state.cfg, best.plan if best else None,
        separation=str(payload.get("separation") or "auto"),
    )

    def task(job):
        def progress(value: float, message: str) -> None:
            state.jobs.update(job, progress=value, message=message)

        result = execute(
            setup, state.cfg,
            on_progress=progress,
            cancel_event=job.cancel_event,
            plan=best.plan if best else None,
            snapshots={"local": snapshot.get("local"), "separation": setup.get("separation")},
        )
        try:
            state.library.scan(state.cfg)
        except Exception:
            pass
        return result

    job = state.jobs.submit("setup", "一键配置环境", task, payload=payload)
    return job.as_dict()


def link_tools(state: AppState, payload: dict[str, Any]) -> dict[str, Any]:
    """POST /api/link：接上本机已有的 RVC / UVR，写进配置。"""
    from ... import probe as probe_mod
    from ...plan.writer import apply_tools

    detected = probe_mod.local_installs(state.cfg)
    if payload.get("rvc_dir"):
        detected["rvc"]["dir"] = str(payload["rvc_dir"])
        detected["rvc"]["ok"] = True
    if payload.get("rvc_python"):
        detected["rvc"]["python"] = str(payload["rvc_python"])
    if payload.get("uvr_script"):
        detected["uvr"]["script"] = str(payload["uvr_script"])
        detected["uvr"]["ok"] = True
    if payload.get("uvr_python"):
        detected["uvr"]["python"] = str(payload["uvr_python"])
    apply_tools(detected)
    state.cfg["local"] = detected
    return {
        "ok": bool(detected["rvc"].get("ok") and detected["uvr"].get("ok")),
        "rvc": detected["rvc"],
        "uvr": detected["uvr"],
    }
