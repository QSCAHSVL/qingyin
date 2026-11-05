"""几个 service 都要用的小工具。"""

from __future__ import annotations

from pathlib import Path


def ffmpeg_duration(path: Path) -> float:
    """音频时长（秒）；ffmpeg 拿不到时由调用方兜底。"""
    from ...utils import ffmpeg

    return ffmpeg.duration(path)


def gpu_used_gb() -> float:
    """nvidia-smi 查当前显存占用；没有 N 卡就返回 0。"""
    import subprocess

    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=8,
        )
        return round(float(out.stdout.strip().splitlines()[0]) / 1024, 1)
    except Exception:
        return 0.0


def is_inside(path: Path, root: Path) -> bool:
    """path 是否在 root 目录里（用于限制只读项目目录内的文件）。"""
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
