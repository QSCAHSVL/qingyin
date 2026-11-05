"""音色转换。

三种接入方式：
1. `local_rvc`：直接用本机已装好的 RVC（默认）——调用 `python -m infer.cli`，
   和 cover-automation 里跑通的是同一条路，长音频自动分块 + 预热裁边拼接。
2. `rvc`：装 pip 包 `rvc-python` 时调用它的 API。
3. 外部命令模板：`convert.command`，把占位符替换掉执行，接任何自己的实现。
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

from ..utils import ffmpeg, log


def convert(vocal: Path, out_path: Path, cfg: dict) -> Path:
    conf = cfg.get("convert", {})
    backend = str(conf.get("backend", "local_rvc")).lower()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if backend == "none":
        log.info("跳过音色转换（convert.backend=none）")
        return vocal

    model_path = resolve_model_path(cfg)
    if model_path is None:
        raise RuntimeError(
            "没找到音色模型。请先 `cover train` 训练，或把 .pth 放到 models/ 下并在配置里写 convert.model。"
        )

    if conf.get("command"):
        return _run_external(str(conf["command"]), vocal, out_path, model_path, cfg)

    if backend in ("local_rvc", "local"):
        return _convert_local_rvc(vocal, out_path, model_path, cfg, conf)

    if backend == "rvc":
        return _convert_pip_rvc(vocal, out_path, model_path, cfg, conf)

    raise ValueError(f"不支持的转换后端：{backend}（支持 local_rvc / rvc / none）")


# --------------------------------------------------------------------------- 本地 RVC

def _convert_local_rvc(vocal: Path, out_path: Path, model_path: Path, cfg: dict, conf: dict) -> Path:
    from .. import probe

    local = cfg.get("local") or probe.local_installs(cfg)
    rvc = local.get("rvc", {})
    if not rvc.get("ok"):
        raise RuntimeError(
            "没找到本地 RVC。两种办法：\n"
            "  1) 跑 `cover link --rvc-dir <RVC目录> --rvc-python <python.exe>` 指过去\n"
            "  2) 或者装 pip 版：pip install rvc-python，然后把 convert.backend 改成 rvc"
        )

    log.step(f"音色转换（本地 RVC · {model_path.name}）")
    env = _rvc_env(cfg, rvc["dir"])
    pitch = int(conf.get("pitch", 0) or 0)
    protect = float(conf.get("protect", 0.5))
    f0_method = str(conf.get("f0_method", "rmvpe"))
    index_rate = float(conf.get("index_rate", 0.0) or 0.0)
    if not resolve_index_path(cfg):
        index_rate = 0.0  # 没有索引文件时传非零值会报错

    total = ffmpeg.duration(vocal)
    chunk = float(conf.get("chunk_seconds", 0) or 0) or _pick_chunk_seconds()
    join_mode = str(conf.get("join_mode", "trim")).lower()
    prewarm = float(conf.get("prewarm_seconds", 0.3) or 0.3)

    tmp_dir = Path(tempfile.mkdtemp(prefix="cover_rvc_"))
    try:
        if total > chunk + 10:
            out = _convert_chunked(
                vocal, tmp_dir, total, chunk, join_mode, prewarm,
                model_path, pitch, protect, f0_method, index_rate, env, rvc, cfg,
            )
        else:
            raw = tmp_dir / "single.wav"
            _rvc_cli(vocal, raw, model_path, pitch, protect, f0_method, index_rate, env, rvc, cfg)
            out = raw
        if not out.exists():
            raise RuntimeError("RVC 转换没有输出")
        shutil.move(str(out), str(out_path))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    log.done(f"转换完成：{out_path.name}")
    return out_path


def _convert_chunked(
    vocal: Path,
    tmp_dir: Path,
    total: float,
    chunk: float,
    join_mode: str,
    prewarm: float,
    model_path: Path,
    pitch: int,
    protect: float,
    f0_method: str,
    index_rate: float,
    env: dict,
    rvc: dict,
    cfg: dict | None = None,
) -> Path:
    """长音频分块转换，再按预热裁边的方式拼回去（避免接缝杂音）。"""
    overlap = 0.004 if join_mode == "trim" else 0.2
    pieces: list[Path] = []
    count = int(total // chunk) + (1 if total % chunk else 0)
    log.info(f"音频 {total:.0f}s，切成 {count} 段（每段 {chunk:.0f}s，接缝方式 {join_mode}）")

    for i in range(count):
        head = prewarm if (join_mode == "trim" and i > 0) else 0.0
        tail = prewarm if (join_mode == "trim" and i < count - 1) else 0.0
        if join_mode == "trim":
            start = max(0.0, i * chunk - head)
            seconds = chunk + head + tail
        else:
            start = max(0.0, i * chunk - (overlap if i else 0.0))
            seconds = chunk + (overlap if i else 0.0)

        piece_in = tmp_dir / f"chunk{i}.wav"
        piece_out = tmp_dir / f"chunk{i}_out.wav"
        ffmpeg.run(
            ["ffmpeg", "-y", "-i", str(vocal), "-ss", f"{start:.2f}", "-t", f"{seconds:.2f}",
             "-ar", "32000", "-ac", "1", str(piece_in)]
        )
        _rvc_cli(piece_in, piece_out, model_path, pitch, protect, f0_method, index_rate, env, rvc, cfg)

        if join_mode == "trim" and (head or tail):
            trimmed = tmp_dir / f"chunk{i}_trim.wav"
            ffmpeg.run(
                ["ffmpeg", "-y", "-i", str(piece_out), "-ss", f"{head:.3f}", "-t", f"{chunk:.3f}",
                 "-ar", "32000", "-ac", "1", str(trimmed)]
            )
            piece_out = trimmed
        pieces.append(piece_out)

    merged = tmp_dir / "merged.wav"
    inputs: list[str] = []
    for piece in pieces:
        inputs += ["-i", str(piece)]
    filters = []
    chain = "[0:a]"
    for idx in range(1, len(pieces)):
        filters.append(f"{chain}[{idx}:a]acrossfade=d={overlap:.3f}:c1=tri:c2=tri[x{idx}];")
        chain = f"[x{idx}]"
    ffmpeg.run(
        ["ffmpeg", "-y"] + inputs + ["-filter_complex", "".join(filters), "-map", chain,
                                     "-ar", "32000", "-ac", "1", str(merged)]
    )
    return merged


def _rvc_cli(
    src: Path,
    dst: Path,
    model_path: Path,
    pitch: int,
    protect: float,
    f0_method: str,
    index_rate: float,
    env: dict,
    rvc: dict,
    cfg: dict | None = None,
) -> None:
    cmd = [
        rvc["python"], "-m", "infer.cli",
        "--model", str(model_path),
        "--input", str(src),
        "--output", str(dst),
        "--pitch", str(pitch),
        "--f0-method", f0_method,
        "--index-rate", str(index_rate),
        "--protect", str(protect),
        "--rms-mix-rate", "0.3",
        "--format", "wav",
    ]
    from ..utils import proc as proc_util

    try:
        proc_util.run(
            cmd, cwd=str(rvc["dir"]), env=env,
            cancel_event=(cfg or {}).get("_cancel_event"), timeout=3600,
        )
    except Exception as exc:
        raise RuntimeError(f"RVC 转换失败：\n{exc}") from exc


def _rvc_env(cfg: dict, rvc_dir: str) -> dict:
    env = dict(os.environ)
    ff_dir = cfg.get("tools", {}).get("ffmpeg_dir") or ""
    if ff_dir:
        env["PATH"] = str(ff_dir) + os.pathsep + env.get("PATH", "")
    env["PYTHONPATH"] = str(rvc_dir) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
    gpu_index = (cfg.get("device", {}) or {}).get("gpu_index")
    if gpu_index not in (None, "", "auto"):
        env["CUDA_VISIBLE_DEVICES"] = str(gpu_index)
    return env


def _pick_chunk_seconds() -> float:
    """按当前显存余量挑分块时长（8G 卡实测：45s≈5.2G，60s≈6.2G）。"""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        free_gb = float(out.stdout.strip().splitlines()[0]) / 1024
    except Exception:
        return 45.0
    if free_gb >= 7.0:
        return 60.0
    if free_gb >= 5.0:
        return 45.0
    if free_gb >= 3.5:
        return 35.0
    return 25.0


# --------------------------------------------------------------------------- pip RVC

def _convert_pip_rvc(vocal: Path, out_path: Path, model_path: Path, cfg: dict, conf: dict) -> Path:
    try:
        from rvc_python.infer import RVCInference  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "没装 RVC 推理依赖。用本地 RVC 的话跑 `cover link` 指路径；"
            "要装 pip 版：pip install rvc-python"
        ) from exc

    log.step(f"音色转换（pip RVC · {model_path.name}）")
    rvc = RVCInference(device=str(cfg.get("device", {}).get("type", "auto")))
    rvc.load_model(str(model_path))
    rvc.infer_file(
        input_path=str(vocal),
        output_path=str(out_path),
        f0_up_key=int(conf.get("pitch", 0) or 0),
        f0_method=str(conf.get("f0_method", "rmvpe")),
        index_rate=float(conf.get("index_rate", 0.75)),
        protect=float(conf.get("protect", 0.5)),
    )
    log.done(f"转换完成：{out_path.name}")
    return out_path


# --------------------------------------------------------------------------- 模型 / 索引定位

def resolve_model_path(cfg: dict) -> Path | None:
    conf = cfg.get("convert", {})
    name = str(conf.get("model", "default"))

    # 版本库优先：models/<音色>/versions/... 里当前激活的那一版
    if name in ("default", ""):
        try:
            from ..models import active_model_path

            active = active_model_path(cfg)
            if active:
                return active
        except Exception:
            pass
    candidate = Path(name).expanduser()
    if candidate.suffix == ".pth" and candidate.exists():
        return candidate

    models_dir = Path(cfg.get("project", {}).get("models_dir", "./models"))
    local = cfg.get("local") or {}
    rvc_dir = (local.get("rvc") or {}).get("dir")

    search = [models_dir / f"{name}.pth", models_dir / name / f"{name}.pth"]
    if rvc_dir:
        search.append(Path(rvc_dir) / "assets" / "weights" / f"{name}.pth")
    for path in search:
        if path.exists():
            return path

    # 兜底：没指定具体模型时，优先找常见的默认名，再找唯一模型，最后挑最新的
    pools: list[list[Path]] = []
    if models_dir.exists():
        pools.append(sorted(models_dir.glob("*.pth")))
    if rvc_dir:
        weight_dir = Path(rvc_dir) / "assets" / "weights"
        if weight_dir.exists():
            pools.append(sorted(weight_dir.glob("*.pth")))
    for pool in pools:
        for preferred in ("xiaojingyu.pth", "default.pth"):
            for path in pool:
                if path.name == preferred:
                    return path
        if len(pool) == 1:
            return pool[0]
    for pool in pools:
        if pool:
            return max(pool, key=lambda p: p.stat().st_mtime)
    return None


def resolve_index_path(cfg: dict) -> Path | None:
    conf = cfg.get("convert", {})
    name = str(conf.get("model", "default"))
    models_dir = Path(cfg.get("project", {}).get("models_dir", "./models"))
    search = [models_dir / f"{name}.index", models_dir / name / f"{name}.index"]
    local = cfg.get("local") or {}
    rvc_dir = (local.get("rvc") or {}).get("dir")
    if rvc_dir:
        search.append(Path(rvc_dir) / "assets" / "indices" / f"{name}.index")
    for path in search:
        if path.exists():
            return path
    return None


# --------------------------------------------------------------------------- 外部命令

def _run_external(template: str, vocal: Path, out_path: Path, model_path: Path, cfg: dict) -> Path:
    conf = cfg.get("convert", {})
    index = resolve_index_path(cfg)
    mapping = {
        "{input}": str(vocal),
        "{output}": str(out_path),
        "{model}": str(model_path),
        "{index}": str(index) if index else "",
        "{pitch}": str(int(conf.get("pitch", 0) or 0)),
        "{protect}": str(float(conf.get("protect", 0.5))),
        "{index_rate}": str(float(conf.get("index_rate", 0.75))),
        "{f0_method}": str(conf.get("f0_method", "rmvpe")),
    }
    cmd = template
    for key, value in mapping.items():
        cmd = cmd.replace(key, value)

    log.step("音色转换（外部命令）")
    log.debug(cmd)
    proc = subprocess.run(
        shlex.split(cmd, posix=False), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError(f"外部转换命令失败（{proc.returncode}）：\n{proc.stderr[-2000:]}")
    if not out_path.exists():
        raise RuntimeError(f"外部命令跑完了，但没生成输出文件：{out_path}")
    log.done(f"转换完成：{out_path.name}")
    return out_path
