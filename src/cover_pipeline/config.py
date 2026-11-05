"""配置加载：默认值 → 预设 → 本地覆盖 → 命令行覆盖。"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "configs"


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"配置文件格式不对，需要是映射：{path}")
    return data


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """递归合并，override 优先；列表整体替换。"""
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def load_config(preset: str | None = None, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """按 默认 → 预设 → local.yaml → overrides 的顺序合成配置。"""
    cfg = _read_yaml(CONFIG_DIR / "default.yaml")
    if preset:
        preset_path = CONFIG_DIR / "presets" / f"{preset}.yaml"
        if not preset_path.exists():
            raise FileNotFoundError(f"没有这个预设：{preset}（可用：{', '.join(available_presets())}）")
        cfg = deep_merge(cfg, _read_yaml(preset_path))
    cfg = deep_merge(cfg, _read_yaml(CONFIG_DIR / "local.yaml"))
    if overrides:
        cfg = deep_merge(cfg, overrides)
    return cfg


def available_presets() -> list[str]:
    preset_dir = CONFIG_DIR / "presets"
    if not preset_dir.exists():
        return []
    return sorted(p.stem for p in preset_dir.glob("*.yaml"))


def resolve_path(cfg: dict[str, Any], key: str) -> Path:
    """把 project.* 里的相对路径解析成绝对路径，并确保目录存在。"""
    project = cfg.setdefault("project", {})
    raw = project.get(key, f"./{key}")
    path = Path(raw)
    if not path.is_absolute():
        path = (ROOT / path).resolve()
    path.mkdir(parents=True, exist_ok=True)
    project[key] = str(path)
    return path
