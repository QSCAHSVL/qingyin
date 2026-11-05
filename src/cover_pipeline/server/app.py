"""本地网页界面（只用标准库，不依赖 FastAPI/uvicorn）。

启动：cover serve --port 7801 --open
所有接口都在 /api/ 下，前端是单页，轮询任务状态和资源占用。
"""

from __future__ import annotations

import json
import shutil
import mimetypes
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import re
import uuid

from .. import __version__
from .. import config as cfg_mod
from .. import probe as probe_mod
from ..jobs.manager import JobManager
from ..library.index import Library, human_size
from ..plan import apply_plan, load_plans, recommend
from ..recipes import loader as recipes_loader
from ..recipes import runner as recipes_runner
from ..utils import log

STATIC_DIR = Path(__file__).parent / "static"

# 简单计数器：排查「界面是不是在反复请求」时很有用
_COUNTERS: dict[str, int] = {}


def _count(name: str) -> None:
    _COUNTERS[name] = _COUNTERS.get(name, 0) + 1


class AppState:
    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg
        self.work_dir = Path(cfg["project"]["work_dir"])
        self.jobs = JobManager(self.work_dir)
        self.library = Library(self.work_dir / "library.db")
        self.started_at = time.time()
        self.port = int((cfg.get("server") or {}).get("port") or 7801)

        self._probe_cache: dict[str, Any] | None = None
        self._probe_at: float = 0.0

        from ..providers import configure_decrypt, load_plugins

        self.plugins = load_plugins()
        configure_decrypt(cfg)

    # ---------------------------------------------------------------- 任务

    def retry_job(self, job_id: str) -> dict[str, Any]:
        """按原任务参数重跑一次（只支持 sing / oneclick / download / train / fix）。"""
        job = self.jobs.get(job_id)
        if not job:
            raise ValueError("任务不存在")
        payload = getattr(job, "payload", None) or {}
        kind = job.kind
        if kind == "sing":
            return self.submit_sing(payload)
        if kind == "oneclick":
            return self.submit_oneclick(payload)
        if kind == "download":
            return self.submit_search_download(payload)
        if kind == "train":
            return self.submit_train(payload)
        if kind == "fix":
            return self.submit_fix(payload)
        if kind == "setup":
            return self.submit_setup(payload)
        raise ValueError(f"这种任务不支持重跑：{kind}")

    def submit_sing(self, payload: dict[str, Any]) -> dict[str, Any]:
        from ..pipelines import sing as sing_pipeline

        query = str(payload.get("input") or payload.get("song") or "").strip()
        if not query:
            raise ValueError("要给 input 或 song")
        name = str(payload.get("name") or Path(query).stem)
        full = bool(payload.get("full"))
        force = bool(payload.get("force"))

        def task(job):
            self.jobs.update(job, progress=0.05, message=f"开始处理 {name}")
            result = sing_pipeline.run(
                query, name, self.cfg, force=force, full=full, cancel_event=job.cancel_event
            )
            self.jobs.update(job, progress=0.95, message="整理产物")
            try:
                self.library.scan(self.cfg)
            except Exception:
                pass
            return result

        job = self.jobs.submit("sing", f"翻唱：{name}", task, gpu=True, payload=payload)
        return job.as_dict()

    def submit_fix(self, payload: dict[str, Any]) -> dict[str, Any]:
        song = str(payload.get("song") or "").strip()
        symptom = str(payload.get("symptom") or "").strip()
        if not song or not symptom:
            raise ValueError("要给 song 和 symptom")
        ids = payload.get("recipes") or None
        seconds = float(payload.get("seconds") or recipes_runner.DEFAULT_SECONDS)
        song_dir = self.work_dir / song

        def task(job):
            def progress(value: float, message: str) -> None:
                self.jobs.update(job, progress=value, message=message)

            return recipes_runner.compare(
                song_dir, self.cfg, symptom, ids, seconds=seconds, progress=progress
            )

        job = self.jobs.submit("fix", f"配方对比：{song}", task, gpu=True, payload=payload)
        return job.as_dict()

    # ---------------------------------------------------------------- 一键配置

    def setup_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        from ..plan import Profile, recommend, recommend_assets
        from ..setup import plan_setup

        snapshot = self.cached_probe()
        profile = Profile(
            prefer=str(payload.get("prefer") or "stability"),
            will_train=str(payload.get("train") or "unsure"),
            max_vram_gb=payload.get("max_vram") or None,
        )
        plans = recommend(snapshot, profile)
        available = [p for p in plans if not p.excluded_reason]
        best = available[0] if available else None
        assets = recommend_assets(snapshot, profile, best.plan if best else None)
        steps = plan_setup(
            snapshot, profile, self.cfg, best.plan if best else None,
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

    def submit_setup(self, payload: dict[str, Any]) -> dict[str, Any]:
        from ..plan import Profile, recommend
        from ..setup import execute, plan_setup

        snapshot = self.cached_probe()
        profile = Profile(
            prefer=str(payload.get("prefer") or "stability"),
            will_train=str(payload.get("train") or "unsure"),
            max_vram_gb=payload.get("max_vram") or None,
        )
        plans = recommend(snapshot, profile)
        available = [p for p in plans if not p.excluded_reason]
        best = available[0] if available else None
        setup = plan_setup(
            snapshot, profile, self.cfg, best.plan if best else None,
            separation=str(payload.get("separation") or "auto"),
        )

        def task(job):
            def progress(value: float, message: str) -> None:
                self.jobs.update(job, progress=value, message=message)

            result = execute(
                setup, self.cfg,
                on_progress=progress,
                cancel_event=job.cancel_event,
                plan=best.plan if best else None,
                snapshots={"local": snapshot.get("local"), "separation": setup.get("separation")},
            )
            try:
                self.library.scan(self.cfg)
            except Exception:
                pass
            return result

        job = self.jobs.submit("setup", "一键配置环境", task, payload=payload)
        return job.as_dict()

    def submit_scan(self) -> dict[str, Any]:
        def task(job):
            self.jobs.update(job, progress=0.1, message="扫描资源库")
            counts = self.library.scan(self.cfg)
            return {"counts": counts, "stats": self.library.stats()}

        job = self.jobs.submit("scan", "重建资源库索引", task)
        return job.as_dict()

    # ---------------------------------------------------------------- 多曲目 / 一键

    def plan_tracks(self, payload: dict[str, Any]) -> dict[str, Any]:
        from ..pipelines import sing as sing_pipeline

        query = str(payload.get("input") or payload.get("song") or "").strip()
        plan = sing_pipeline.plan_tracks(query, self.cfg)
        for track in plan.get("tracks", []):
            path = Path(track["path"])
            if path.is_file():
                try:
                    track["duration"] = round(ffmpeg_duration(path), 1)
                except Exception:
                    track["duration"] = None
        return plan

    def submit_tracks(self, payload: dict[str, Any]) -> dict[str, Any]:
        from ..pipelines import sing as sing_pipeline

        tracks = payload.get("tracks") or []
        if not tracks:
            raise ValueError("没有选中的曲目")
        full = bool(payload.get("full"))
        force = bool(payload.get("force"))
        names = "、".join(str(t.get("name") or "?") for t in tracks[:3])
        label = f"翻唱 {len(tracks)} 首：{names}" + ("…" if len(tracks) > 3 else "")

        def task(job):
            result = sing_pipeline.run_many(
                tracks, self.cfg, force=force, full=full,
                on_progress=lambda value, message: self.jobs.update(job, progress=value, message=message),
                cancel_event=job.cancel_event,
            )
            try:
                self.library.scan(self.cfg)
            except Exception:
                pass
            return result

        job = self.jobs.submit("sing", label, task, gpu=True)
        return job.as_dict()

    def submit_oneclick(self, payload: dict[str, Any]) -> dict[str, Any]:
        """一键翻唱：搜一首、挑最能下的、下完直接唱。"""
        from ..sources import online

        query = str(payload.get("query") or "").strip()
        if not query:
            raise ValueError("给个歌名")
        full = bool(payload.get("full"))

        def task(job):
            self.jobs.update(job, progress=0.02, message="在线找歌")
            items = [item for item in online.search(query, 12) if item.get("playable")]
            if not items:
                raise RuntimeError("没找到能直接下载的结果，去「找歌」页手动挑一个，或用自己的文件")
            chosen = items[0]
            self.jobs.update(job, progress=0.05, message=f"选了：{chosen['title'][:30]}")
            cache = Path(self.cfg["project"]["work_dir"]) / "_cache"
            path = online.download(
                chosen, cache,
                on_progress=lambda text: self.jobs.update(job, message=text),
                ffmpeg_dir=self.cfg.get("tools", {}).get("ffmpeg_dir"),
                cancel_event=job.cancel_event,
            )
            from ..pipelines import sing as sing_pipeline

            name = re.sub(r"[\\/:*?\"<>|]+", "_", chosen["title"])[:40]
            self.jobs.update(job, progress=0.25, message=f"开始翻唱：{name}")
            result = sing_pipeline.run(
                str(path), name, self.cfg, force=False, full=full, cancel_event=job.cancel_event
            )
            try:
                self.library.scan(self.cfg)
            except Exception:
                pass
            return {**result, "picked": chosen}

        job = self.jobs.submit("oneclick", f"一键翻唱：{query}", task, gpu=True, payload=payload)
        return job.as_dict()

    # ---------------------------------------------------------------- 资源库交互

    def library_item(self, path: str) -> dict[str, Any] | None:
        item = self.library.detail(path)
        if not item:
            return None
        target = Path(path)
        if target.is_file() and target.suffix.lower() in {".wav", ".mp3", ".flac", ".m4a", ".ogg"}:
            try:
                item["duration"] = round(ffmpeg_duration(target), 1)
            except Exception:
                item["duration"] = None
            item["playable"] = True
        else:
            item["playable"] = False
        return item

    def delete_item(self, path: str) -> dict[str, Any]:
        trash = self.work_dir / "_trash"
        moved = self.library.delete(path, trash)
        if not moved:
            raise FileNotFoundError(path)
        return {"ok": True, "moved_to": str(moved)}

    # ---------------------------------------------------------------- 训练

    def train_preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        from ..pipelines import train as train_pipeline

        data = str(payload.get("data") or "").strip()
        if not data:
            return {"error": "请填写素材目录"}
        info = train_pipeline.preview(Path(data).expanduser(), self.cfg)
        info["ready"] = bool(info["files"]) and info["command_configured"]
        if not info["command_configured"]:
            info["warnings"].append("还没配置训练命令（train.command），填好才能真的开跑")
        return info

    # ---------------------------------------------------------------- 备份

    def create_backup(self) -> dict[str, Any]:
        """把 work / output / models 打包（后台任务）。"""
        def task(job):
            return self._do_backup(job)

        job = self.jobs.submit("backup", "备份数据目录", task)
        return job.as_dict()

    def _do_backup(self, job) -> dict[str, Any]:
        """把 work / output / models 打成 zip（不含 library.db 之外的缓存）。"""
        import time as _time
        import zipfile

        stamp = _time.strftime("%Y%m%d-%H%M%S")
        target_dir = cfg_mod.ROOT / "backups"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"qingyin-backup-{stamp}.zip"

        project = self.cfg.get("project", {})
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
                            self.jobs.update(job, progress=min(0.95, count / 8000), message=f"打包中 {count} 个文件")
                    except OSError:
                        continue
        return {"path": str(target), "files": count, "size_mb": round(target.stat().st_size / 1024 / 1024, 1)}

    # ---------------------------------------------------------------- 发布配置

    def save_send_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        from ..plan.writer import patch_local

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

    # ---------------------------------------------------------------- 组件安装

    def assets_list(self) -> dict[str, Any]:
        """清单里每一项的安装状态。"""
        import importlib.util

        from ..plan import assets as assets_mod

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

    def install_asset(self, payload: dict[str, Any]) -> dict[str, Any]:
        """按清单里的 pip 命令装一个组件（后台任务）。"""
        import shlex
        import sys

        from ..plan import assets as assets_mod
        from ..utils import proc

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
            self.jobs.update(job, progress=0.05, message=f"安装 {target.get('label')}")
            proc.run([sys.executable, "-m", "pip", "install", *args], timeout=3600)
            return {"id": asset_id, "installed": True}

        job = self.jobs.submit("install", f"安装组件：{target.get('label')}", task, payload=payload)
        return job.as_dict()

    # ---------------------------------------------------------------- 日志

    def logs_list(self) -> dict[str, Any]:
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

    def logs_tail(self, payload: dict[str, Any]) -> dict[str, Any]:
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

    def fs_list(self, payload: dict[str, Any]) -> dict[str, Any]:
        """列目录（给页面里的文件浏览器用）。path 为空时返回盘符。"""
        from ..pipelines.sing import AUDIO_SUFFIXES

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

    def pick_folder(self, payload: dict[str, Any]) -> dict[str, Any]:
        """在服务端弹原生文件夹选择框（只对本机有意义）。"""
        from ..utils import folder_pick

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

    def train_config(self) -> dict[str, Any]:
        """当前训练相关配置（给训练页回填）。"""
        train_cfg = self.cfg.get("train") or {}
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

    def submit_train(self, payload: dict[str, Any]) -> dict[str, Any]:
        from ..pipelines import train as train_pipeline

        data = str(payload.get("data") or "").strip()
        name = str(payload.get("name") or "").strip()
        if not data:
            raise ValueError("请填写素材目录")
        if not name:
            raise ValueError("请填写音色名（训练出来的模型用这个名字）")

        cfg = dict(self.cfg)
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
                self.jobs.update(job, progress=value, message=message)

            result = train_pipeline.run(Path(data).expanduser(), name, cfg, on_progress=progress)
            try:
                self.library.scan(self.cfg)
            except Exception:
                pass
            return result

        job = self.jobs.submit("train", f"训练音色 {name}", task, gpu=True, payload=payload)
        return job.as_dict()

    def save_train_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        """写训练相关配置到 local.yaml（命令、模型名、输出目录、默认轮数）。"""
        from ..plan.writer import patch_local

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

    # ---------------------------------------------------------------- 设置

    def settings(self) -> dict[str, Any]:
        """当前数据目录、占用和磁盘余量。"""
        project = self.cfg.get("project", {})
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
                "enabled": bool((self.cfg.get("send") or {}).get("enabled")),
                "target": str((self.cfg.get("send") or {}).get("target") or ""),
                "account": str((self.cfg.get("send") or {}).get("account") or "main"),
            },
            "version": __version__,
        }

    def save_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        """校验并写入三个数据目录（写入 local.yaml，重启后生效）。"""
        from ..plan.writer import set_project_paths

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

    def cached_probe(self, force: bool = False) -> dict[str, Any]:
        """硬件探测比较贵（nvidia-smi + 扫目录），默认缓存 60 秒。

        界面默认不自动探测，用户点「检测环境」时才带 refresh=1 强制刷新。
        """
        import time as _time

        now = _time.time()
        if not force and self._probe_cache and now - self._probe_at < 60:
            return self._probe_cache
        snapshot = probe_mod.probe(self.cfg)
        self._probe_cache = snapshot
        self._probe_at = now
        return snapshot

    def reveal(self, path: str) -> None:
        """在资源管理器里定位文件（只在本机、只对项目目录内生效）。"""
        import subprocess

        target = Path(path)
        allowed = [self.work_dir.resolve(), Path(self.cfg["project"]["output_dir"]).resolve()]
        resolved = target.resolve()
        if not any(_is_inside(resolved, root) for root in allowed):
            raise PermissionError("只能打开项目目录里的文件")
        if resolved.is_dir():
            subprocess.Popen(["explorer", str(resolved)])
        else:
            subprocess.Popen(["explorer", "/select,", str(resolved)])

    def agent_key(self) -> str:
        key_file = self.work_dir / "_agent_key.txt"
        configured = str((self.cfg.get("server") or {}).get("api_key") or "").strip()
        if configured:
            return configured
        if key_file.exists():
            return key_file.read_text(encoding="utf-8").strip()
        key = "cp_" + uuid.uuid4().hex
        key_file.write_text(key, encoding="utf-8")
        return key

    def submit_search_download(self, payload: dict[str, Any]) -> dict[str, Any]:
        """在线找到的歌：先下载，按需接着翻唱。"""
        from ..sources import online

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
            cache = Path(self.cfg["project"]["work_dir"]) / "_cache"
            self.jobs.update(job, progress=0.05, message="下载中")
            path = online.download(
                item, cache,
                on_progress=lambda text: self.jobs.update(job, message=text),
                ffmpeg_dir=self.cfg.get("tools", {}).get("ffmpeg_dir"),
                cancel_event=job.cancel_event,
                quality=quality,
            )
            result: dict[str, Any] = {"downloaded": str(path), "name": name}
            if also_sing:
                from ..pipelines import sing as sing_pipeline

                self.jobs.update(job, progress=0.2, message="开始翻唱")
                sung = sing_pipeline.run(str(path), name, self.cfg, force=False, full=bool(payload.get("full")))
                result.update(sung)
                try:
                    self.library.scan(self.cfg)
                except Exception:
                    pass
            return result

        job = self.jobs.submit("search", f"在线素材：{name}", task, gpu=also_sing, payload=payload)
        return job.as_dict()

    def onboarding(self) -> dict[str, Any]:
        from ..core import convert
        from ..plan.writer import current_plan

        snapshot = self.cached_probe()
        local = snapshot.get("local", {})
        plan = current_plan()
        model = convert.resolve_model_path(self.cfg)
        outputs = list(Path(self.cfg["project"]["work_dir"]).glob("*/4-成品/*.wav"))
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

    # ---------------------------------------------------------------- 资源

    def resources(self, force: bool = False) -> dict[str, Any]:
        _ = force  # 兼容旧调用；探测本身已带缓存
        snapshot = self.cached_probe()
        stats = self.library.stats()
        gpu = snapshot.get("gpu") or []
        vram_total = max((g.get("vram_gb", 0) for g in gpu), default=0)
        vram_used = _gpu_used_gb()
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
            "jobs": {"active": self.jobs.active_count(), "total": len(self.jobs.list())},
            "uptime_seconds": int(time.time() - self.started_at),
        }


