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
    problems = validate(cfg)
    if problems:
        raise ConfigError("配置有问题：\n  - " + "\n  - ".join(problems))
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

class ConfigError(ValueError):
    """配置不合法时抛出，带字段路径，便于用户定位。"""


_TYPES = {
    "project": dict,
    "separate": dict,
    "convert": dict,
    "mix": dict,
    "clip": dict,
    "train": dict,
    "server": dict,
    "send": dict,
}


def validate(data: dict) -> list[str]:
    """最小 schema 校验：返回问题列表，空列表表示通过。"""
    problems: list[str] = []
    for key, expect in _TYPES.items():
        if key in data and not isinstance(data[key], expect):
            problems.append(f"{key} 应为对象，实际是 {type(data[key]).__name__}")
    for path, expect in (("server.port", int), ("clip.seconds", (int, float)),
                         ("separate.backend", str), ("convert.backend", str),
                         ("train.epochs", int)):
        node = data
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                node = None
                break
            node = node[part]
        if node is not None and not isinstance(node, expect):
            problems.append(f"{path} 类型不对：{type(node).__name__}")
    return problems
