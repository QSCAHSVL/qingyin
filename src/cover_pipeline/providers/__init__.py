"""开放接口：音源（source）、发布（publish）、AI 增强（ai）。

主仓库只实现「本地文件」和「本地文件夹」，其余由用户自己在 plugins/ 下接。
配置里只留占位与密钥字段，不写死任何第三方平台。
"""

from __future__ import annotations

import importlib.util
import sys
from abc import ABC, abstractmethod
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .. import config as cfg_mod
from ..utils import log

# --------------------------------------------------------------------------- 发布

class PublishProvider(ABC):
    name = "base"

    @abstractmethod
    def send(self, audio: Path, meta: dict[str, Any], cfg: dict[str, Any]) -> str:
        """把成品发出去，返回一句人能看懂的结果。"""


_PUBLISH: dict[str, type[PublishProvider]] = {}


def register_publish(cls: type[PublishProvider]) -> type[PublishProvider]:
    if not getattr(cls, "name", None) or cls.name == "base":
        raise ValueError("发布插件必须有唯一的 name")
    _PUBLISH[cls.name] = cls
    return cls


def get_publish(name: str) -> PublishProvider:
    if name not in _PUBLISH:
        raise KeyError(f"没有这个发布方式：{name}（可用：{', '.join(sorted(_PUBLISH)) or '无'}）")
    return _PUBLISH[name]()


# --------------------------------------------------------------------------- AI 增强

class AIProvider(ABC):
    name = "base"

    def enhance(self, audio: Path, cfg: dict[str, Any]) -> Path:
        raise NotImplementedError

    def transcribe(self, audio: Path, cfg: dict[str, Any]) -> str:
        raise NotImplementedError

    def denoise(self, audio: Path, cfg: dict[str, Any]) -> Path:
        raise NotImplementedError


_AI: dict[str, type[AIProvider]] = {}


def register_ai(cls: type[AIProvider]) -> type[AIProvider]:
    if not getattr(cls, "name", None) or cls.name == "base":
        raise ValueError("AI 插件必须有唯一的 name")
    _AI[cls.name] = cls
    return cls


def get_ai(name: str) -> AIProvider:
    if name not in _AI:
        raise KeyError(f"没有这个 AI 增强：{name}（可用：{', '.join(sorted(_AI)) or '无'}）")
    return _AI[name]()


def available() -> dict[str, list[str]]:
    return {"publish": sorted(_PUBLISH), "ai": sorted(_AI), "decrypt": sorted(_DECRYPT)}


# --------------------------------------------------------------------------- 插件加载

def load_plugins(plugins_dir: Path | None = None) -> list[str]:
    """加载 plugins/providers/*.py，模块导入时自行 register。"""
    directory = (plugins_dir or (cfg_mod.ROOT / "plugins")) / "providers"
    if not directory.exists():
        return []
    loaded: list[str] = []
    for path in sorted(directory.glob("*.py")):
        if path.name.startswith("_"):
            continue
        module_name = f"cover_provider_{path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            if not spec or not spec.loader:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            loaded.append(path.name)
        except Exception as exc:
            log.warn(f"发布/AI 插件加载失败 {path.name}：{exc}")
    return loaded


def iter_names(kind: str) -> Iterable[str]:
    yield from (sorted(_PUBLISH) if kind == "publish" else sorted(_AI))


# --------------------------------------------------------------------------- 解密服务（可选插件）

class DecryptProvider(ABC):
    """用户自己接的高音质解密服务。

    本项目**不提供**任何解密实现，只留这个接口：想用高音质的人自己写一个，
    在 plugins/providers/decrypt_xxx.py 里注册，然后在 configs/local.yaml 里
    providers.decrypt 写插件名。
    """

    name = "base"

    @abstractmethod
    def fetch(self, track: dict[str, Any], dest_dir: Path) -> Path:
        """把这首歌的高音质音频弄到本地，返回文件路径。"""


_DECRYPT: dict[str, type[DecryptProvider]] = {}
_ACTIVE_DECRYPT: DecryptProvider | None = None


def register_decrypt(cls: type[DecryptProvider]) -> type[DecryptProvider]:
    if not getattr(cls, "name", None) or cls.name == "base":
        raise ValueError("解密插件必须有唯一的 name")
    _DECRYPT[cls.name] = cls
    return cls


def configure_decrypt(cfg: dict[str, Any]) -> None:
    """按配置挑一个解密插件；没配或没装就保持 None。"""
    global _ACTIVE_DECRYPT
    name = str(((cfg or {}).get("providers") or {}).get("decrypt") or "").strip()
    if not name:
        _ACTIVE_DECRYPT = None
        return
    cls = _DECRYPT.get(name)
    if cls is None:
        log.warn(f"配置里写了 providers.decrypt={name}，但没找到这个插件，高音质会不可用")
        _ACTIVE_DECRYPT = None
        return
    _ACTIVE_DECRYPT = cls()
    log.info(f"高音质解密插件已就绪：{name}")


def get_decrypt() -> DecryptProvider | None:
    return _ACTIVE_DECRYPT


def available_decrypt() -> list[str]:
    return sorted(_DECRYPT)


# 内置实现放在文件末尾导入，避免循环依赖
from . import local_folder  # noqa: F401