def ffmpeg_duration(path: Path) -> float:
    from ..utils import ffmpeg

    return ffmpeg.duration(path)


def _gpu_used_gb() -> float:
    import subprocess

    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=8,
        )
        return round(float(out.stdout.strip().splitlines()[0]) / 1024, 1)
    except Exception:
        return 0.0


# --------------------------------------------------------------------------- HTTP

def make_handler(state: AppState):
    class Handler(BaseHTTPRequestHandler):
        server_version = f"cover-pipeline/{__version__}"

        # ------------------------------------------------------------ 路由
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)
            try:
                if path == "/" or path == "/index.html":
                    return self._file(STATIC_DIR / "index.html")
                if path.startswith("/static/"):
                    return self._file(STATIC_DIR / path[len("/static/"):])
                if path == "/api/health":
                    return self._json({"ok": True, "version": __version__, "uptime": int(time.time() - state.started_at), "counters": _COUNTERS})
                if path == "/api/probe":
                    snapshot = state.cached_probe()
                    return self._json({"probe": snapshot, "summary": probe_mod.summary(snapshot)})
                if path == "/api/resources":
                    _count("resources")
                    force = (query.get("refresh") or ["0"])[0] in ("1", "true", "yes")
                    return self._json(state.resources(force))
                if path == "/api/plan":
                    profile = _profile_from_query(query)
                    snapshot = state.cached_probe()
                    scored = recommend(snapshot, profile)
                    from ..plan import recommend_assets

                    available_plans = [s for s in scored if not s.excluded_reason]
                    assets = recommend_assets(
                        snapshot, profile, available_plans[0].plan if available_plans else None
                    )
                    return self._json(
                        {
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
                    )
                if path == "/api/jobs":
                    return self._json({"jobs": state.jobs.list()})
                if path == "/api/onboarding":
                    return self._json(state.onboarding())
                if path == "/api/fs/list":
                    return self._json(state.fs_list({"path": (query.get("path") or [""])[0]}))
                if path == "/api/train/config":
                    return self._json(state.train_config())
                if path == "/api/train/preview":
                    _count("train_preview")
                    return self._json(state.train_preview({
                        "data": (query.get("data") or [""])[0],
                    }))
                if path == "/api/logs":
                    return self._json(state.logs_list())
                if path == "/api/logs/tail":
                    return self._json(state.logs_tail({
                        "name": (query.get("name") or [""])[0],
                        "lines": (query.get("lines") or ["200"])[0],
                    }))
                if path == "/api/assets":
                    return self._json(state.assets_list())
                if path == "/api/settings":
                    return self._json(state.settings())
                if path == "/api/setup/plan":
                    _count("setup_plan")
                    force = (query.get("refresh") or ["0"])[0] in ("1", "true", "yes")
                    separation = (query.get("separation") or ["auto"])[0]
                    return self._json(state.setup_plan({"refresh": force, "separation": separation}))
                if path == "/api/models":
                    from ..models import list_models

                    return self._json({"voices": list_models(state.cfg)})
                if path == "/api/search/providers":
                    from ..sources import online

                    return self._json({"providers": online.providers()})
                if path == "/api/library/item":
                    target = (query.get("path") or [""])[0]
                    item = state.library_item(target)
                    return self._json(item or {"error": "not found"}, 200 if item else 404)
                if path == "/api/library/favorites":
                    items = state.library.favorites()
                    for item in items:
                        item["size_human"] = human_size(item.get("size_bytes") or 0)
                    return self._json({"items": items})
                if path == "/api/plan/current":
                    from ..plan.writer import current_plan

                    return self._json({"plan": current_plan()})
                if path == "/api/agent/info":
                    return self._json(
                        {
                            "base": f"http://127.0.0.1:{state.port}",
                            "api_key": state.agent_key(),
                            "endpoints": {
                                "sing": "POST /api/agent/sing  {query, name?, full?}",
                                "status": "GET /api/agent/status?id=<job_id>",
                                "search": "GET /api/search?q=",
                            },
                            "hint": "外部 Agent 用 X-Api-Key 头调用；也可以直接用 /api/sing 等公开接口。",
                        }
                    )
                if path == "/api/agent/status":
                    job_id = (query.get("id") or [""])[0]
                    job = state.jobs.get(job_id)
                    return self._json(job or {"error": "not found"}, 200 if job else 404)
                if path == "/api/search":
                    from ..sources import online

                    text = (query.get("q") or [""])[0]
                    limit = int((query.get("limit") or ["12"])[0])
                    raw_sources = (query.get("sources") or [""])[0]
                    sources = [x.strip() for x in raw_sources.split(",") if x.strip()] or None
                    return self._json({"query": text, "items": online.search(text, limit, sources)})
                if path == "/api/openapi.json":
                    return self._json(openapi_spec())
                if path in ("/docs", "/api/docs"):
                    return self._file(STATIC_DIR / "api.html")
                if path == "/docs/plans":
                    doc = cfg_mod.ROOT / "docs" / "PLANS.md"
                    if not doc.exists():
                        return self._text("还没写 docs/PLANS.md", 404)
                    return self._text(doc.read_text(encoding="utf-8"))
                if path.startswith("/api/jobs/"):
                    parts = path.strip("/").split("/")
                    job_id = parts[2]
                    if len(parts) == 4 and parts[3] == "log":
                        return self._text(state.jobs.tail(job_id, 200))
                    job = state.jobs.get(job_id)
                    return self._json(job or {"error": "not found"}, 200 if job else 404)
                if path == "/api/library/stats":
                    return self._json(state.library.stats())
                if path == "/api/library":
                    kind = (query.get("kind") or [None])[0]
                    text = (query.get("q") or [""])[0]
                    page = int((query.get("page") or ["1"])[0])
                    size = int((query.get("size") or ["20"])[0])
                    items = state.library.list(kind, text, limit=size, page=page)
                    for item in items:
                        item["size_human"] = human_size(item["size_bytes"])
                    total = state.library.count(kind, text)
                    return self._json({"items": items, "page": page, "size": size, "total": total,
                                       "pages": max(1, (total + size - 1) // size)})
                if path == "/api/recipes":
                    items = recipes_loader.load_recipes()
                    return self._json(
                        {
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
                    )
                if path == "/api/audio":
                    return self._audio((query.get("path") or [""])[0])
                if path == "/api/plans/available":
                    return self._json({"plans": [{"id": p.get("id"), "name": p.get("name")} for p in load_plans()]})
                return self._json({"error": "not found"}, 404)
            except Exception as exc:  # noqa: BLE001
                log.error(f"{path} 出错：{exc}")
                return self._json({"error": str(exc)}, 500)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            payload = self._read_json()
            try:
                if path == "/api/plan/apply":
                    plan_id = str(payload.get("id") or "")
                    target = next((p for p in load_plans() if str(p.get("id")) == plan_id), None)
                    if not target:
                        return self._json({"error": f"没有这个方案：{plan_id}"}, 400)
                    from ..plan.writer import apply_tools

                    snapshot = state.cached_probe()
                    apply_tools(snapshot.get("local", {}))
                    path_written = apply_plan(target)
                    return self._json({"ok": True, "path": str(path_written), "plan": plan_id})
                if path == "/api/sing/plan":
                    return self._json(state.plan_tracks(payload))
                if path == "/api/sing/tracks":
                    return self._json(state.submit_tracks(payload))
                if path == "/api/sing":
                    return self._json(state.submit_sing(payload))
                if path == "/api/oneclick":
                    return self._json(state.submit_oneclick(payload))
                if path == "/api/reveal":
                    target = str(payload.get("path") or "")
                    if not target:
                        return self._json({"error": "missing path"}, 400)
                    try:
                        state.reveal(target)
                    except PermissionError as exc:
                        return self._json({"error": str(exc)}, 403)
                    return self._json({"ok": True})
                if path == "/api/pick-folder":
                    return self._json(state.pick_folder(payload))
                if path == "/api/train":
                    return self._json(state.submit_train(payload))
                if path == "/api/train/config":
                    return self._json(state.save_train_config(payload))
                if path == "/api/settings":
                    return self._json(state.save_settings(payload))
                if path == "/api/setup/plan":
                    _count("setup_plan_post")
                    return self._json(state.setup_plan(payload))
                if path == "/api/setup/run":
                    return self._json(state.submit_setup(payload))
                if path == "/api/models/activate":
                    from ..models import activate_version

                    voice = str(payload.get("voice") or "")
                    version = str(payload.get("version") or "")
                    info = activate_version(state.cfg, voice, version)
                    return self._json({"ok": True, **info})
                if path == "/api/models/import":
                    from ..models import register

                    source = Path(str(payload.get("path") or "")).expanduser()
                    voice = str(payload.get("voice") or source.stem)
                    info = register(state.cfg, voice, source, {"note": "手动导入"})
                    return self._json({"ok": True, **info})
                if path == "/api/models/delete":
                    from ..models import delete_version

                    ok = delete_version(state.cfg, str(payload.get("voice") or ""), str(payload.get("version") or ""))
                    return self._json({"ok": ok})
                if path == "/api/library/batch":
                    action = str(payload.get("action") or "")
                    paths = payload.get("paths") or []
                    done = 0
                    for item_path in paths:
                        try:
                            if action == "delete":
                                state.delete_item(str(item_path))
                            elif action == "favorite":
                                state.library.set_favorite(str(item_path), bool(payload.get("on", True)))
                            done += 1
                        except Exception:
                            continue
                    return self._json({"ok": True, "done": done, "total": len(paths)})
                if path == "/api/library/delete":
                    return self._json(state.delete_item(str(payload.get("path") or "")))
                if path == "/api/library/favorite":
                    target = str(payload.get("path") or "")
                    on = bool(payload.get("on", True))
                    state.library.set_favorite(target, on)
                    return self._json({"ok": True, "favorite": on})
                if path == "/api/plan/clear":
                    from ..plan.writer import clear_plan

                    written = clear_plan()
                    return self._json({"ok": True, "path": str(written)})
                if path == "/api/agent/sing":
                    key = self.headers.get("X-Api-Key") or ""
                    if key != state.agent_key():
                        return self._json({"error": "bad api key"}, 401)
                    return self._json(state.submit_oneclick(payload))
                if path == "/api/search/download":
                    return self._json(state.submit_search_download(payload))
                if path == "/api/link":
                    from ..plan.writer import apply_tools

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
                    return self._json(
                        {
                            "ok": bool(detected["rvc"].get("ok") and detected["uvr"].get("ok")),
                            "rvc": detected["rvc"],
                            "uvr": detected["uvr"],
                        }
                    )
                if path == "/api/fix":
                    return self._json(state.submit_fix(payload))
                if path == "/api/library/scan":
                    return self._json(state.submit_scan())
                if path == "/api/fix/adopt":
                    song = str(payload.get("song") or "")
                    symptom = str(payload.get("symptom") or "")
                    chosen = str(payload.get("recipe") or "")
                    candidates = payload.get("candidates") or []
                    recipes_loader.record_decision(state.cfg, symptom, chosen, candidates, str(payload.get("note") or ""))
                    return self._json({"ok": True, "song": song})
                if path.startswith("/api/jobs/") and path.endswith("/retry"):
                    job_id = path.split("/")[3]
                    return self._json(state.retry_job(job_id))
                if path == "/api/backup":
                    return self._json(state.create_backup())
                if path == "/api/settings/send":
                    return self._json(state.save_send_config(payload))
                if path == "/api/assets/install":
                    return self._json(state.install_asset(payload))
                if path.startswith("/api/jobs/") and path.endswith("/cancel"):
                    job_id = path.strip("/").split("/")[2]
                    return self._json({"ok": state.jobs.cancel(job_id)})
                return self._json({"error": "not found"}, 404)
            except Exception as exc:  # noqa: BLE001
                log.error(f"{path} 出错：{exc}")
                return self._json({"error": str(exc)}, 500)

        # ------------------------------------------------------------ 工具
        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or 0)
            if not length:
                return {}
            raw = self.rfile.read(length)
            try:
                return json.loads(raw.decode("utf-8"))
            except Exception:
                return {}

        def _json(self, data: Any, code: int = 200) -> None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self._send(body, "application/json; charset=utf-8", code)

        def _text(self, text: str, code: int = 200) -> None:
            body = text.encode("utf-8", errors="replace")
            self._send(body, "text/plain; charset=utf-8", code)

        def _send(self, body: bytes, ctype: str, code: int = 200) -> None:
            try:
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                # 浏览器切页/关闭会主动断开，属于正常情况，不打堆栈
                pass

        def _file(self, path: Path) -> None:
            if not path.exists() or not path.is_file():
                return self._json({"error": "not found"}, 404)
            data = path.read_bytes()
            ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            # 禁缓存：改完界面刷新就能看到，不用清缓存
            self.send_header("Cache-Control", "no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(data)

        def _audio(self, raw: str) -> None:
            """只允许播项目目录里的音频，避免变成任意文件读取。"""
            if not raw:
                return self._json({"error": "missing path"}, 400)
            target = Path(raw)
            try:
                resolved = target.resolve()
            except OSError:
                return self._json({"error": "bad path"}, 400)
            allowed = [
                Path(state.cfg["project"]["work_dir"]).resolve(),
                Path(state.cfg["project"]["output_dir"]).resolve(),
            ]
            if not any(_is_inside(resolved, root) for root in allowed):
                return self._json({"error": "forbidden"}, 403)
            if resolved.suffix.lower() not in {".wav", ".mp3", ".flac", ".ogg", ".m4a"}:
                return self._json({"error": "not audio"}, 400)
            if not resolved.exists():
                return self._json({"error": "not found"}, 404)
            return self._file(resolved)

        def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
            return  # 静音：日志走自己的 log()

    return Handler


def _is_inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


# 接口分类：给 /docs 页和外部调用者用
API_CATEGORIES: list[dict[str, Any]] = [
    {"name": "环境与配置", "description": "探测硬件、推荐方案、一键装依赖和模型", "match": (
        "/api/onboarding", "/api/setup/", "/api/link", "/api/probe", "/api/resources")},
    {"name": "方案", "description": "硬件驱动的参数方案：推荐、应用、撤销", "match": (
        "/api/plan", "/api/plans/")},
    {"name": "找歌", "description": "四个平台搜索、下载、一键翻唱", "match": (
        "/api/search", "/api/oneclick")},
    {"name": "翻唱与任务", "description": "跑翻唱、批量、任务状态与取消、症状配方", "match": (
        "/api/sing", "/api/jobs", "/api/fix", "/api/recipes")},
    {"name": "资源库", "description": "模型/工程/成品/音源：列表、收藏、删除、定位、试听", "match": (
        "/api/library", "/api/reveal", "/api/audio")},
    {"name": "音色模型", "description": "训练出来的版本：查看、切换、导入、删除", "match": (
        "/api/models",)},
    {"name": "训练", "description": "素材预检、训练音色、训练命令配置", "match": ("/api/train",)},
    {"name": "本机交互", "description": "调用系统对话框、备份、日志", "match": ("/api/pick-folder", "/api/logs", "/api/backup")},
    {"name": "组件", "description": "清单里缺什么，一键装", "match": ("/api/assets",)},
    {"name": "Agent 接入", "description": "给外部 Agent 用的精简入口（带 X-Api-Key）", "match": (
        "/api/agent/",)},
    {"name": "设置", "description": "数据目录、服务信息", "match": ("/api/settings",)},
    {"name": "系统", "description": "健康检查、接口清单", "match": ("/api/health", "/api/openapi.json")},
]


def _category_for(path: str) -> str:
    for item in API_CATEGORIES:
        for prefix in item["match"]:
            if path.startswith(prefix):
                return item["name"]
    return "系统"


def openapi_spec() -> dict[str, Any]:
    """手写的接口描述，给 /docs 页和外部调用者看。"""
    def ok(desc: str) -> dict[str, Any]:
        return {"description": desc, "content": {"application/json": {"schema": {"type": "object"}}}}

    paths: dict[str, Any] = {
            "/api/health": {"get": {"summary": "存活检查", "responses": {"200": ok("服务信息")}}},
            "/api/probe": {"get": {"summary": "硬件与环境探测", "responses": {"200": ok("探测结果")}}},
            "/api/resources": {"get": {"summary": "显存/内存/磁盘/库容量", "responses": {"200": ok("资源快照")}}},
            "/api/onboarding": {"get": {"summary": "引导清单状态", "responses": {"200": ok("五个步骤的完成情况")}}},
            "/api/plan": {
                "get": {
                    "summary": "推荐配置方案",
                    "parameters": [
                        {"name": "prefer", "in": "query", "schema": {"type": "string", "enum": ["quality", "speed", "space", "stability"]}},
                        {"name": "train", "in": "query", "schema": {"type": "string", "enum": ["yes", "no", "unsure"]}},
                        {"name": "disk", "in": "query", "schema": {"type": "number"}},
                        {"name": "patience", "in": "query", "schema": {"type": "number"}},
                    ],
                    "responses": {"200": ok("方案卡列表")},
                }
            },
            "/api/plan/apply": {
                "post": {
                    "summary": "应用某个方案",
                    "requestBody": {"content": {"application/json": {"schema": {"type": "object", "properties": {"id": {"type": "string"}}}}}},
                    "responses": {"200": ok("写入结果")},
                }
            },
            "/api/search": {
                "get": {
                    "summary": "在线找歌（B站 / iTunes / 网易云 / QQ音乐）",
                    "parameters": [
                        {"name": "q", "in": "query", "required": True, "schema": {"type": "string"}},
                        {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 12}},
                    ],
                    "responses": {"200": ok("搜索结果")},
                }
            },
            "/api/search/download": {
                "post": {
                    "summary": "下载搜索结果（可选接着翻唱）",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "url": {"type": "string"},
                                        "title": {"type": "string"},
                                        "name": {"type": "string"},
                                        "sing": {"type": "boolean"},
                                        "full": {"type": "boolean"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": ok("任务对象")},
                }
            },
            "/api/sing": {
                "post": {
                    "summary": "翻唱（本地文件 / 歌名 / 在线链接）",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "input": {"type": "string"},
                                        "song": {"type": "string"},
                                        "name": {"type": "string"},
                                        "full": {"type": "boolean"},
                                        "force": {"type": "boolean"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": ok("任务对象")},
                }
            },
            "/api/jobs": {"get": {"summary": "任务列表", "responses": {"200": ok("任务数组")}}},
            "/api/jobs/{id}": {"get": {"summary": "任务状态", "responses": {"200": ok("任务详情")}}},
            "/api/jobs/{id}/log": {"get": {"summary": "任务日志", "responses": {"200": {"description": "纯文本"}}}},
            "/api/library": {
                "get": {
                    "summary": "资源库列表（支持 kind / q / page / size）",
                    "parameters": [
                        {"name": "kind", "in": "query", "schema": {"type": "string", "enum": ["model", "song", "output", "source"]}},
                        {"name": "q", "in": "query", "schema": {"type": "string"}},
                    ],
                    "responses": {"200": ok("条目数组")},
                }
            },
            "/api/library/scan": {"post": {"summary": "重建资源库索引", "responses": {"200": ok("任务对象")}}},
            "/api/library/stats": {"get": {"summary": "资源库统计", "responses": {"200": ok("按类型汇总")}}},
            "/api/search/providers": {"get": {"summary": "可用的搜索来源", "responses": {"200": ok("平台列表")}}},
            "/api/sing/plan": {
                "post": {
                    "summary": "判断给的是文件/文件夹/歌名",
                    "requestBody": {"content": {"application/json": {"schema": {"type": "object", "properties": {"input": {"type": "string"}, "song": {"type": "string"}}}}}},
                    "responses": {"200": ok("曲目列表")},
                }
            },
            "/api/sing/tracks": {"post": {"summary": "按选中的曲目批量翻唱", "responses": {"200": ok("任务对象")}}},
            "/api/oneclick": {"post": {"summary": "一键翻唱（自动找源+下载+翻唱）", "responses": {"200": ok("任务对象")}}},
            "/api/jobs/{id}/cancel": {"post": {"summary": "取消任务", "responses": {"200": ok("取消结果")}}},
            "/api/library/item": {"get": {"summary": "单个资源详情", "responses": {"200": ok("详情")}}},
            "/api/library/favorite": {"post": {"summary": "收藏 / 取消收藏", "responses": {"200": ok("结果")}}},
            "/api/library/delete": {"post": {"summary": "删除到回收站", "responses": {"200": ok("结果")}}},
            "/api/library/favorites": {"get": {"summary": "收藏列表", "responses": {"200": ok("列表")}}},
            "/api/plan/current": {"get": {"summary": "当前生效的方案", "responses": {"200": ok("方案信息")}}},
            "/api/plan/clear": {"post": {"summary": "撤销方案，恢复默认", "responses": {"200": ok("结果")}}},
            "/api/agent/info": {"get": {"summary": "给外部 Agent 的接入信息（含本地 key）", "responses": {"200": ok("接入信息")}}},
            "/api/agent/sing": {"post": {"summary": "外部 Agent 调一键翻唱（X-Api-Key）", "responses": {"200": ok("任务对象")}}},
            "/api/agent/status": {"get": {"summary": "外部 Agent 查任务状态", "responses": {"200": ok("任务详情")}}},
            "/api/setup/plan": {
                "get": {"summary": "探测环境并给出配置步骤（GET 用默认偏好）", "responses": {"200": ok("方案 + 步骤")}},
                "post": {"summary": "同上，可带 prefer/train/max_vram", "responses": {"200": ok("方案 + 步骤")}},
            },
            "/api/setup/run": {"post": {"summary": "确认后执行配置（装依赖/下模型/写配置）", "responses": {"200": ok("任务对象")}}},
            "/api/link": {"post": {"summary": "接上本机已有的 RVC / UVR（写进配置）", "responses": {"200": ok("结果")}}},
            "/api/plans/available": {"get": {"summary": "所有方案（不做推荐排序）", "responses": {"200": ok("方案列表")}}},
            "/api/reveal": {"post": {"summary": "在资源管理器里定位文件（限定项目目录内）", "responses": {"200": ok("结果")}}},
            "/api/library/batch": {"post": {"summary": "批量收藏 / 取消收藏 / 删除", "responses": {"200": ok("处理条数")}}},
            "/api/openapi.json": {"get": {"summary": "本接口清单（机器可读）", "responses": {"200": ok("OpenAPI 片段")}}},
            "/api/models": {"get": {"summary": "音色模型版本列表", "responses": {"200": ok("按音色分组的版本")}}},
            "/api/models/activate": {"post": {"summary": "切换模型版本", "responses": {"200": ok("结果")}}},
            "/api/models/import": {"post": {"summary": "导入 .pth 作为新版本", "responses": {"200": ok("结果")}}},
            "/api/models/delete": {"post": {"summary": "删除某个版本（当前在用的不能删）", "responses": {"200": ok("结果")}}},
            "/api/recipes": {"get": {"summary": "症状与配方", "responses": {"200": ok("配方列表")}}},
            "/api/fix": {
                "post": {
                    "summary": "跑一组配方做对比",
                    "requestBody": {"content": {"application/json": {"schema": {"type": "object", "properties": {"song": {"type": "string"}, "symptom": {"type": "string"}, "seconds": {"type": "number"}}}}}},
                    "responses": {"200": ok("任务对象")},
                }
            },
            "/api/fix/adopt": {"post": {"summary": "采纳某个配方", "responses": {"200": ok("记录结果")}}},
            "/api/audio": {
                "get": {
                    "summary": "播放项目内的音频（只读）",
                    "parameters": [{"name": "path", "in": "query", "required": True, "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "音频字节"}},
                }
            },
                }

    for path, entry in paths.items():
        tag = _category_for(path)
        for method_spec in entry.values():
            if isinstance(method_spec, dict):
                method_spec["tags"] = [tag]

    return {
        "openapi": "3.0.3",
        "info": {
            "title": "QingYin API",
            "version": __version__,
            "description": "本地翻唱流水线的 HTTP 接口。全部在本机 127.0.0.1 上，除 /api/agent/* 外不需要鉴权。",
        },
        "servers": [{"url": "http://127.0.0.1:7801"}],
        "tags": [{"name": item["name"], "description": item["description"]} for item in API_CATEGORIES],
        "paths": paths,
    }


def _profile_from_query(query: dict[str, list[str]]):
    from ..plan import Profile

    def one(key: str, default: str) -> str:
        return (query.get(key) or [default])[0]

    max_vram_raw = one("max_vram", "")
    return Profile(
        max_vram_gb=float(max_vram_raw) if max_vram_raw else None,
        prefer=one("prefer", "stability"),
        will_train=one("train", "unsure"),
        disk_budget_gb=float(one("disk", "30")),
        patience_minutes=float(one("patience", "10")),
        frequency=one("freq", "weekly"),
        allow_advanced=one("advanced", "0") in ("1", "true", "yes"),
        song_count=int(one("songs", "10")),
    )


def serve(cfg: dict[str, Any], host: str = "127.0.0.1", port: int = 7801, open_browser: bool = True) -> None:
    state = AppState(cfg)
    handler = make_handler(state)
    httpd = ThreadingHTTPServer((host, port), handler)
    url = f"http://{host}:{port}/"
    log.done(f"界面已启动：{url}")
    log.info("Ctrl+C 停止界面；正在跑的任务会被中断，重开后可看日志")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log.warn("已停止")
    finally:
        httpd.server_close()
