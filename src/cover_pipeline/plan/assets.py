"""模型与环境推荐：新用户什么都没有时，告诉他需要下什么、多大、放哪。

和方案引擎的分工：
- 方案引擎决定「参数」（分块、index_rate、训练轮数…）
- 这里决定「文件」：要不要装 torch、哪个分离模型、RVC 必需的特征模型

判断依据：有没有显卡、显存够不够、要不要训练、磁盘剩多少、用不用本机已有环境。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .. import config as cfg_mod
from ..utils import log

MANIFEST = cfg_mod.ROOT / "assets" / "manifest.yaml"


def load_manifest(path: Path | None = None) -> dict[str, Any]:
    directory = path or MANIFEST
    if not directory.exists():
        return {"runtimes": [], "models": [], "bundles": []}
    with directory.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {"runtimes": [], "models": [], "bundles": []}


def recommend(probe: dict[str, Any], profile, plan: dict[str, Any] | None = None) -> dict[str, Any]:
    """返回需要准备的文件清单。"""
    manifest = load_manifest()
    runtimes = {item["id"]: item for item in manifest.get("runtimes") or []}
    models = {item["id"]: item for item in manifest.get("models") or []}
    bundles = {item["id"]: item for item in manifest.get("bundles") or []}

    local = (probe.get("local") or {})
    has_local_rvc = bool((local.get("rvc") or {}).get("ok"))
    has_local_uvr = bool((local.get("uvr") or {}).get("ok"))
    gpus = probe.get("gpu") or []
    vram = max((float(g.get("vram_gb", 0) or 0) for g in gpus), default=0.0)
    disk_free = float((probe.get("disk") or {}).get("free_gb", 0) or 0)
    wants_train = str(getattr(profile, "will_train", "unsure"))

    # 1) 已经有本机环境：直接用，不下载
    if has_local_rvc and has_local_uvr:
        return {
            "bundle": bundles.get("reuse_local", {"id": "reuse_local", "label": "复用本机已装环境"}),
            "items": [],
            "total_mb": 0,
            "note": "已经检测到本机 RVC 和 UVR，不需要下载任何模型；跑 cover link --auto 把它们记下来就行。",
        }

    # 2) 选场景包
    if vram <= 0:
        bundle = bundles.get("cpu_only")
    elif wants_train == "no":
        bundle = bundles.get("minimal_gpu")
    elif vram and vram < 6:
        bundle = bundles.get("low_vram")
    else:
        bundle = bundles.get("minimal_gpu_train")

    # 3) 按方案微调：方案里用轻量分离就换成 hp2
    include_ids = list((bundle or {}).get("includes") or [])
    plan_sep = str(((plan or {}).get("params") or {}).get("separate", {}).get("local_model") or "")
    if plan_sep == "hp2":
        include_ids = ["uvr_hp2" if item == "uvr_becruily" else item for item in include_ids]
    # 已经有本机 RVC：不装 rvc_python / hubert / rmvpe（本机自带）
    if has_local_rvc:
        include_ids = [item for item in include_ids if item not in ("rvc_python", "hubert_base", "rmvpe")]
    if has_local_uvr:
        include_ids = [item for item in include_ids if item not in ("audio_separator", "uvr_becruily", "uvr_hp2")]

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item_id in include_ids:
        if item_id in seen:
            continue
        seen.add(item_id)
        source = runtimes.get(item_id) or models.get(item_id)
        if source:
            items.append(dict(source))

    total_mb = sum(int(item.get("size_mb", 0) or 0) for item in items)
    warning = ""
    if disk_free and total_mb / 1024 > disk_free * 0.8:
        warning = f"这些文件要 {total_mb / 1024:.1f}G，你只剩 {disk_free:.0f}G，建议先清点空间或换盘"

    return {
        "bundle": bundle or {"id": "custom", "label": "自定义"},
        "items": items,
        "total_mb": total_mb,
        "vram_peak_gb": _peak(items),
        "note": (bundle or {}).get("note", ""),
        "warning": warning,
        "needs_pip": [item["id"] for item in items if item.get("source", "").startswith("pip install")],
    }


def render(result: dict[str, Any]) -> list[str]:
    """给命令行/日志用的几行文字。"""
    lines: list[str] = []
    bundle = result.get("bundle") or {}
    lines.append(f"建议组合：{bundle.get('label', '自定义')}（约 {result.get('total_mb', 0) / 1024:.1f}G）")
    if result.get("note"):
        lines.append(f"  {result['note']}")
    for item in result.get("items") or []:
        lines.append(f"  · {item['label']}  {item.get('size_mb', 0)}MB")
        if item.get("source"):
            lines.append(f"      {item['source']}")
        if item.get("note"):
            lines.append(f"      {item['note']}")
    if result.get("warning"):
        lines.append(f"  ! {result['warning']}")
    if result.get("needs_pip"):
        lines.append(f"  pip 需要装：{', '.join(result['needs_pip'])}")
    return lines


def print_summary(result: dict[str, Any]) -> None:
    for line in render(result):
        if line.startswith("  !"):
            log.warn(line.strip())
        elif line.startswith("建议"):
            log.info(line)
        elif line.startswith("  ·") or line.startswith("  "):
            log.info(line)
        else:
            log.info(line)


def _peak(items: list[dict[str, Any]]) -> float:
    """显存峰值：取各项的最大值（它们不会同时满载）。"""
    return max((float(item.get("vram_gb", 0) or 0) for item in items), default=0.0)
