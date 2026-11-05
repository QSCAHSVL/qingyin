"""音源适配层。

主仓库只内置 `local_file`（本地音频文件）。
其他来源（在线平台、自建下载工具、用户自己的解密工具等）**不在本仓库内**，
请放在项目根目录的 `plugins/` 下，通过这里的注册表按名字选用。

设计原则：
- 本项目只负责「拿到一个可读的音频文件」，不关心你怎么拿到的
- 插件由使用者自行提供与负责，仓库不附带、不推荐、不解释任何绕过版权保护的手段
"""

from __future__ import annotations

import importlib.util
import sys
from abc import ABC, abstractmethod
from collections.abc import Iterable
from pathlib import Path

from .. import config as cfg_mod
from ..utils import log

_REGISTRY: dict[str, type[SourceAdapter]] = {}


class SourceNotFound(RuntimeError):
    pass


class SourceAdapter(ABC):
    """音源适配器接口。实现 name 与 resolve 即可。"""

    name: str = "base"
    description: str = ""

    @abstractmethod
    def resolve(self, query: str, work_dir: Path, cfg: dict) -> Path:
        """把 query（歌名/链接/路径）解析成一个本地音频文件，返回绝对路径。"""

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"<SourceAdapter {self.name}>"


def register(adapter_cls: type[SourceAdapter]) -> type[SourceAdapter]:
    """注册适配器（插件里也用它）。"""
    if not getattr(adapter_cls, "name", None) or adapter_cls.name == "base":
        raise ValueError("适配器必须有唯一的 name 属性")
    _REGISTRY[adapter_cls.name] = adapter_cls
    return adapter_cls


def available() -> list[str]:
    return sorted(_REGISTRY)


def get(name: str) -> SourceAdapter:
    if name not in _REGISTRY:
        raise SourceNotFound(
            f"没有这个音源适配器：{name}。已注册：{', '.join(available()) or '无'}"
        )
    return _REGISTRY[name]()


def load_plugins(plugins_dir: Path | None = None) -> list[str]:
    """加载 plugins/*.py，每个模块导入时自行 register()。返回加载到的文件名。"""
    plugins_dir = plugins_dir or (cfg_mod.ROOT / "plugins")
    if not plugins_dir.exists():
        return []
    loaded: list[str] = []
    for path in sorted(plugins_dir.glob("*.py")):
        if path.name.startswith("_"):
            continue
        module_name = f"cover_pipeline_plugin_{path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            if not spec or not spec.loader:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            loaded.append(path.name)
        except Exception as exc:  # 插件坏了不该拖垮主流程
            log.warn(f"插件加载失败 {path.name}：{exc}")
    if loaded:
        log.debug(f"已加载插件：{', '.join(loaded)}")
    return loaded


def iter_adapters() -> Iterable[str]:
    yield from available()


# 内置适配器：放在文件末尾导入，避免循环依赖
from . import local_file  # noqa: F401  (导入即注册)
