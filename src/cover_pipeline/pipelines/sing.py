"""sing 流程：源文件 → 分离 → 转换 → 混音 → 挑段 → 导出。

带缓存：
- `work/<歌名>/1-源文件/` 已存在就跳过获取
- `work/<歌名>/4-成品/` 比模型新就直接复用
"""

from __future__ import annotations

import shutil
from pathlib import Path

from ..core import clip, convert, mix, pitch, separate
from ..sources import get as get_source
from ..sources import load_plugins
from ..utils import log

STAGE_SOURCE = "1-源文件"
STAGE_VOCAL = "2-人声"
STAGE_CONVERTED = "3-转换"
STAGE_FINAL = "4-成品"


AUDIO_SUFFIXES = {".wav", ".flac", ".mp3", ".m4a", ".ogg", ".opus", ".aiff", ".wma"}


def plan_tracks(query: str, cfg: dict, *, max_tracks: int = 200) -> dict:
    """给界面用：判断用户给的是文件、文件夹还是歌名。

    文件夹会列出里面所有音频，让用户勾选后再跑，避免误填目录直接开跑。
    """
    raw = (query or "").strip().strip('"')
    if not raw:
        return {"kind": "empty", "tracks": [], "hint": "先给一个文件、文件夹或歌名"}

    path = Path(raw).expanduser()
    if path.is_dir():
        files = [
            item for item in sorted(path.rglob("*"))
            if item.is_file() and item.suffix.lower() in AUDIO_SUFFIXES
        ][:max_tracks]
        tracks = [
            {
                "path": str(item),
                "name": item.stem,
                "size_mb": round(item.stat().st_size / 1024 / 1024, 1),
            }
            for item in files
        ]
        return {
            "kind": "folder",
            "dir": str(path),
            "tracks": tracks,
            "hint": f"这是个文件夹，里面有 {len(tracks)} 首音频。选好再开始。" if tracks else "文件夹里没找到音频文件",
        }

    if path.is_file():
        return {
            "kind": "file",
            "tracks": [{"path": str(path), "name": path.stem, "size_mb": round(path.stat().st_size / 1024 / 1024, 1)}],
            "hint": "",
        }

    return {"kind": "name", "tracks": [], "hint": "按歌名在配置的搜索目录里找，或者去「找歌」页在线搜"}


def run_many(
    tracks: list[dict],
    cfg: dict,
    *,
    force: bool = False,
    full: bool = False,
    on_progress=None,
    cancel_event=None,
) -> dict:
    """按顺序跑多首，中途取消就停下，返回已完成的结果。"""
    results = []
    total = max(1, len(tracks))
    for index, track in enumerate(tracks):
        if cancel_event is not None and cancel_event.is_set():
            log.warn("收到取消，停止后续曲目")
            break
        name = str(track.get("name") or Path(track["path"]).stem)[:40]
        if on_progress:
            on_progress(index / total, f"第 {index + 1}/{total} 首：{name}")
        try:
            result = run(track["path"], name, cfg, force=force, full=full, cancel_event=cancel_event)
            results.append({"name": name, "ok": True, **result})
        except Exception as exc:
            if type(exc).__name__ == "Cancelled":
                raise
            log.error(f"{name} 失败：{exc}")
            results.append({"name": name, "ok": False, "error": str(exc)})
    if on_progress:
        on_progress(1.0, "全部完成")
    return {"tracks": results, "count": len(results)}


