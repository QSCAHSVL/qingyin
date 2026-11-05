"""后台任务：跑训练、翻唱、配方对比这类几十秒到几十分钟的活。

设计要点：
- 任务在子线程里跑，界面只轮询状态，不阻塞
- 每个任务一份 JSON 状态 + 一份日志文件，进程崩了也能看到上次跑到哪
- 同一时间只允许一个「吃显存」的任务（GPU 独占），其余排队
"""

from __future__ import annotations

import json
import threading
import time
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class Job:
    id: str
    kind: str
    label: str
    status: str = "queued"          # queued / running / succeeded / failed / cancelled
    progress: float = 0.0           # 0~1，不知道就留 0
    message: str = ""
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    ended_at: float | None = None
    log_path: str = ""
    payload: dict = field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: str = ""
    gpu: bool = False

    # 取消标记：worker 里传给可取消的子进程，界面点「取消」就置位
    cancel_event: Any = field(default_factory=threading.Event, repr=False, compare=False)

    def as_dict(self) -> dict[str, Any]:
        # 不用 asdict：它会对 cancel_event 做深拷贝，Event 里有锁，拷不动
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "log_path": self.log_path,
            "result": self.result,
            "error": self.error,
            "gpu": self.gpu,
        }


class JobManager:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.dir = self.root / "_jobs"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._gpu_lock = threading.Lock()
        self._load_existing()

    # ------------------------------------------------------------------ 对外接口

    def submit(
        self,
        kind: str,
        label: str,
        fn: Callable[[Job], dict[str, Any] | None],
        *,
        gpu: bool = False,
        payload: dict[str, Any] | None = None,
    ) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], kind=kind, label=label, gpu=gpu, payload=payload or {})
        # 日志落到项目 logs/ 下（不是 work/），方便长期查阅、也方便打包时排除
        try:
            from .. import config as cfg_mod

            log_dir = cfg_mod.ROOT / "logs" / "jobs"
            log_dir.mkdir(parents=True, exist_ok=True)
            job.log_path = str(log_dir / f"{job.id}.log")
        except Exception:
            job.log_path = str(self.dir / f"{job.id}.log")
        with self._lock:
            self._jobs[job.id] = job
        self._persist(job)
        thread = threading.Thread(target=self._run, args=(job, fn), name=f"job-{job.id}", daemon=True)
        thread.start()
        return job

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
        return [job.as_dict() for job in jobs]

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
        return job.as_dict() if job else None

    def get_obj(self, job_id: str) -> "Job | None":
        """拿 Job 对象本身。as_dict() 里没有 payload，重跑这类场景要读原始参数。"""
        with self._lock:
            return self._jobs.get(job_id)

    def tail(self, job_id: str, lines: int = 80) -> str:
        job = self._jobs.get(job_id)
        if not job or not job.log_path:
            return ""
        path = Path(job.log_path)
        if not path.exists():
            return ""
        text = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(text[-lines:])

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
        if not job or job.status not in ("queued", "running"):
            return False
        job.status = "cancelled"
        job.message = "正在取消…"
        try:
            job.cancel_event.set()
        except Exception as exc:  # noqa: BLE001 - 落盘失败只记录，不打断任务
            try:
                from ..utils.log import warn

                warn(f"任务状态落盘失败：{exc}")
            except Exception:
                pass
        self._persist(job)
        return True

    def active_count(self) -> int:
        with self._lock:
            return sum(1 for j in self._jobs.values() if j.status in ("queued", "running"))

    # ------------------------------------------------------------------ 内部

    def _run(self, job: Job, fn: Callable[[Job], dict[str, Any] | None]) -> None:
        acquired = False
        try:
            if job.gpu:
                self._gpu_lock.acquire()
                acquired = True
            if job.status == "cancelled":
                return
            job.status = "running"
            job.started_at = time.time()
            job.message = "开始"
            self._persist(job)
            result = fn(job) or {}
            if job.status == "cancelled":
                job.message = "已取消"
                return
            job.status = "succeeded"
            job.progress = 1.0
            job.result = result
            job.message = "完成"
            self._record_plan_stat(job, True)
        except Exception as exc:  # noqa: BLE001 - 任务失败要留在状态里
            if job.status == "cancelled" or type(exc).__name__ == "Cancelled":
                job.status = "cancelled"
                job.message = "已取消"
                job.error = ""
                self.log(job, "任务被取消")
                return
            job.status = "failed"
            try:
                from ..utils.errors import explain

                info = explain(exc)
                job.error = f"{info['title']}：{info['hint']}"
                job.message = job.error[:200]
                job.result = {"error_raw": info["raw"], "error_title": info["title"], "error_hint": info["hint"]}
            except Exception:
                job.error = f"{exc}"
                job.message = str(exc)[:200]
            self.log(job, traceback.format_exc())
            self._record_plan_stat(job, False, error_text=f"{exc}\n{traceback.format_exc()[-2000:]}")
        finally:
            job.ended_at = time.time()
            self._persist(job)
            if acquired:
                self._gpu_lock.release()

    def _record_plan_stat(self, job: Job, ok: bool, error_text: str = "") -> None:
        """把这次跑的方案与耗时回写，供方案引擎下次加权；失败时附一条自愈建议。"""
        payload = job.payload or {}
        plan = payload.get("plan") if isinstance(payload.get("plan"), dict) else None
        plan_id = (plan or {}).get("id") or payload.get("plan_id")
        if not plan_id:
            return
        seconds = None
        if job.started_at and job.ended_at:
            seconds = round(job.ended_at - job.started_at, 1)
        kind = None
        try:
            from ..plan import heal, stats

            if ok:
                stats.record(str(plan_id), True, seconds=seconds)
                return
            kind = heal.classify(error_text)
            stats.record(str(plan_id), False, seconds=seconds, kind=kind,
                         note=(error_text or "")[:200].replace("\n", " "))
            if plan:
                suggestion = heal.next_plan(plan, error_text, 1)
                if suggestion:
                    job.result = {**(job.result or {}), "heal_suggestion": {
                        "plan_id": suggestion.get("id"),
                        "name": suggestion.get("name"),
                        "kind": kind,
                    }}
        except Exception as exc:  # noqa: BLE001 - 统计失败不能影响任务状态
            self.log(job, f"方案统计写入失败：{exc}")

    def log(self, job: Job, text: str) -> None:
        if not job.log_path:
            return
        with open(job.log_path, "a", encoding="utf-8") as fh:
            fh.write(f"[{time.strftime('%H:%M:%S')}] {text}\n")

    def update(self, job: Job, *, progress: float | None = None, message: str | None = None) -> None:
        if progress is not None:
            job.progress = max(0.0, min(1.0, progress))
        if message is not None:
            job.message = message
            self.log(job, message)
        self._persist(job)

    def _persist(self, job: Job) -> None:
        try:
            path = self.dir / f"{job.id}.json"
            path.write_text(json.dumps(job.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001 - 落盘失败只记录，不打断任务
            try:
                from ..utils.log import warn

                warn(f"任务状态落盘失败：{exc}")
            except Exception:
                pass

    def _load_existing(self) -> None:
        """重启后把历史任务读回来，正在跑的标记成中断。"""
        for path in sorted(self.dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                job = Job(**{k: v for k, v in data.items() if k in Job.__annotations__})
                if job.status in ("queued", "running"):
                    job.status = "failed"
                    job.message = "进程重启，任务中断"
                    self._persist(job)
                self._jobs[job.id] = job
            except Exception:
                continue
