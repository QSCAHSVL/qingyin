"""本地网页界面（只用标准库，不依赖 FastAPI/uvicorn）。

启动：cover serve --port 7801 --open
所有接口都在 /api/ 下，前端是单页，轮询任务状态和资源占用。

这个文件只做 HTTP 适配：解析请求 → 调 services 里的业务函数 → 回 JSON。
业务逻辑在 server/services/*.py，接口描述在 server/openapi.py。
"""

from __future__ import annotations

import json
import mimetypes
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .. import __version__
from .. import config as cfg_mod
from ..jobs.manager import JobManager
from ..library.index import Library
from ..utils import log
from .openapi import openapi_spec
from .services import jobs, library, models, plans, search, system, train
from .services import probe as probe_service
from .services import settings as settings_service
from .services.common import is_inside

STATIC_DIR = Path(__file__).parent / "static"

# 简单计数器：排查「界面是不是在反复请求」时很有用
_COUNTERS: dict[str, int] = {}


def _count(name: str) -> None:
    _COUNTERS[name] = _COUNTERS.get(name, 0) + 1


class AppState:
    """一次服务进程的全部共享状态：配置、任务队列、资源库、探测缓存。

    这里只放状态，不放业务逻辑；业务在 services/ 里，HTTP 在 make_handler 里。
    """

    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg
        self.work_dir = Path(cfg["project"]["work_dir"])
        self.jobs = JobManager(self.work_dir)
        self.library = Library(self.work_dir / "library.db")
        self.started_at = time.time()
        self.port = int((cfg.get("server") or {}).get("port") or 7801)

        # 硬件探测比较贵，services/probe.cached_probe 会读写这两个字段
        self.probe_cache: dict[str, Any] | None = None
        self.probe_at: float = 0.0

        from ..providers import configure_decrypt, load_plugins

        self.plugins = load_plugins()
        configure_decrypt(cfg)


# --------------------------------------------------------------------------- HTTP

