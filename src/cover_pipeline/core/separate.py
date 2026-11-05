"""人声分离。

默认走 UVR（audio-separator）后端；没装依赖时给出可操作的提示，而不是堆栈。
想换 Demucs 或自建模型，实现同样的 `separate()` 签名即可。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..utils import ffmpeg, log


@dataclass
class SeparationResult:
    vocal: Path
    instrumental: Path | None


def _uvr_available() -> bool:
    try:
        import audio_separator  # noqa: F401
    except Exception:
        return False
    return True


def separate(src: Path, out_dir: Path, cfg: dict) -> SeparationResult:
    """把 src 拆成人声与伴奏。"""
    conf = cfg.get("separate", {})
    backend = str(conf.get("backend", "local_uvr")).lower()
    out_dir.mkdir(parents=True, exist_ok=True)

    if backend == "none":
        log.info("跳过分离（separate.backend=none）")
        return SeparationResult(vocal=src, instrumental=None)

    if backend in ("local_uvr", "local"):
        return _separate_local_uvr(src, out_dir, conf, cfg)

    if backend == "uvr":
        return _separate_uvr(src, out_dir, conf)

    if backend == "demucs":
        return _separate_demucs(src, out_dir, conf, cfg)

    raise ValueError(
        f"不支持的人声分离后端：{backend}"
        "（支持 local_uvr / uvr / demucs / none）"
    )


def _separate_local_uvr(src: Path, out_dir: Path, conf: dict, cfg: dict) -> SeparationResult:
    """用本地已部署的 UVR5 helper（uvr_sep.py）分离。"""

    from .. import probe

    local = cfg.get("local") or probe.local_installs(cfg)
    uvr = local.get("uvr", {})
    if not uvr.get("ok"):
        raise RuntimeError(
            "没找到本地 UVR。两种办法：\n"
            "  1) 跑 `cover link --uvr-script <uvr_sep.py> --uvr-python <python.exe>` 指过去\n"
            "  2) 或者装 pip 版：pip install audio-separator[gpu]，然后把 separate.backend 改成 uvr"
        )

    model = str(conf.get("local_model") or uvr.get("model") or "roformer")
    log.step(f"人声分离（本地 UVR · {model}）")
    cmd = [uvr["python"], uvr["script"], str(src), str(out_dir), "--model", model]
    from ..utils import proc as proc_util

    try:
        proc_util.run(
            cmd,
            cwd=str(Path(uvr["script"]).parent),
            cancel_event=cfg.get("_cancel_event"),
            timeout=1800,
        )
    except Exception as exc:
        raise RuntimeError(f"UVR 分离失败：\n{exc}") from exc

    vocal = out_dir / "人声.wav"
    backing = out_dir / "伴奏.wav"
    if not vocal.exists():
        raise RuntimeError(f"分离跑完了但没看到人声输出：{out_dir}")
    log.done(f"分离完成：{vocal.name}" + (f"，{backing.name}" if backing.exists() else "，无伴奏"))
    return SeparationResult(vocal=vocal, instrumental=backing if backing.exists() else None)


def _separate_uvr(src: Path, out_dir: Path, conf: dict) -> SeparationResult:
    if not _uvr_available():
        raise RuntimeError(
            "没装人声分离依赖。请执行：pip install audio-separator[cpu]（有 CUDA 显卡用 audio-separator[gpu]）"
        )

    from audio_separator.separator import Separator  # 延迟导入

    model = str(conf.get("model", "UVR-MDX-NET-Inst_HQ_3"))
    log.step(f"人声分离（{model}）")
    sep = Separator(
        model_file_dir=str(out_dir / "_models"),
        output_dir=str(out_dir),
        output_format="wav",
    )
    sep.load_model(model_filename=model)
    outputs = sep.separate(str(src))

    vocal = _pick(outputs, out_dir, ("vocal", "人声", "voice"))
    inst = _pick(outputs, out_dir, ("instrumental", "伴奏", "no_vocal", "accompaniment"), required=False)
    if vocal is None:
        raise RuntimeError(f"分离完成但没找到人声输出：{outputs}")
    log.done(f"分离完成：人声 {vocal.name}" + (f"，伴奏 {inst.name}" if inst else "，无伴奏"))
    return SeparationResult(vocal=vocal, instrumental=inst)


def _pick(outputs: list[str], out_dir: Path, keywords: tuple[str, ...], required: bool = True) -> Path | None:
    for name in outputs:
        path = Path(name)
        if not path.is_absolute():
            path = out_dir / path.name
        lowered = path.name.lower()
        if any(k in lowered for k in keywords):
            return path
    if required:
        return None
    return None


def ensure_wav(src: Path, work_dir: Path) -> Path:
    """统一转成 44.1k 单声道 wav，减少后续步骤的格式差异。"""
    if src.suffix.lower() == ".wav":
        return src
    dst = work_dir / f"{src.stem}.wav"
    if dst.exists():
        return dst
    log.info(f"转码：{src.name} → {dst.name}")
    return ffmpeg.to_wav(src, dst, sample_rate=44100, channels=1)


def _demucs_available() -> bool:
    try:
        import demucs  # noqa: F401
    except Exception:
        return False
    return True


def _separate_demucs(src: Path, out_dir: Path, conf: dict, cfg: dict) -> SeparationResult:
    """用 Demucs（htdemucs）分离：输出人声与伴奏。

    比 UVR 慢一点，但人声残留少，适合 UVR 分不干净的歌。
    """
    import shutil
    import sys

    from ..utils import proc

    if not _demucs_available():
        raise RuntimeError(
            "没装 Demucs。装一下：pip install demucs\n"
            "  或者把 separate.backend 改回 local_uvr，用本机已有的 UVR"
        )

    model = str(conf.get("demucs_model", "htdemucs"))
    log.info(f"用 Demucs 分离（{model}）…")
    work = out_dir / "_demucs"
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)

    cmd = [sys.executable, "-m", "demucs", "--two-stems", "vocals", "-n", model, "-o", str(work), str(src)]
    proc.run(cmd, cancel_event=cfg.get("_cancel_event"), timeout=3600)

    # demucs 输出结构：<out>/<model>/<曲名>/vocals.wav 与 no_vocals.wav
    stems = sorted(work.rglob("vocals.wav"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not stems:
        raise RuntimeError(f"Demucs 跑完了但没找到 vocals.wav（输出目录：{work}）")
    vocal_src = stems[0]
    backing_src = vocal_src.with_name("no_vocals.wav")

    vocal = out_dir / "vocal.wav"
    shutil.copy2(vocal_src, vocal)
    instrumental = None
    if backing_src.exists() and bool(conf.get("keep_backing", True)):
        instrumental = out_dir / "instrumental.wav"
        shutil.copy2(backing_src, instrumental)
    shutil.rmtree(work, ignore_errors=True)
    log.done("Demucs 分离完成")
    return SeparationResult(vocal=vocal, instrumental=instrumental)
