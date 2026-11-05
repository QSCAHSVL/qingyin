"""混音：人声 + 伴奏，带增益、暖色补偿与响度归一。"""

from __future__ import annotations

import math
from pathlib import Path

from ..utils import ffmpeg, log


def mix(vocal: Path, instrumental: Path | None, out_path: Path, cfg: dict) -> Path:
    conf = cfg.get("mix", {})
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if instrumental is None:
        log.info("没有伴奏，直接使用人声")
        return ffmpeg.to_wav(vocal, out_path, channels=2)

    vocal_db = _to_db(conf, "vocal_gain", "vocal_gain_db")
    backing_db = _to_db(conf, "backing_gain", "backing_gain_db")
    warmth_db = float(conf.get("warmth_db", 0) or 0)
    limiter = bool(conf.get("limiter"))

    log.step("混音")
    _amix(vocal, instrumental, out_path, vocal_db, backing_db, warmth_db, limiter, cfg)

    if conf.get("normalize", True):
        _normalize(out_path, float(conf.get("target_lufs", -14) or -14), cfg)

    log.done(f"混音完成：{out_path.name}")
    return out_path


def _to_db(conf: dict, linear_key: str, db_key: str) -> float:
    """同时支持线性倍数（2.5）和 dB（+8）两种写法。"""
    if conf.get(db_key) is not None:
        return float(conf.get(db_key) or 0)
    value = conf.get(linear_key)
    if value is None:
        return 0.0
    value = float(value)
    if value <= 0:
        return 0.0
    return round(20 * math.log10(value), 2)


def _amix(
    vocal: Path,
    backing: Path,
    out_path: Path,
    vocal_db: float,
    backing_db: float,
    warmth_db: float,
    limiter: bool,
    cfg: dict,
) -> None:
    chain = (
        f"[0:a]volume={vocal_db}dB[v];"
        f"[1:a]volume={backing_db}dB[b];"
        f"[v][b]amix=inputs=2:duration=longest:normalize=0[out]"
    )
    if warmth_db:
        chain += f";[out]equalizer=f=250:t=q:w=1.0:g={warmth_db}[warm]"
        tail = "[warm]"
    else:
        tail = "[out]"
    if limiter:
        chain += f";{tail}alimiter=limit=0.89[lim]"
        tail = "[lim]"

    ffmpeg.run(
        [
            "ffmpeg", "-y",
            "-i", str(vocal),
            "-i", str(backing),
            "-filter_complex", chain,
            "-map", tail,
            str(out_path),
        ],
        cancel_event=cfg.get("_cancel_event"),
    )


def _normalize(path: Path, target_db: float, cfg: dict | None = None) -> None:
    """按均值响度做一次简单归一到目标 LUFS 附近（近似，够用）。"""
    current = ffmpeg.loudness(path)
    if current <= -90:
        return
    delta = target_db - current
    if abs(delta) < 1.0:
        return
    log.info(f"响度归一：{current:.1f} → {target_db:.1f} dB（{delta:+.1f}）")
    tmp = path.with_suffix(".norm.wav")
    ffmpeg.run(
        ["ffmpeg", "-y", "-i", str(path), "-af", f"volume={delta}dB", str(tmp)],
        cancel_event=(cfg or {}).get("_cancel_event"),
    )
    tmp.replace(path)
