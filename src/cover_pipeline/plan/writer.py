"""把选中的方案写进 configs/local.yaml。

原则：
- 只覆盖方案负责的段（separate / convert / train / clip / mix）
- 保留用户已有的其它配置（tools、source、device、providers……）
- 写之前留一份备份，方便回滚
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from .. import config as cfg_mod

MANAGED_KEYS = ("separate", "convert", "train", "clip", "mix")

HEADER = """# 本文件由 `cover plan` 维护（方案参数部分）。
# 你手动改过的其它段（tools / source / device / providers）会保留。
# 想换方案：再跑一次 `cover plan --apply <方案id>`。
"""


def local_config_path() -> Path:
    return cfg_mod.CONFIG_DIR / "local.yaml"


def apply_plan(plan: dict[str, Any], *, backup: bool = True) -> Path:
    path = local_config_path()
    existing: dict[str, Any] = {}
    if path.exists():
        with path.open("r", encoding="utf-8") as fh:
            existing = yaml.safe_load(fh) or {}
        if not isinstance(existing, dict):
            existing = {}
        if backup:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            shutil.copy2(path, path.with_name(f"local.yaml.bak-{stamp}"))

    params = plan.get("params", {})
    for key in MANAGED_KEYS:
        if key in params:
            existing[key] = _merge(existing.get(key, {}), params[key])

    existing["plan"] = {
        "id": plan.get("id"),
        "name": plan.get("name"),
        "applied_at": datetime.now().isoformat(timespec="seconds"),
    }

    text = HEADER + "\n" + yaml.safe_dump(
        existing, allow_unicode=True, sort_keys=False, default_flow_style=False, width=100
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _merge(base: Any, override: Any) -> Any:
    if isinstance(base, dict) and isinstance(override, dict):
        out = dict(base)
        for key, value in override.items():
            out[key] = _merge(out.get(key), value)
        return out
    return override


def current_plan() -> dict[str, Any] | None:
    path = local_config_path()
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except Exception:
        return None
    plan = data.get("plan") if isinstance(data, dict) else None
    return plan if isinstance(plan, dict) else None


def clear_plan() -> Path:
    """把方案管的几段恢复成默认值，并删掉 plan 记录。"""
    path = local_config_path()
    existing: dict[str, Any] = {}
    if path.exists():
        with path.open("r", encoding="utf-8") as fh:
            existing = yaml.safe_load(fh) or {}
        if not isinstance(existing, dict):
            existing = {}
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(path, path.with_name(f"local.yaml.bak-{stamp}"))

    defaults_path = cfg_mod.CONFIG_DIR / "default.yaml"
    defaults: dict[str, Any] = {}
    if defaults_path.exists():
        with defaults_path.open("r", encoding="utf-8") as fh:
            defaults = yaml.safe_load(fh) or {}

    for key in MANAGED_KEYS:
        if key in defaults:
            existing[key] = defaults[key]
    existing.pop("plan", None)

    text = HEADER + "\n" + yaml.safe_dump(
        existing, allow_unicode=True, sort_keys=False, default_flow_style=False, width=100
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def apply_tools(local_installs: dict[str, Any], *, backup: bool = False) -> Path:
    """把探测到的本地 RVC / UVR 路径写进 configs/local.yaml 的 tools 段。"""
    path = local_config_path()
    existing: dict[str, Any] = {}
    if path.exists():
        with path.open("r", encoding="utf-8") as fh:
            existing = yaml.safe_load(fh) or {}
        if not isinstance(existing, dict):
            existing = {}
        if backup:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            shutil.copy2(path, path.with_name(f"local.yaml.bak-{stamp}"))

    tools = existing.get("tools") or {}
    rvc = local_installs.get("rvc", {})
    uvr = local_installs.get("uvr", {})
    if rvc.get("dir"):
        tools["rvc_dir"] = rvc["dir"]
    if rvc.get("python"):
        tools["rvc_python"] = rvc["python"]
    if uvr.get("script"):
        tools["uvr_script"] = uvr["script"]
    if uvr.get("python"):
        tools["uvr_python"] = uvr["python"]
    if uvr.get("model"):
        tools["uvr_model"] = uvr["model"]
    existing["tools"] = tools

    text = HEADER + "\n" + yaml.safe_dump(
        existing, allow_unicode=True, sort_keys=False, default_flow_style=False, width=100
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def patch_local(updates: dict[str, Any], *, backup: bool = True) -> Path:
    """只改指定的几段（深合并），其它保持不动。"""
    import time as _time

    path = local_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {}
    if path.exists():
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if backup:
            stamp = _time.strftime("%Y%m%d-%H%M%S")
            path.with_name(f"{path.name}.bak-{stamp}").write_text(
                path.read_text(encoding="utf-8"), encoding="utf-8"
            )
    for key, value in updates.items():
        data[key] = _merge(data.get(key) or {}, value) if isinstance(value, dict) else value
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=1000), encoding="utf-8")
    return path


def set_project_paths(paths: dict[str, str], *, backup: bool = True) -> Path:
    """改 work_dir / output_dir / models_dir 到 local.yaml 的 project 段。

    只接受这三项；空值会被忽略（保持原样）。
    """
    import time as _time

    allowed = {"work_dir", "output_dir", "models_dir"}
    updates = {k: str(v) for k, v in paths.items() if k in allowed and str(v or "").strip()}
    if not updates:
        raise ValueError("没有可写的路径")

    path = local_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if path.exists():
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if backup:
            stamp = _time.strftime("%Y%m%d-%H%M%S")
            path.with_name(f"{path.name}.bak-{stamp}").write_text(
                path.read_text(encoding="utf-8"), encoding="utf-8"
            )
    project = data.get("project") or {}
    project.update(updates)
    data["project"] = project
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=1000), encoding="utf-8")
    return path
