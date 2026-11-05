"""一键配置：探测环境 → 推荐组合 → 用户确认 → 自动装依赖、下模型、写配置。

原则：
- 每一步都先说清楚「要做什么、多大」，用户确认后才动手
- pip 安装走当前解释器（`sys.executable -m pip`），不改系统环境
- 下载支持断点续传，默认走 hf-mirror（国内可达），可配置换源
- 任何一步失败都停下并说清原因，不会「装作成功」
"""

from __future__ import annotations

import importlib.util
import sys
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..utils import log, proc

PIP_INDEX_CUDA = "https://download.pytorch.org/whl/cu121"
PIP_INDEX_CPU = "https://download.pytorch.org/whl/cpu"

# 权重文件：镜像优先，官方兜底
WEIGHTS = {
    "hubert_base.pt": {
        "path": ["assets/hubert_base.pt", "assets/hubert/hubert_base.pt", "assets/weights/hubert_base.pt"],
        "mirror": "https://hf-mirror.com/lj1995/VoiceConversionWebUI/resolve/main/hubert_base.pt",
        "official": "https://huggingface.co/lj1995/VoiceConversionWebUI/resolve/main/hubert_base.pt",
        "size_mb": 181,
    },
    "rmvpe.pt": {
        "path": ["assets/rmvpe/rmvpe.pt", "assets/rmvpe.pt", "assets/weights/rmvpe.pt"],
        "mirror": "https://hf-mirror.com/lj1995/VoiceConversionWebUI/resolve/main/rmvpe.pt",
        "official": "https://huggingface.co/lj1995/VoiceConversionWebUI/resolve/main/rmvpe.pt",
        "size_mb": 173,
    },
    "f0G40k.pth": {
        "path": ["assets/pretrained_v2/f0G40k.pth"],
        "mirror": "https://hf-mirror.com/lj1995/VoiceConversionWebUI/resolve/main/pretrained_v2/f0G40k.pth",
        "official": "https://huggingface.co/lj1995/VoiceConversionWebUI/resolve/main/pretrained_v2/f0G40k.pth",
        "size_mb": 75,
    },
    "f0D40k.pth": {
        "path": ["assets/pretrained_v2/f0D40k.pth"],
        "mirror": "https://hf-mirror.com/lj1995/VoiceConversionWebUI/resolve/main/pretrained_v2/f0D40k.pth",
        "official": "https://huggingface.co/lj1995/VoiceConversionWebUI/resolve/main/pretrained_v2/f0D40k.pth",
        "size_mb": 75,
    },
}


