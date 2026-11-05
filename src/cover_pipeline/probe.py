"""硬件与环境探测：只读，不改任何东西。

给 `cover plan` 提供决策依据，也给 `cover doctor` 复用。
"""

from __future__ import annotations

import ctypes
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from . import config as cfg_mod
from .utils import ffmpeg


def probe(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """返回一份完整的硬件/环境快照。"""
    cfg = cfg or {}
    root = Path(cfg.get("project", {}).get("root") or cfg_mod.ROOT)
    return {
        "os": _os_info(),
        "cpu": _cpu_info(),
        "memory": _memory_info(),
        "gpu": _gpu_info(),
        "disk": _disk_info(root),
        "python": {"version": platform.python_version(), "executable": sys.executable},
        "ffmpeg": _ffmpeg_info(),
        "deps": _deps_info(),
        "assets": _assets_info(cfg),
        "local": local_installs(cfg),
    }


def summary(probe_result: dict[str, Any]) -> str:
    """一行话概括机器水平，给界面和命令行用。"""
    gpu = probe_result.get("gpu") or []
    mem = probe_result.get("memory", {}).get("total_gb", 0)
    if not gpu:
        return f"无独显，内存 {mem:.0f}G —— 只能跑 CPU 推理，训练会非常慢"
    best = max(gpu, key=lambda g: g.get("vram_gb", 0))
    vram = best.get("vram_gb", 0)
    if vram >= 12:
        level = "可以训练 + 跑高质量方案"
    elif vram >= 8:
        level = "训练和推理都够用"
    elif vram >= 6:
        level = "能训练，但要降 batch"
    elif vram >= 4:
        level = "只能推理，不建议训练"
    else:
        level = "显存偏小，建议只做推理或换机器"
    return f"{best.get('name', 'GPU')}（{vram:.0f}G 显存）+ {mem:.0f}G 内存 —— {level}"


# --------------------------------------------------------------------------- 各部件

def _os_info() -> dict[str, Any]:
    return {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
    }


def _cpu_info() -> dict[str, Any]:
    return {
        "model": platform.processor() or "unknown",
        "cores": os.cpu_count() or 1,
    }


def _memory_info() -> dict[str, float]:
    if os.name == "nt":
        class _MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        stat = _MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
        try:
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            return {
                "total_gb": stat.ullTotalPhys / 1024**3,
                "available_gb": stat.ullAvailPhys / 1024**3,
            }
        except Exception:
            return {"total_gb": 0.0, "available_gb": 0.0}

    try:  # Linux / macOS 兜底
        with open("/proc/meminfo", "r", encoding="utf-8") as fh:
            data = {line.split(":")[0]: line.split()[1] for line in fh if ":" in line}
        total = int(data.get("MemTotal", 0)) / 1024**2
        avail = int(data.get("MemAvailable", 0)) / 1024**2
        return {"total_gb": total, "available_gb": avail}
    except Exception:
        return {"total_gb": 0.0, "available_gb": 0.0}


def _gpu_info() -> list[dict[str, Any]]:
    if not shutil.which("nvidia-smi"):
        return []
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        if out.returncode != 0:
            return []
        gpus = []
        for line in out.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 2:
                continue
            try:
                vram = float(parts[1]) / 1024
            except ValueError:
                continue
            gpus.append(
                {
                    "name": parts[0],
                    "vram_gb": round(vram, 1),
                    "driver": parts[2] if len(parts) > 2 else "",
                }
            )
        return gpus
    except Exception:
        return []


def _disk_info(root: Path) -> dict[str, Any]:
    try:
        anchor = root.drive or str(root)
        usage = shutil.disk_usage(anchor if root.drive else root)
        return {
            "drive": anchor,
            "total_gb": round(usage.total / 1024**3, 1),
            "free_gb": round(usage.free / 1024**3, 1),
        }
    except Exception:
        return {"drive": "", "total_gb": 0.0, "free_gb": 0.0}


def _ffmpeg_info() -> dict[str, Any]:
    try:
        exe = ffmpeg._which("ffmpeg")
    except Exception:
        return {"available": False, "version": ""}
    try:
        out = subprocess.run(
            [exe, "-version"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15
        )
        first = (out.stdout or "").splitlines()[0] if out.stdout else ""
        return {"available": True, "version": first.strip()}
    except Exception:
        return {"available": True, "version": ""}


def _deps_info() -> dict[str, Any]:
    def has(module: str) -> bool:
        try:
            return importlib.util.find_spec(module) is not None
        except (ImportError, ValueError):
            return False

    torch_version = ""
    if has("torch"):
        try:
            import torch  # type: ignore

            torch_version = getattr(torch, "__version__", "")
        except Exception:
            torch_version = "unknown"

    return {
        "torch": torch_version,
        "cuda": has("torch") and _torch_cuda_available(),
        "audio_separator": has("audio_separator"),
        "rvc_python": has("rvc_python"),
        "librosa": has("librosa"),
    }


def _torch_cuda_available() -> bool:
    try:
        import torch  # type: ignore

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _assets_info(cfg: dict[str, Any]) -> dict[str, Any]:
    project = cfg.get("project", {})
    models_dir = Path(project.get("models_dir") or (cfg_mod.ROOT / "models"))
    work_dir = Path(project.get("work_dir") or (cfg_mod.ROOT / "work"))
    output_dir = Path(project.get("output_dir") or (cfg_mod.ROOT / "output"))

    models = sorted(p.name for p in models_dir.glob("*.pth")) if models_dir.exists() else []
    songs = [p for p in work_dir.glob("*") if p.is_dir() and not p.name.startswith("_")] if work_dir.exists() else []
    outputs = list(output_dir.rglob("*.wav")) if output_dir.exists() else []

    return {
        "models": models,
        "model_count": len(models),
        "songs": len(songs),
        "outputs": len(outputs),
    }


def to_json(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------- 本地已部署检测

RVC_DIR_CANDIDATES = (
    "E:/AI-Companion/tools/RVC",
    "D:/AI-Companion/tools/RVC",
    "~/RVC",
    "./RVC",
    "./tools/RVC",
)

UVR_SCRIPT_CANDIDATES = (
    "E:/AI-Companion/tools/cover-automation/uvr_sep.py",
    "D:/AI-Companion/tools/cover-automation/uvr_sep.py",
    "./uvr_sep.py",
    "./scripts/uvr_sep.py",
)

UVR_PYTHON_CANDIDATES = (
    "E:/AI-Companion/tools/GPT-SoVITS/.venv/Scripts/python.exe",
    "D:/AI-Companion/tools/GPT-SoVITS/.venv/Scripts/python.exe",
)


def local_installs(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """检测本机是否已经装好 RVC / UVR，能直接复用。

    顺序：配置文件里写的 > 常见默认位置 > 自动推断。
    """
    tools = (cfg or {}).get("tools", {}) or {}

    rvc_dir = _first_dir(tools.get("rvc_dir"), *RVC_DIR_CANDIDATES)
    rvc_python = _first_file(tools.get("rvc_python"))
    if not rvc_python and rvc_dir:
        rvc_python = _first_file(
            Path(rvc_dir) / ".venv" / "Scripts" / "python.exe",
            Path(rvc_dir) / "venv" / "Scripts" / "python.exe",
            Path(rvc_dir) / ".venv" / "bin" / "python",
        )
    rvc_ok = bool(rvc_dir and (Path(rvc_dir) / "infer" / "cli.py").exists() and rvc_python)

    uvr_script = _first_file(tools.get("uvr_script"), *UVR_SCRIPT_CANDIDATES)
    uvr_python = _first_file(tools.get("uvr_python"), *UVR_PYTHON_CANDIDATES)
    if not uvr_python and uvr_script:
        uvr_python = _infer_uvr_python(Path(uvr_script))
    uvr_ok = bool(uvr_script and uvr_python)

    weights = []
    if rvc_dir:
        weight_dir = Path(rvc_dir) / "assets" / "weights"
        if weight_dir.exists():
            weights = sorted(p.name for p in weight_dir.glob("*.pth"))

    return {
        "rvc": {
            "ok": rvc_ok,
            "dir": str(rvc_dir) if rvc_dir else "",
            "python": str(rvc_python) if rvc_python else "",
            "weights": weights,
        },
        "uvr": {
            "ok": uvr_ok,
            "script": str(uvr_script) if uvr_script else "",
            "python": str(uvr_python) if uvr_python else "",
            "model": str(tools.get("uvr_model") or "becruily"),
        },
    }


def _first_file(*candidates: Any) -> Path | None:
    for item in candidates:
        if not item:
            continue
        path = Path(str(item)).expanduser()
        if path.is_file():
            return path
    return None


def _first_dir(*candidates: Any) -> Path | None:
    for item in candidates:
        if not item:
            continue
        path = Path(str(item)).expanduser()
        if path.is_dir():
            return path
    return None


def _infer_uvr_python(script: Path) -> Path | None:
    """从 uvr_sep.py 的位置往上找 GPT-SoVITS 的 venv。"""
    for parent in list(script.parents)[:4]:
        candidate = parent / "GPT-SoVITS" / ".venv" / "Scripts" / "python.exe"
        if candidate.is_file():
            return candidate
    return None
