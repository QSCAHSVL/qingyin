"""挑段：自动找副歌/高潮，或按全曲切段。

用纯 Python 算 RMS 能量，不依赖 numpy：把音频解成 8kHz 单声道 PCM，
按 0.5 秒一个窗口算能量，再滑窗找最响的连续 N 秒。
"""

from __future__ import annotations

import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..utils import ffmpeg, log

SAMPLE_RATE = 8000
WINDOW_SECONDS = 0.5


@dataclass
class ClipResult:
    start: float
    seconds: float
    path: Path


def pick_chorus(src: Path, seconds: float, cfg: dict) -> ClipResult:
    """按 clip.mode 挑段：chorus（默认，找最响）/ start（从头）/ middle（中间）/ full（整首）。"""
    total = ffmpeg.duration(src)
    if total <= 0:
        raise RuntimeError(f"读不到时长：{src}")

    clip_cfg = cfg.get("clip", {}) or {}
    mode = str(clip_cfg.get("mode", "chorus")).lower()
    if mode in ("full", "整首", "all"):
        log.info("按配置整首输出")
        return ClipResult(start=0.0, seconds=total, path=src)
    if seconds >= total:
        log.info(f"歌曲只有 {total:.1f}s，直接整首")
        return ClipResult(start=0.0, seconds=total, path=src)
    if mode == "start":
        log.info("按配置从开头截取")
        return ClipResult(start=0.0, seconds=seconds, path=src)
    if mode == "middle":
        start = max(0.0, (total - seconds) / 2)
        log.info(f"按配置取中段 {start:.1f}s 起")
        return ClipResult(start=start, seconds=seconds, path=src)

    energies = _window_energies(src, float(clip_cfg.get("energy_window", 0.5) or 0.5))
    if not energies:
        log.warn("算不出能量曲线，退回从中间截取")
        start = max(0.0, (total - seconds) / 2)
        return ClipResult(start=start, seconds=seconds, path=src)

    window = float((cfg.get("clip", {}) or {}).get("energy_window", 0.5) or 0.5)
    per_second = 1.0 / window
    span = max(1, round(seconds * per_second))
    if span >= len(energies):
        return ClipResult(start=0.0, seconds=total, path=src)

    best_start, best_score = 0, -1.0
    running = sum(energies[:span])
    for i in range(len(energies) - span):
        if running > best_score:
            best_score, best_start = running, i
        running += energies[i + span] - energies[i]

    start = best_start * window
    # 稍微避开开头结尾的淡入淡出
    start = min(max(0.0, start), max(0.0, total - seconds))
    log.info(f"挑中 {start:.1f}s 起的 {seconds:.0f}s 片段（能量峰值）")
    return ClipResult(start=start, seconds=seconds, path=src)


def export(src: Path, result: ClipResult, dst: Path) -> Path:
    if result.path == src and result.start == 0.0 and result.seconds >= ffmpeg.duration(src):
        return ffmpeg.to_wav(src, dst, channels=2)
    return ffmpeg.slice_audio(src, dst, result.start, result.seconds)


def split_full(src: Path, segment_seconds: float, out_dir: Path) -> list[Path]:
    """全曲模式：切成固定长度，供语音条发送。"""
    total = ffmpeg.duration(src)
    out_dir.mkdir(parents=True, exist_ok=True)
    parts: list[Path] = []
    index = 1
    start = 0.0
    while start < total - 0.05:
        seconds = min(segment_seconds, total - start)
        dst = out_dir / f"part{index:02d}.wav"
        ffmpeg.slice_audio(src, dst, start, seconds)
        parts.append(dst)
        start += segment_seconds
        index += 1
    log.info(f"全曲切成 {len(parts)} 段（每段 {segment_seconds:.0f}s）")
    return parts


def _window_energies(src: Path, window_seconds: float = WINDOW_SECONDS) -> list[float]:
    """解码成 8k 单声道 PCM，按窗口算 RMS。"""
    ffmpeg_path = ffmpeg._which("ffmpeg")
    proc = subprocess.run(
        [
            ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(src),
            "-f",
            "s16le",
            "-ac",
            "1",
            "-ar",
            str(SAMPLE_RATE),
            "pipe:1",
        ],
        capture_output=True,
    )
    if proc.returncode != 0 or not proc.stdout:
        return []
    raw = proc.stdout
    step = max(2, int(SAMPLE_RATE * max(0.1, window_seconds))) * 2  # 16bit
    energies: list[float] = []
    for offset in range(0, len(raw) - step + 1, step):
        chunk = raw[offset : offset + step]
        samples = struct.unpack(f"<{len(chunk) // 2}h", chunk)
        if not samples:
            continue
        energies.append((sum(s * s for s in samples) / len(samples)) ** 0.5)
    return energies
