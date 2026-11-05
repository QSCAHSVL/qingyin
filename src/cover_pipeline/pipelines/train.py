"""train 流程：素材 → 清洗切分 → 特征 → 训练 → 导出推理模型。

两条路：
1. 装了 RVC 训练依赖时，调它的训练入口（`train.command` 模板优先）；
2. 否则把「清洗 + 切分」做完，输出一个标准数据集目录，并打印下一步要跑什么。

对新手来说，第 2 步的价值已经很大：素材怎么处理、要多少、怎么切，都自动做好了。
"""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from ..utils import ffmpeg, log

AUDIO_SUFFIXES = {".wav", ".flac", ".mp3", ".m4a", ".ogg", ".opus"}
SEGMENT_SECONDS = 8.0
MIN_SEGMENT_SECONDS = 2.5


def run(data_dir: Path, name: str, cfg: dict, *, dry_run: bool = False, on_progress=None) -> dict:
    def report(value: float, message: str) -> None:
        if on_progress:
            try:
                on_progress(value, message)
            except Exception:
                pass

    train_cfg = cfg.get("train", {})
    report(0.03, "扫描素材")
    work_root = Path(cfg["project"]["work_dir"])
    dataset_dir = work_root / name / "0-数据集"
    dataset_dir.mkdir(parents=True, exist_ok=True)

    files = _collect(data_dir)
    if not files:
        raise RuntimeError(f"没在 {data_dir} 里找到音频文件（支持 {', '.join(sorted(AUDIO_SUFFIXES))}）")

    total_seconds = sum(ffmpeg.duration(p) for p in files)
    minutes = total_seconds / 60
    log.step(f"素材：{len(files)} 个文件，共 {minutes:.1f} 分钟")

    warn = float(train_cfg.get("min_minutes_warn", 10) or 10)
    if minutes < warn:
        log.warn(f"素材偏少（建议至少 {warn:.0f} 分钟），效果可能不稳定")

    if dry_run:
        log.info(f"将清洗并切分到：{dataset_dir}")
        log.info(f"训练轮数：{train_cfg.get('epochs')}")
        return {"dry_run": True, "files": len(files), "minutes": round(minutes, 1)}

    epochs = int(train_cfg.get("epochs", 80) or 80)
    if epochs < 20 and str(train_cfg.get("command") or ""):
        log.warn(
            f"训练轮数只有 {epochs}：RVC 默认每 20 轮才存一次检查点，"
            "轮数太少会导不出模型（train_model.py 用的是 -se 20）。建议 ≥20。"
        )

    report(0.08, f"切分素材（{len(files)} 个文件）")
    segments = _prepare_segments(files, dataset_dir, cfg)
    report(0.2, f"数据集就绪（{len(segments)} 段）")
    if train_cfg.get("clean", True):
        before = len(segments)
        segments = _filter_quiet(segments, cfg)
        if len(segments) != before:
            log.info(f"清洗掉 {before - len(segments)} 段过安静的片段")
    if not segments:
        raise RuntimeError("清洗后没有可用片段：素材是不是几乎全是静音/噪声？")
    log.done(f"数据集就绪：{len(segments)} 段 → {dataset_dir}")

    command = train_cfg.get("command")
    if command:
        report(0.25, "开始训练（外部命令，可能要几十分钟）")
        _run_external(command, dataset_dir, name, cfg)
        report(0.9, "训练完成，登记模型版本")
        version = _register_result(name, cfg, train_cfg)
        report(1.0, "完成")
        return {"segments": len(segments), "dataset": str(dataset_dir), "version": version}

    log.warn(
        "没配置 train.command，训练未执行。\n"
        "  数据集已经准备好，你可以：\n"
        "  1) 在 configs/local.yaml 里设置 train.command，指向 RVC 的训练命令模板\n"
        "  2) 或者用 RVC WebUI 直接加载这个数据集目录训练\n"
        "  占位符：{dataset} {name} {epochs} {batch} {sample_rate}"
    )
    return {"segments": len(segments), "dataset": str(dataset_dir), "trained": False}


def _collect(data_dir: Path) -> list[Path]:
    if data_dir.is_file():
        return [data_dir]
    out: list[Path] = []
    for path in data_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() in AUDIO_SUFFIXES:
            out.append(path)
    return sorted(out)


def _prepare_segments(files: list[Path], dataset_dir: Path, cfg: dict) -> list[Path]:
    """统一采样率、去静音、切段。"""
    sample_rate = int(cfg.get("train", {}).get("sample_rate", 40000) or 40000)
    segments: list[Path] = []
    index = 1
    for src in files:
        try:
            wav = dataset_dir / f"_src_{index:03d}.wav"
            ffmpeg.to_wav(src, wav, sample_rate=sample_rate, channels=1)
        except Exception as exc:
            log.warn(f"跳过 {src.name}：{exc}")
            index += 1
            continue

        duration = ffmpeg.duration(wav)
        offset = 0.0
        while offset < duration:
            seconds = min(SEGMENT_SECONDS, duration - offset)
            if seconds < MIN_SEGMENT_SECONDS:
                break
            seg = dataset_dir / f"seg_{len(segments) + 1:04d}.wav"
            ffmpeg.slice_audio(wav, seg, offset, seconds)
            segments.append(seg)
            offset += SEGMENT_SECONDS
        wav.unlink(missing_ok=True)
        index += 1
    return segments