def make_handler(state: AppState):
    class Handler(BaseHTTPRequestHandler):
        server_version = f"cover-pipeline/{__version__}"

        # ------------------------------------------------------------ 路由
        def do_GET(self) -> None:
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
                    return self._json(probe_service.snapshot_payload(state))
                if path == "/api/resources":
                    _count("resources")
                    force = (query.get("refresh") or ["0"])[0] in ("1", "true", "yes")
                    return self._json(probe_service.resources(state, force))
                if path == "/api/plan":
                    return self._json(plans.recommend_payload(state, _profile_from_query(query)))
                if path == "/api/jobs":
                    return self._json(jobs.list_jobs(state))
                if path == "/api/onboarding":
                    return self._json(probe_service.onboarding(state))
                if path == "/api/fs/list":
                    return self._json(system.fs_list(state, {"path": (query.get("path") or [""])[0]}))
                if path == "/api/train/config":
                    return self._json(train.config(state))
                if path == "/api/train/preview":
                    _count("train_preview")
                    return self._json(train.preview(state, {
                        "data": (query.get("data") or [""])[0],
                    }))
                if path == "/api/disclaimer":
                    return self._json(settings_service.disclaimer(state))
                if path == "/api/logs":
                    return self._json(system.logs_list(state))
                if path == "/api/logs/tail":
                    return self._json(system.logs_tail(state, {
                        "name": (query.get("name") or [""])[0],
                        "lines": (query.get("lines") or ["200"])[0],
                    }))
                if path == "/api/assets":
                    return self._json(system.assets_list(state))
                if path == "/api/settings":
                    return self._json(settings_service.settings(state))
                if path == "/api/setup/plan":
                    _count("setup_plan")
                    force = (query.get("refresh") or ["0"])[0] in ("1", "true", "yes")
                    separation = (query.get("separation") or ["auto"])[0]
                    return self._json(plans.setup_plan(state, {"refresh": force, "separation": separation}))
                if path == "/api/models":
                    return self._json(models.voices(state))
                if path == "/api/search/providers":
                    return self._json(search.providers(state))
                if path == "/api/library/item":
                    target = (query.get("path") or [""])[0]
                    item = library.item(state, target)
                    return self._json(item or {"error": "not found"}, 200 if item else 404)
                if path == "/api/library/favorites":
                    return self._json(library.favorites(state))
                if path == "/api/plan/current":
                    return self._json(plans.current(state))
                if path == "/api/agent/info":
                    return self._json(settings_service.agent_info(state))
                if path == "/api/agent/status":
                    job_id = (query.get("id") or [""])[0]
                    job = jobs.get_job(state, job_id)
                    return self._json(job or {"error": "not found"}, 200 if job else 404)
                if path == "/api/search":
                    text = (query.get("q") or [""])[0]
                    limit = int((query.get("limit") or ["12"])[0])
                    raw_sources = (query.get("sources") or [""])[0]
                    sources = [x.strip() for x in raw_sources.split(",") if x.strip()] or None
                    return self._json(search.search(state, text, limit, sources))
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
                        return self._text(jobs.tail_log(state, job_id, 200))
                    job = jobs.get_job(state, job_id)
                    return self._json(job or {"error": "not found"}, 200 if job else 404)
                if path == "/api/library/stats":
                    return self._json(library.stats(state))
                if path == "/api/library":
                    kind = (query.get("kind") or [None])[0]
                    text = (query.get("q") or [""])[0]
                    page = int((query.get("page") or ["1"])[0])
                    size = int((query.get("size") or ["20"])[0])
                    return self._json(library.list_payload(state, kind, text, page, size))
                if path == "/api/recipes":
                    return self._json(jobs.recipes(state))
                if path == "/api/audio":
                    return self._audio((query.get("path") or [""])[0])
                if path == "/api/plans/available":
                    return self._json(plans.available(state))
                return self._json({"error": "not found"}, 404)
            except Exception as exc:
                log.error(f"{path} 出错：{exc}")
                return self._json({"error": str(exc)}, 500)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            payload = self._read_json()
            try:
                if path == "/api/plan/apply":
                    plan_id = str(payload.get("id") or "")
                    applied = plans.apply_by_id(state, plan_id)
                    if applied is None:
                        return self._json({"error": f"没有这个方案：{plan_id}"}, 400)
                    return self._json(applied)
                if path == "/api/sing/plan":
                    return self._json(jobs.plan_tracks(state, payload))
                if path == "/api/sing/tracks":
                    return self._json(jobs.submit_tracks(state, payload))
                if path == "/api/sing":
                    return self._json(jobs.submit_sing(state, payload))
                if path == "/api/oneclick":
                    return self._json(search.submit_oneclick(state, payload))
                if path == "/api/reveal":
                    target = str(payload.get("path") or "")
                    if not target:
                        return self._json({"error": "missing path"}, 400)
                    try:
                        system.reveal(state, target)
                    except PermissionError as exc:
                        return self._json({"error": str(exc)}, 403)
                    return self._json({"ok": True})
                if path == "/api/disclaimer/ack":
                    return self._json(settings_service.ack_disclaimer(state))
                if path == "/api/pick-folder":
                    return self._json(system.pick_folder(state, payload))
                if path == "/api/train":
                    return self._json(train.submit_train(state, payload))
                if path == "/api/train/config":
                    return self._json(train.save_config(state, payload))
                if path == "/api/settings":
                    return self._json(settings_service.save_settings(state, payload))
                if path == "/api/setup/plan":
                    _count("setup_plan_post")
                    return self._json(plans.setup_plan(state, payload))
                if path == "/api/setup/run":
                    return self._json(plans.submit_setup(state, payload))
                if path == "/api/models/activate":
                    return self._json(models.activate(
                        state, str(payload.get("voice") or ""), str(payload.get("version") or ""),
                    ))
                if path == "/api/models/import":
                    return self._json(models.import_model(
                        state, str(payload.get("path") or ""), str(payload.get("voice") or ""),
                    ))
                if path == "/api/models/delete":
                    return self._json(models.delete_model(
                        state, str(payload.get("voice") or ""), str(payload.get("version") or ""),
                    ))
                if path == "/api/library/batch":
                    return self._json(library.batch(
                        state,
                        str(payload.get("action") or ""),
                        payload.get("paths") or [],
                        bool(payload.get("on", True)),
                    ))
                if path == "/api/library/delete":
                    return self._json(library.delete(state, str(payload.get("path") or "")))
                if path == "/api/library/favorite":
                    target = str(payload.get("path") or "")
                    on = bool(payload.get("on", True))
                    return self._json(library.set_favorite(state, target, on))
                if path == "/api/plan/clear":
                    return self._json(plans.clear(state))
                if path == "/api/agent/sing":
                    key = self.headers.get("X-Api-Key") or ""
                    if key != settings_service.agent_key(state):
                        return self._json({"error": "bad api key"}, 401)
                    return self._json(search.submit_oneclick(state, payload))
                if path == "/api/search/download":
                    return self._json(search.submit_search_download(state, payload))
                if path == "/api/link":
                    return self._json(plans.link_tools(state, payload))
                if path == "/api/fix":
                    return self._json(jobs.submit_fix(state, payload))
                if path == "/api/library/scan":
                    return self._json(library.scan(state))
                if path == "/api/fix/adopt":
                    return self._json(jobs.adopt_recipe(state, payload))
                if path.startswith("/api/jobs/") and path.endswith("/retry"):
                    job_id = path.split("/")[3]
                    return self._json(jobs.retry_job(state, job_id))
                if path == "/api/backup":
                    return self._json(jobs.create_backup(state))
                if path == "/api/settings/send":
                    return self._json(settings_service.save_send_config(state, payload))
                if path == "/api/assets/install":
                    return self._json(system.install_asset(state, payload))
                if path.startswith("/api/jobs/") and path.endswith("/cancel"):
                    job_id = path.strip("/").split("/")[2]
                    return self._json(jobs.cancel_job(state, job_id))
                return self._json({"error": "not found"}, 404)
            except Exception as exc:
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
            if not any(is_inside(resolved, root) for root in allowed):
                return self._json({"error": "forbidden"}, 403)
            if resolved.suffix.lower() not in {".wav", ".mp3", ".flac", ".ogg", ".m4a"}:
                return self._json({"error": "not audio"}, 400)
            if not resolved.exists():
                return self._json({"error": "not found"}, 404)
            return self._file(resolved)

        def log_message(self, fmt: str, *args: Any) -> None:
            return  # 静音：日志走自己的 log()

    return Handler


def _profile_from_query(query: dict[str, list[str]]):
    """GET 查询参数 → 方案偏好。"""
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