@dataclass
class Step:
    id: str
    label: str
    kind: str                     # pip / download / config / verify
    commands: list[str] = field(default_factory=list)
    size_mb: int = 0
    note: str = ""
    target: str = ""
    url: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def plan_setup(
    probe: dict[str, Any],
    profile,
    cfg: dict[str, Any],
    plan: dict[str, Any] | None = None,
    separation: str = "auto",
) -> dict[str, Any]:
    """生成配置步骤清单（不执行）。

    separation：auto（按环境推荐）/ uvr（audio-separator）/ demucs / both / none
    """
    local = probe.get("local") or {}
    rvc = local.get("rvc") or {}
    uvr = local.get("uvr") or {}
    has_local_rvc = bool(rvc.get("ok"))
    has_local_uvr = bool(uvr.get("ok"))
    gpus = probe.get("gpu") or []
    vram = max((float(g.get("vram_gb", 0) or 0) for g in gpus), default=0.0)
    disk_free = float((probe.get("disk") or {}).get("free_gb", 0) or 0)
    wants_train = str(getattr(profile, "will_train", "unsure"))

    steps: list[Step] = []

    # 0) 分离后端：本地已有 UVR 就复用；否则按硬件和磁盘给出选择
    choice = (separation or "auto").lower()
    if choice == "auto":
        if has_local_uvr:
            choice = "uvr"
        elif disk_free and disk_free < 6:
            choice = "demucs"      # 空间紧张：demucs 只要 300MB
        elif vram and vram < 5:
            choice = "demucs"      # 显存紧张：demucs 峰值 2.5G
        else:
            choice = "uvr"         # 其余情况 UVR 质量更高
    if choice not in ("uvr", "demucs", "both", "none"):
        choice = "uvr"

    # 1) Python 依赖
    if not has_local_rvc and not _has_module("torch"):
        if vram > 0:
            steps.append(Step("pip_torch", "安装 PyTorch（CUDA 版）", "pip",
                              [sys.executable, "-m", "pip", "install", "torch", "torchaudio", "--index-url", PIP_INDEX_CUDA],
                              size_mb=2600, note="有显卡，装 CUDA 版"))
        else:
            steps.append(Step("pip_torch", "安装 PyTorch（CPU 版）", "pip",
                              [sys.executable, "-m", "pip", "install", "torch", "torchaudio", "--index-url", PIP_INDEX_CPU],
                              size_mb=220, note="没有显卡，装 CPU 版"))
    need_uvr = choice in ("uvr", "both") and not has_local_uvr
    need_demucs = choice in ("demucs", "both") and not _has_module("demucs")
    if need_uvr and not _has_module("audio_separator"):
        tag = "audio-separator[gpu]" if vram > 0 else "audio-separator[cpu]"
        steps.append(Step("pip_separator", "安装人声分离运行时（UVR）", "pip",
                          [sys.executable, "-m", "pip", "install", tag], size_mb=60,
                          note="质量优先，显存峰值约 3.5G"))
    if need_demucs:
        steps.append(Step("pip_demucs", "安装 Demucs（另一种分离）", "pip",
                          [sys.executable, "-m", "pip", "install", "demucs"], size_mb=300,
                          note="比 UVR 慢，人声残留少；显存峰值约 2.5G"))
    if not has_local_rvc and not _has_module("rvc_python"):
        steps.append(Step("pip_rvc", "安装音色转换运行时", "pip",
                          [sys.executable, "-m", "pip", "install", "rvc-python"], size_mb=40,
                          note="不想装的话也可以接本机已有的 RVC"))

    # 2) 权重文件
    weights_dir = _weights_root(cfg, rvc.get("dir"))
    needed = ["hubert_base.pt", "rmvpe.pt"]
    if wants_train == "yes" or wants_train == "unsure":
        needed += ["f0G40k.pth", "f0D40k.pth"]
    if choice in ("demucs", "none") and not need_uvr:
        needed = [n for n in needed if not n.startswith(("uvr_",))]
    if has_local_rvc and not rvc.get("dir"):
        # 有本机 RVC 但没给路径：相信它自带权重，不重复下
        needed = []
    mirror = str(((cfg.get("download") or {}).get("mirror")) or "https://hf-mirror.com")
    for name in needed:
        info = WEIGHTS[name]
        if _weight_exists(weights_dir, info):
            continue
        target = Path(weights_dir) / info["path"][0]
        steps.append(Step(f"download_{name}", f"下载 {name}", "download",
                          size_mb=int(info["size_mb"]),
                          target=str(target),
                          url=str(info["mirror"]).replace("https://hf-mirror.com", mirror.rstrip("/")),
                          note="备用源：" + str(info["official"])))

    # 3) 写配置
    steps.append(Step("config", "写入配置（模型路径 + 方案参数）", "config", size_mb=0,
                      note="只改方案管的几段和 tools 路径，其它配置保留"))

    # 4) 收尾自检
    steps.append(Step("verify", "装完自检", "verify", size_mb=0))

    total = sum(s.size_mb for s in steps)
    warning = ""
    if disk_free and total / 1024 > disk_free * 0.85:
        warning = f"这套要 {total / 1024:.1f}G，你只剩 {disk_free:.0f}G，可能装不下"

    return {
        "steps": [s.as_dict() for s in steps],
        "total_mb": total,
        "warning": warning,
        "has_local_rvc": has_local_rvc,
        "has_local_uvr": has_local_uvr,
        "vram_gb": vram,
        "plan_id": (plan or {}).get("id", ""),
        "separation": choice,
        "profile": {
            "prefer": getattr(profile, "prefer", ""),
            "will_train": wants_train,
            "max_vram_gb": getattr(profile, "max_vram_gb", None),
        },
    }