def _run_external(template: str, dataset_dir: Path, name: str, cfg: dict) -> None:
    train_cfg = cfg.get("train", {})
    mapping = {
        "{dataset}": str(dataset_dir),
        "{name}": name,
        "{model_name}": str(train_cfg.get("model_name") or name),
        "{epochs}": str(train_cfg.get("epochs", 80)),
        "{batch}": str(train_cfg.get("batch_size", 4)),
        "{sample_rate}": str(train_cfg.get("sample_rate", 40000)),
        "{rvc_dir}": str((cfg.get("tools") or {}).get("rvc_dir") or ""),
        "{rvc_python}": str((cfg.get("tools") or {}).get("rvc_python") or "python"),
    }
    cmd = template
    for key, value in mapping.items():
        cmd = cmd.replace(key, value)
    log.step("开始训练（外部命令）")
    log.debug(cmd)
    proc = subprocess.run(shlex.split(cmd, posix=False), text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError(f"训练命令失败（{proc.returncode}）")
    log.done("训练完成")


def _register_result(name: str, cfg: dict, train_cfg: dict) -> dict | None:
    """训练完把导出的 .pth 登记成新版本，方便以后切回旧版。"""
    from ..models import register

    out_dir = Path(train_cfg.get("output_dir") or cfg["project"]["work_dir"]) / name
    search_roots: list[Path] = [out_dir, Path(train_cfg.get("output_dir") or "."), Path(cfg["project"]["work_dir"]) / name]
    for extra in train_cfg.get("output_dirs") or []:
        search_roots.append(Path(str(extra)).expanduser())
    rvc_dir = Path(str((cfg.get("tools") or {}).get("rvc_dir") or "")).expanduser()
    if rvc_dir:
        search_roots.append(rvc_dir / "assets" / "weights")

    model_name = str(train_cfg.get("model_name") or name)
    candidates: list[Path] = []
    for root in search_roots:
        if not root.exists():
            continue
        exact = root / f"{model_name}.pth"
        if exact.exists():
            candidates.append(exact)
        candidates.extend(sorted(root.rglob("*.pth"), key=lambda p: p.stat().st_mtime, reverse=True))
    if not candidates:
        log.warn("训练完成了但没找到导出的 .pth；用 `cover models import <文件>` 手动登记")
        return None
    newest = candidates[0]
    info = register(
        cfg,
        voice=name,
        source=newest,
        meta={
            "epochs": train_cfg.get("epochs"),
            "dataset_segments": len(list((Path(cfg["project"]["work_dir"]) / name / "0-数据集").glob("seg*.wav"))),
            "source_file": newest.name,
        },
    )
    log.done(f"已登记模型版本：{info['voice']} {info['version']}（当前生效）")
    return info

def _filter_quiet(segments: list[Path], cfg: dict) -> list[Path]:
    """丢掉平均音量太低的片段（底噪、纯伴奏段），训练时更干净。"""
    threshold = float((cfg.get("train", {}) or {}).get("clean_threshold_db", -40) or -40)
    kept: list[Path] = []
    for seg in segments:
        try:
            mean_db = _mean_volume(seg)
        except Exception:
            kept.append(seg)
            continue
        if mean_db is None or mean_db >= threshold:
            kept.append(seg)
        else:
            seg.unlink(missing_ok=True)
    return kept


def _mean_volume(path: Path) -> float | None:
    import re

    from ..utils import ffmpeg

    out = ffmpeg.run(
        ["ffmpeg", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
        quiet=False,
    )
    match = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", (out.stderr or "") + (out.stdout or ""))
    return float(match.group(1)) if match else None


def preview(data_dir: Path, cfg: dict) -> dict:
    """训练前预检：素材时长、预计段数、配置是否就绪。"""
    train_cfg = cfg.get("train", {})
    files = _collect(Path(data_dir))
    total = 0.0
    unreadable = 0
    for path in files:
        try:
            total += ffmpeg.duration(path)
        except Exception:
            unreadable += 1
    minutes = total / 60
    warn_minutes = float(train_cfg.get("min_minutes_warn", 10) or 10)
    epochs = int(train_cfg.get("epochs", 80) or 80)

    warnings: list[str] = []
    if not files:
        warnings.append("这个目录里没找到音频（支持 wav/flac/mp3/m4a/ogg）")
    if files and minutes < warn_minutes:
        warnings.append(f"素材只有 {minutes:.1f} 分钟，建议至少 {warn_minutes:.0f} 分钟")
    if unreadable:
        warnings.append(f"有 {unreadable} 个文件读不出时长，会被跳过")
    if epochs < 20:
        warnings.append("训练轮数少于 20，RVC 可能存不出检查点（建议 ≥20）")

    command = str(train_cfg.get("command") or "").strip()
    return {
        "data_dir": str(Path(data_dir)),
        "files": len(files),
        "minutes": round(minutes, 1),
        "segments_est": int(total // SEGMENT_SECONDS) if total else 0,
        "epochs": epochs,
        "batch_size": int(train_cfg.get("batch_size", 4) or 4),
        "sample_rate": int(train_cfg.get("sample_rate", 40000) or 40000),
        "clean": bool(train_cfg.get("clean", True)),
        "model_name": str(train_cfg.get("model_name") or ""),
        "command_configured": bool(command),
        "command_hint": command[:160] if command else "",
        "warnings": warnings,
        "estimate_minutes": round(max(5.0, minutes * 1.2 + epochs * 0.6), 0),
    }
