"""ffmpeg / ffprobe 封装。所有音频读写都走这里，方便统一换实现。"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from . import log


class FFmpegMissing(RuntimeError):
    pass


_bin_dir: Path | None = None


def configure(bin_dir: str | Path | None) -> None:
    """指定 ffmpeg/ffprobe 所在目录（没在 PATH 里时用）。

    优先看配置 `tools.ffmpeg_dir`，其次环境变量 FFMPEG_DIR。
    """
    global _bin_dir
    raw = bin_dir or os.environ.get("FFMPEG_DIR") or ""
    _bin_dir = Path(raw).expanduser() if raw else None


def bin_dir() -> Path | None:
    return _bin_dir


def _which(name: str) -> str:
    if _bin_dir:
        candidate = _bin_dir / (name + (".exe" if os.name == "nt" else ""))
        if candidate.exists():
            return str(candidate)
        plain = _bin_dir / name
        if plain.exists():
            return str(plain)
    path = shutil.which(name)
    if not path:
        raise FFmpegMissing(
            f"找不到 {name}。两种办法：\n"
            "  1) 安装并加入 PATH（Windows：winget install Gyan.FFmpeg，装完重开终端）\n"
            "  2) 在 configs/local.yaml 里设置 tools.ffmpeg_dir 指向 ffmpeg 的 bin 目录"
        )
    return path


def has_ffmpeg() -> bool:
    try:
        _which("ffmpeg")
        _which("ffprobe")
        return True
    except FFmpegMissing:
        return False


def run(args: list[str], quiet: bool = True, cancel_event=None) -> subprocess.CompletedProcess:
    if args and args[0] in {"ffmpeg", "ffprobe"}:
        args = [_which(args[0]), *args[1:]]
    cmd = [args[0], "-hide_banner", "-loglevel", "error" if quiet else "info", *args[1:]]
    log.debug(" ".join(cmd))
    if cancel_event is None:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if proc.returncode != 0:
            raise RuntimeError(f"命令失败：{' '.join(cmd)}\n{proc.stderr[-2000:]}")
        return proc

    from . import proc as proc_util

    try:
        out, err = proc_util.run(cmd, cancel_event=cancel_event)
    except Exception as exc:
        raise RuntimeError(f"命令失败：{' '.join(cmd)}\n{exc}") from exc
    return subprocess.CompletedProcess(cmd, 0, out, err)


def duration(path: Path) -> float:
    """返回音频时长（秒）。"""
    ffprobe = _which("ffprobe")
    proc = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError(f"读取时长失败：{path}\n{proc.stderr[-1000:]}")
    data = json.loads(proc.stdout or "{}")
    return float(data.get("format", {}).get("duration", 0.0) or 0.0)


def to_wav(src: Path, dst: Path, sample_rate: int | None = None, channels: int = 1) -> Path:
    """转成 PCM wav（默认单声道，训练/分离前统一格式）。"""
    ffmpeg = _which("ffmpeg")
    dst.parent.mkdir(parents=True, exist_ok=True)
    args = [ffmpeg, "-y", "-i", str(src)]
    if sample_rate:
        args += ["-ar", str(sample_rate)]
    args += ["-ac", str(channels), str(dst)]
    run(args)
    return dst


def slice_audio(src: Path, dst: Path, start: float, seconds: float) -> Path:
    ffmpeg = _which("ffmpeg")
    dst.parent.mkdir(parents=True, exist_ok=True)
    run([ffmpeg, "-y", "-ss", f"{start:.3f}", "-t", f"{seconds:.3f}", "-i", str(src), str(dst)])
    return dst


def concat(parts: list[Path], dst: Path) -> Path:
    """按顺序拼接（先转成同格式再 concat）。"""
    if not parts:
        raise ValueError("没有可拼接的文件")
    ffmpeg = _which("ffmpeg")
    list_file = dst.parent / "concat.txt"
    list_file.parent.mkdir(parents=True, exist_ok=True)
    list_file.write_text(
        "\n".join(f"file '{p.as_posix()}'" for p in parts), encoding="utf-8"
    )
    run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), str(dst)])
    list_file.unlink(missing_ok=True)
    return dst


def loudness(src: Path) -> float:
    """粗略响度（LUFS 近似）：用 ffmpeg volumedetect 的 mean_volume。"""
    ffmpeg = _which("ffmpeg")
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(src), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    for line in (proc.stderr or "").splitlines():
        if "mean_volume:" in line:
            try:
                return float(line.split("mean_volume:")[1].strip().split()[0])
            except (IndexError, ValueError):
                break
    return -99.0