def execute(
    setup: dict[str, Any],
    cfg: dict[str, Any],
    *,
    on_progress: Callable[[float, str], None] | None = None,
    cancel_event=None,
    plan: dict[str, Any] | None = None,
    snapshots: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """执行步骤清单。"""
    steps = setup.get("steps") or []
    done: list[dict[str, Any]] = []
    total = max(1, len(steps))
    for index, raw in enumerate(steps):
        step = Step(**{k: v for k, v in raw.items() if k in Step.__dataclass_fields__})
        if cancel_event is not None and cancel_event.is_set():
            raise proc.Cancelled("已取消")
        if on_progress:
            on_progress(index / total, f"{step.label}…")
        log.step(step.label)

        if step.kind == "pip":
            _run_pip(step, cancel_event)
        elif step.kind == "download":
            _download(step, cfg, cancel_event, on_progress=on_progress)
        elif step.kind == "config":
            _write_config(cfg, plan, snapshots or {})
        elif step.kind == "verify":
            _verify(cfg, snapshots or {})

        done.append({"id": step.id, "label": step.label, "ok": True})
        if on_progress:
            on_progress((index + 1) / total, f"{step.label} 完成")

    return {"steps": done, "total": len(steps)}


# --------------------------------------------------------------------------- 各步骤实现

def _run_pip(step: Step, cancel_event) -> None:
    try:
        proc.run(step.commands, cancel_event=cancel_event, timeout=1800)
    except Exception as exc:
        raise RuntimeError(f"{step.label} 失败：{exc}") from exc


def _download(step: Step, cfg: dict[str, Any], cancel_event, on_progress=None) -> None:
    dest = Path(step.target)
    dest.parent.mkdir(parents=True, exist_ok=True)
    urls = [step.url, step.note] if step.note else [step.url]
    last_error: Exception | None = None
    for url in urls:
        if not url:
            continue
        try:
            _download_file(url, dest, cancel_event, on_progress=on_progress, label=step.label)
            return
        except Exception as exc:
            last_error = exc
            log.warn(f"{url} 下载失败：{exc}，换下一个源")
    raise RuntimeError(f"{step.label} 下载失败：{last_error}（建议手动下载放到 {dest}）")


def _download_file(url: str, dest: Path, cancel_event, on_progress=None, label: str = "") -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    have = tmp.stat().st_size if tmp.exists() else 0
    headers = {"User-Agent": "cover-pipeline/0.2"}
    if have:
        headers["Range"] = f"bytes={have}-"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        total = int(resp.headers.get("Content-Length") or 0) + have
        mode = "ab" if have and resp.status == 206 else "wb"
        if mode == "wb":
            have = 0
        with tmp.open(mode) as fh:
            read = 0
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    raise proc.Cancelled("已取消")
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                fh.write(chunk)
                read += len(chunk)
                if on_progress and total:
                    on_progress((have + read) / total, f"{label} {int((have + read) / 1024 / 1024)}MB / {int(total / 1024 / 1024)}MB")
    size = tmp.stat().st_size if tmp.exists() else 0
    if size < 1024 * 1024:
        tmp.unlink(missing_ok=True)
        raise RuntimeError("下载到的文件太小，可能被拦截了")
    tmp.replace(dest)
    log.done(f"已保存：{dest}")


def _write_config(cfg: dict[str, Any], plan: dict[str, Any] | None, snapshots: dict[str, Any]) -> None:
    from ..plan.writer import apply_plan, apply_tools, patch_local

    local = (snapshots or {}).get("local") or {}
    if local:
        apply_tools(local)
    if plan:
        apply_plan(plan)
    # 分离后端以用户选择为准（demucs 不是方案里的字段）
    choice = str((snapshots or {}).get("separation") or "").lower()
    if choice in ("demucs", "uvr", "local_uvr", "none"):
        backend = "demucs" if choice == "demucs" else ("none" if choice == "none" else choice)
        patch_local({"separate": {"backend": backend}})


def _verify(cfg: dict[str, Any], snapshots: dict[str, Any]) -> None:
    from .. import probe

    snapshot = probe.probe(cfg)
    missing = []
    if not snapshot["ffmpeg"]["available"]:
        missing.append("ffmpeg")
    local = snapshot.get("local") or {}
    if not (local.get("rvc") or {}).get("ok") and not _has_module("rvc_python"):
        missing.append("RVC")
    if not (local.get("uvr") or {}).get("ok") and not _has_module("audio_separator"):
        missing.append("人声分离")
    if missing:
        raise RuntimeError("还缺：" + "、".join(missing) + "；按提示补上再跑 cover doctor")


# --------------------------------------------------------------------------- 工具

def _weights_root(cfg: dict[str, Any], rvc_dir: str | None) -> Path:
    """权重放哪：有本机 RVC 就放它的 assets，否则放项目 models/assets。"""
    if rvc_dir:
        return Path(rvc_dir)
    configured = (cfg.get("download") or {}).get("assets_dir")
    if configured:
        return Path(configured).expanduser()
    return Path(cfg["project"]["models_dir"])


def _weight_exists(root: Path, info: dict[str, Any]) -> bool:
    for rel in info["path"]:
        candidate = Path(root) / rel
        if candidate.exists() and candidate.stat().st_size > 1024 * 1024:
            return True
    return False


def render(setup: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    total = setup.get("total_mb", 0) / 1024
    lines.append(f"预计占用 {total:.1f}G，共 {len(setup.get('steps') or [])} 步")
    if setup.get("has_local_rvc") and setup.get("has_local_uvr"):
        lines.append("检测到本机已有 RVC + UVR，会优先复用")
    for step in setup.get("steps") or []:
        size = f"  {step['size_mb']}MB" if step.get("size_mb") else ""
        lines.append(f"  · {step['label']}{size}")
        if step.get("kind") == "pip" and step.get("commands"):
            lines.append("      " + " ".join(step["commands"][2:]))
        if step.get("kind") == "download":
            lines.append(f"      → {step.get('target')}")
        if step.get("note"):
            lines.append(f"      {step['note']}")
    if setup.get("warning"):
        lines.append(f"  ! {setup['warning']}")
    return lines


def apply_all(cfg: dict[str, Any], *, prefer: str = "stability", will_train: str = "unsure",
              max_vram: float | None = None, separation: str = "auto",
              yes: bool = False, dry_run: bool = False) -> int:
    """CLI 入口：探测 → 推荐 → 确认 → 执行。"""
    from .. import probe
    from ..plan import Profile, recommend, recommend_assets
    from ..utils import log as lg

    snapshot = probe.probe(cfg)
    profile = Profile(prefer=prefer, will_train=will_train, max_vram_gb=max_vram)
    plans = recommend(snapshot, profile)
    available = [p for p in plans if not p.excluded_reason]
    best = available[0] if available else None
    if best is None:
        lg.error("没有匹配的方案，先跑 cover plan 看看")
        return 1

    lg.step(f"推荐方案：{best.name}")
    assets = recommend_assets(snapshot, profile, best.plan)
    for line in (assets.get("note") and [assets["note"]] or []):
        lg.info(line)

    setup = plan_setup(snapshot, profile, cfg, best.plan, separation=separation)
    lg.step("将要执行的步骤")
    for line in render(setup):
        lg.info(line)

    if dry_run:
        lg.info("这是预演（--dry-run），什么都没做")
        return 0

    if not yes:
        try:
            answer = input("确认按上面执行？[y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = ""
        if answer not in ("y", "yes", "是"):
            lg.warn("已取消，什么都没改")
            return 1

    result = execute(
        setup, cfg,
        on_progress=lambda value, message: lg.info(message),
        plan=best.plan,
        snapshots={"local": snapshot.get("local"), "separation": setup.get("separation")},
    )
    lg.done(f"配置完成（{result['total']} 步）")
    lg.info("下一步：cover sing --song \"歌名\"")
    return 0