def run(
    query: str,
    name: str,
    cfg: dict,
    *,
    force: bool = False,
    full: bool = False,
    dry_run: bool = False,
    cancel_event=None,
) -> dict:
    if cancel_event is not None:
        cfg = {**cfg, "_cancel_event": cancel_event}
    work_root = Path(cfg["project"]["work_dir"])
    song_dir = work_root / name
    for stage in (STAGE_SOURCE, STAGE_VOCAL, STAGE_CONVERTED, STAGE_FINAL):
        (song_dir / stage).mkdir(parents=True, exist_ok=True)

    log.step(f"开始：{name}")

    if dry_run:
        _print_plan(cfg, song_dir, full)
        return {"dry_run": True, "song_dir": str(song_dir)}

    # 1) 源文件
    source_path = _stage_source(query, song_dir, cfg)

    # 2) 分离
    vocal_path, backing_path = _stage_separate(source_path, song_dir, cfg, force)

    # 2.5) 整首变调：人声和伴奏一起移，不然唱出来对不上原曲
    shift = pitch.estimate_shift(vocal_path, cfg)
    if shift and backing_path:
        log.info(f"整首移调 {shift:+d} 半音（人声和伴奏一起）")
        vocal_path = pitch.shift_file(vocal_path, shift, song_dir / STAGE_VOCAL / f"vocal{shift:+d}.wav", cfg)
        backing_path = pitch.shift_file(backing_path, shift, song_dir / STAGE_VOCAL / f"instrumental{shift:+d}.wav", cfg)
        cfg = {**cfg, "convert": {**cfg.get("convert", {}), "pitch": 0}}

    # 3) 转换
    converted = _stage_convert(vocal_path, song_dir, cfg, force)

    # 4) 混音
    mixed = song_dir / STAGE_FINAL / "mixed.wav"
    if force or not mixed.exists() or _newer(converted, mixed):
        mixed = mix.mix(converted, backing_path, mixed, cfg)
    else:
        log.info(f"复用混音结果：{mixed.name}")

    # 4.5) 分轨存一份，方便二次处理
    result: dict = {"song_dir": str(song_dir), "mixed": str(mixed)}
    try:
        stems = song_dir / STAGE_FINAL / "stems"
        stems.mkdir(parents=True, exist_ok=True)
        vocal_copy = stems / f"{name}-人声.wav"
        if vocal_path and vocal_path.exists():
            shutil.copy2(vocal_path, vocal_copy)
            result["vocal"] = str(vocal_copy)
        if backing_path and backing_path.exists():
            backing_copy = stems / f"{name}-伴奏.wav"
            shutil.copy2(backing_path, backing_copy)
            result["instrumental"] = str(backing_copy)
    except Exception as exc:
        log.warn(f"分轨导出失败（不影响成品）：{exc}")

    # 5) 挑段 / 切段
    if full:
        parts = clip.split_full(mixed, float(cfg.get("clip", {}).get("full_segment_seconds", 55)), song_dir / STAGE_FINAL / "parts")
        result["parts"] = [str(p) for p in parts]
    else:
        seconds = float(cfg.get("clip", {}).get("seconds", 45))
        picked = clip.pick_chorus(mixed, seconds, cfg)
        final = song_dir / STAGE_FINAL / f"{name}-片段.wav"
        clip.export(mixed, picked, final)
        result["final"] = str(final)
        result["start"] = picked.start
        result["seconds"] = picked.seconds
        log.done(f"成品：{final}")
        _maybe_publish(final, name, cfg, result)

    return result


def _stage_source(query: str, song_dir: Path, cfg: dict) -> Path:
    cached = sorted((song_dir / STAGE_SOURCE).glob("*.wav"))
    if cached:
        log.info(f"复用源文件：{cached[0].name}")
        return cached[0]

    # 在线地址：先下到缓存目录，再当作本地文件走后面的流程
    if query.startswith(("http://", "https://")):
        from ..sources import online

        cache = Path(cfg["project"]["work_dir"]) / "_cache"
        log.info("给的是链接，先下载音频")
        downloaded = online.download({"url": query, "source": "bilibili"}, cache, ffmpeg_dir=cfg.get("tools", {}).get("ffmpeg_dir"))
        target = song_dir / STAGE_SOURCE / f"原始{downloaded.suffix.lower()}"
        if not target.exists():
            shutil.copy2(downloaded, target)
        return target

    load_plugins()
    adapter_name = str(cfg.get("source", {}).get("adapter", "local_file"))
    adapter = get_source(adapter_name)
    path = adapter.resolve(query, song_dir / STAGE_SOURCE, cfg)
    if path.parent != song_dir / STAGE_SOURCE:
        target = song_dir / STAGE_SOURCE / f"原始{path.suffix.lower()}"
        if not target.exists():
            target.write_bytes(path.read_bytes())
        path = target
    return path


