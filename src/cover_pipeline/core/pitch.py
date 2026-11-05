"""自动降调：按源人声音高判断要不要整体降 1~3 个半音。

思路：取人声的中位基频，和「舒适区」比较。
- 源人声偏高（比如女声原曲给男声音色唱），整体降调更自然
- 算不出来就不动，宁可不改也不要瞎改

依赖 librosa 时更准；没装就返回 0（保持原调）。
"""

from __future__ import annotations

import statistics
from pathlib import Path

from ..utils import log

# 认为「偏高」的阈值（Hz）：中位基频超过这个值就考虑降调
HIGH_PITCH_HZ = 320.0
LOW_PITCH_HZ = 120.0


def estimate_shift(vocal: Path, cfg: dict) -> int:
    conf = cfg.get("convert", {})
    if not conf.get("auto_pitch", True):
        return int(conf.get("pitch", 0) or 0)

    low, high = conf.get("auto_pitch_range", [-3, 3])
    try:
        median = _median_f0(vocal)
    except Exception as exc:  # 依赖缺失或分析失败
        log.debug(f"音高分析跳过：{exc}")
        return 0

    if median <= 0:
        return 0
    log.info(f"源人声中位基频 ≈ {median:.0f} Hz")

    if median >= HIGH_PITCH_HZ:
        shift = -min(int(high) * -1 if high < 0 else 2, 3)
    elif median <= LOW_PITCH_HZ:
        shift = 1
    else:
        shift = 0

    shift = max(int(low), min(int(high), shift))
    if shift:
        log.info(f"自动变调：{shift:+d} 半音")
    return shift


def _median_f0(path: Path) -> float:
    import librosa  # 延迟导入
    import numpy as np

    y, sr = librosa.load(str(path), sr=22050, mono=True, duration=60.0)
    f0, voiced_flag, _ = librosa.pyin(
        y,
        fmin=float(librosa.note_to_hz("C2")),
        fmax=float(librosa.note_to_hz("C6")),
        sr=sr,
    )
    values = [float(v) for v, ok in zip(f0, voiced_flag) if ok and v and not np.isnan(v)]
    if not values:
        return 0.0
    return statistics.median(values)


def shift_file(src: Path, semitones: int, out_path: Path, cfg: dict | None = None) -> Path:
    """整首移调：改采样率再计时补偿，避免变速。"""
    if not semitones:
        return Path(src)
    ratio = 2 ** (semitones / 12)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg.run(
        [
            "ffmpeg", "-y", "-i", str(src),
            "-af", f"asetrate=44100*{ratio:.6f},aresample=44100,atempo={1/ratio:.6f}",
            str(out_path),
        ],
        cancel_event=(cfg or {}).get("_cancel_event"),
    )
    return out_path