"""任务：翻唱、批量、配方对比、重跑、取消、备份，以及任务列表查询。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from ... import config as cfg_mod
from ...recipes import loader as recipes_loader
from ...recipes import runner as recipes_runner
from .common import ffmpeg_duration

if TYPE_CHECKING:
    from ..app import AppState


# ---------------------------------------------------------------- 查询与控制

def list_jobs(state: AppState) -> dict[str, Any]:
    """GET /api/jobs。"""
    return {"jobs": state.jobs.list()}


def get_job(state: AppState, job_id: str) -> dict[str, Any] | None:
    """GET /api/jobs/{id}、/api/agent/status。"""
    return state.jobs.get(job_id)


def tail_log(state: AppState, job_id: str, lines: int = 200) -> str:
    """GET /api/jobs/{id}/log。"""
    return state.jobs.tail(job_id, lines)


def cancel_job(state: AppState, job_id: str) -> dict[str, Any]:
    """POST /api/jobs/{id}/cancel。"""
    return {"ok": state.jobs.cancel(job_id)}


def retry_job(state: AppState, job_id: str) -> dict[str, Any]:
    """按原任务参数重跑一次（只支持 sing / oneclick / download / train / fix）。

    注意：`state.jobs.get()` 返回的是 `as_dict()`（dict，且不含 payload），
    这里要读原始参数，所以走 `get_obj()` 拿 Job 对象。
    """
    job = state.jobs.get_obj(job_id)
    if not job:
        raise ValueError("任务不存在")
    payload = dict(job.payload or {})
    kind = job.kind
    if kind == "sing":
        return submit_sing(state, payload)
    if kind == "oneclick":
        from .search import submit_oneclick

        return submit_oneclick(state, payload)
    if kind == "download":
        from .search import submit_search_download

        return submit_search_download(state, payload)
    if kind == "train":
        from .train import submit_train

        return submit_train(state, payload)
    if kind == "fix":
        return submit_fix(state, payload)
    if kind == "setup":
        from .plans import submit_setup

        return submit_setup(state, payload)
    raise ValueError(f"这种任务不支持重跑：{kind}")


# ---------------------------------------------------------------- 提交任务

def submit_sing(state: AppState, payload: dict[str, Any]) -> dict[str, Any]:
    """POST /api/sing：翻唱一首。"""
    from ...pipelines import sing as sing_pipeline

    query = str(payload.get("input") or payload.get("song") or "").strip()
    if not query:
        raise ValueError("要给 input 或 song")
    name = str(payload.get("name") or Path(query).stem)
    full = bool(payload.get("full"))
    force = bool(payload.get("force"))

    def task(job):
        state.jobs.update(job, progress=0.05, message=f"开始处理 {name}")
        result = sing_pipeline.run(
            query, name, state.cfg, force=force, full=full, cancel_event=job.cancel_event
        )
        state.jobs.update(job, progress=0.95, message="整理产物")
        try:
            state.library.scan(state.cfg)
        except Exception:
            pass
        return result

    job = state.jobs.submit("sing", f"翻唱：{name}", task, gpu=True, payload=payload)
    return job.as_dict()


def submit_fix(state: AppState, payload: dict[str, Any]) -> dict[str, Any]:
    """POST /api/fix：跑一组配方做对比。"""
    song = str(payload.get("song") or "").strip()
    symptom = str(payload.get("symptom") or "").strip()
    if not song or not symptom:
        raise ValueError("要给 song 和 symptom")
    ids = payload.get("recipes") or None
    seconds = float(payload.get("seconds") or recipes_runner.DEFAULT_SECONDS)
    song_dir = state.work_dir / song

    def task(job):
        def progress(value: float, message: str) -> None:
            state.jobs.update(job, progress=value, message=message)

        return recipes_runner.compare(
            song_dir, state.cfg, symptom, ids, seconds=seconds, progress=progress
        )

    job = state.jobs.submit("fix", f"配方对比：{song}", task, gpu=True, payload=payload)
    return job.as_dict()


def plan_tracks(state: AppState, payload: dict[str, Any]) -> dict[str, Any]:
    """POST /api/sing/plan：判断给的是文件 / 文件夹 / 歌名。"""
    from ...pipelines import sing as sing_pipeline

    query = str(payload.get("input") or payload.get("song") or "").strip()
    plan = sing_pipeline.plan_tracks(query, state.cfg)
    for track in plan.get("tracks", []):
        path = Path(track["path"])
        if path.is_file():
            try:
                track["duration"] = round(ffmpeg_duration(path), 1)
            except Exception:
                track["duration"] = None
    return plan


def submit_tracks(state: AppState, payload: dict[str, Any]) -> dict[str, Any]:
    """POST /api/sing/tracks：按选中的曲目批量翻唱。"""
    from ...pipelines import sing as sing_pipeline

    tracks = payload.get("tracks") or []
    if not tracks:
        raise ValueError("没有选中的曲目")
    full = bool(payload.get("full"))
    force = bool(payload.get("force"))
    names = "、".join(str(t.get("name") or "?") for t in tracks[:3])
    label = f"翻唱 {len(tracks)} 首：{names}" + ("…" if len(tracks) > 3 else "")

    def task(job):
        result = sing_pipeline.run_many(
            tracks, state.cfg, force=force, full=full,
            on_progress=lambda value, message: state.jobs.update(job, progress=value, message=message),
            cancel_event=job.cancel_event,
        )
        try:
            state.library.scan(state.cfg)
        except Exception:
            pass
        return result

    job = state.jobs.submit("sing", label, task, gpu=True)
    return job.as_dict()


# ---------------------------------------------------------------- 备份

def create_backup(state: AppState) -> dict[str, Any]:
    """POST /api/backup：把 work / output / models 打包（后台任务）。"""
    def task(job):
        return _do_backup(state, job)

    job = state.jobs.submit("backup", "备份数据目录", task)
    return job.as_dict()


def _do_backup(state: AppState, job) -> dict[str, Any]:
    """把 work / output / models 打成 zip（不含 library.db 之外的缓存）。"""
    import time as _time
    import zipfile

    stamp = _time.strftime("%Y%m%d-%H%M%S")
    target_dir = cfg_mod.ROOT / "backups"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"qingyin-backup-{stamp}.zip"

    project = state.cfg.get("project", {})
    roots = []
    for key in ("work_dir", "output_dir", "models_dir"):
        path = Path(str(project.get(key) or "")).expanduser()
        if not path.is_absolute():
            path = (cfg_mod.ROOT / path).resolve()
        if path.exists():
            roots.append(path)

    count = 0
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for base in roots:
            for file in base.rglob("*"):
                if not file.is_file():
                    continue
                if file.suffix.lower() in {".tmp", ".part"}:
                    continue
                try:
                    zf.write(file, file.relative_to(cfg_mod.ROOT))
                    count += 1
                    if count % 200 == 0:
                        state.jobs.update(job, progress=min(0.95, count / 8000), message=f"打包中 {count} 个文件")
                except OSError:
                    continue
    return {"path": str(target), "files": count, "size_mb": round(target.stat().st_size / 1024 / 1024, 1)}


# ---------------------------------------------------------------- 症状配方

def recipes(state: AppState) -> dict[str, Any]:
    """GET /api/recipes：症状与配方清单。"""
    items = recipes_loader.load_recipes()
    return {
        "recipes": [
            {
                "id": item.get("id"),
                "symptom": item.get("symptom"),
                "selected": recipes_loader.recommended_of(item),
                "options": [
                    {
                        "id": r.get("id"),
                        "name": r.get("name"),
                        "how": r.get("how"),
                        "cost": r.get("cost"),
                        "risk": r.get("risk"),
                        "evidence": r.get("evidence"),
                        "experimental": r.get("experimental", False),
                    }
                    for r in item.get("recipes") or []
                ],
            }
            for item in items
        ]
    }


def adopt_recipe(state: AppState, payload: dict[str, Any]) -> dict[str, Any]:
    """POST /api/fix/adopt：采纳某个配方，记一笔决策。"""
    song = str(payload.get("song") or "")
    symptom = str(payload.get("symptom") or "")
    chosen = str(payload.get("recipe") or "")
    candidates = payload.get("candidates") or []
    recipes_loader.record_decision(state.cfg, symptom, chosen, candidates, str(payload.get("note") or ""))
    return {"ok": True, "song": song}