def _stage_separate(src: Path, song_dir: Path, cfg: dict, force: bool) -> tuple[Path, Path | None]:
    vocal_dir = song_dir / STAGE_VOCAL
    vocal = vocal_dir / "vocal.wav"
    backing = vocal_dir / "instrumental.wav"
    if not force and vocal.exists():
        log.info(f"复用人声：{vocal.name}")
        return vocal, (backing if backing.exists() else None)

    src_wav = separate.ensure_wav(src, vocal_dir)
    result = separate.separate(src_wav, vocal_dir, cfg)
    if result.vocal != vocal and result.vocal.exists():
        # 分离器输出在别的目录才移动；指向源文件时用复制，保住 1-源文件 缓存
        if result.vocal.parent == vocal_dir:
            result.vocal.replace(vocal)
        else:
            shutil.copy2(result.vocal, vocal)
    keep_backing = bool(cfg.get("separate", {}).get("keep_backing", True))
    if not keep_backing and backing.exists():
        backing.unlink(missing_ok=True)
        log.info("按配置丢弃伴奏（separate.keep_backing=false）")

    if result.instrumental and result.instrumental.exists() and result.instrumental != backing:
        if result.instrumental.parent == vocal_dir:
            result.instrumental.replace(backing)
        else:
            shutil.copy2(result.instrumental, backing)
    return vocal, (backing if backing.exists() else None)


def _stage_convert(vocal: Path, song_dir: Path, cfg: dict, force: bool) -> Path:
    out = song_dir / STAGE_CONVERTED / "converted.wav"
    if not force and out.exists() and not _newer(_model_path(cfg), out):
        log.info(f"复用转换结果：{out.name}")
        return out

    shift = int(cfg.get("convert", {}).get("pitch", 0) or 0)
    local_cfg = dict(cfg)
    local_cfg["convert"] = {**cfg.get("convert", {}), "pitch": shift}
    return convert.convert(vocal, out, local_cfg)


def _model_path(cfg: dict) -> Path | None:
    return convert.resolve_model_path(cfg)


def _newer(a: Path | None, b: Path) -> bool:
    if a is None or not a.exists():
        return False
    return a.stat().st_mtime > b.stat().st_mtime


def _print_plan(cfg: dict, song_dir: Path, full: bool) -> None:
    conf = cfg.get("separate", {})
    conv = cfg.get("convert", {})
    log.info("将执行：")
    log.info(f"  源文件  → {song_dir / STAGE_SOURCE}")
    log.info(f"  分离    → {conf.get('backend')} / {conf.get('model')}")
    log.info(f"  转换    → {conv.get('backend')} / 模型 {conv.get('model')}")
    log.info(f"  混音    → {'归一' if cfg.get('mix', {}).get('normalize') else '原样'}")
    if full:
        log.info(f"  切段    → 每段 {cfg.get('clip', {}).get('full_segment_seconds')}s")
    else:
        log.info(f"  挑段    → 副歌 {cfg.get('clip', {}).get('seconds')}s")
    log.info("（dry-run，没有真的执行）")


def _maybe_publish(audio: Path, name: str, cfg: dict, result: dict) -> None:
    """send.enabled 打开时，把成品交给发布插件（默认关，本地用户不需要）。"""
    conf = cfg.get("send", {}) or {}
    if not conf.get("enabled"):
        return
    provider_name = str((cfg.get("providers") or {}).get("publish") or "local_folder")
    try:
        from ..providers import get_publish

        provider = get_publish(provider_name)
        where = provider.send(audio, {"name": name, "song": name, "target": conf.get("target"), "account": conf.get("account")}, cfg)
        result["published"] = where
        log.done(f"已发布：{where}")
    except Exception as exc:
        log.warn(f"发布失败（成品还在本地）：{exc}")