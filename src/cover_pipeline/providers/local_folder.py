"""内置发布方式：拷到输出目录（或指定目录），顺便按模板改名。"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from ..utils import log
from . import PublishProvider, register_publish


@register_publish
class LocalFolderPublish(PublishProvider):
    name = "local_folder"

    def send(self, audio: Path, meta: dict[str, Any], cfg: dict[str, Any]) -> str:
        conf = (cfg.get("providers") or {}).get("publish_options") or {}
        target_dir = Path(conf.get("dir") or cfg.get("project", {}).get("output_dir") or "./output")
        target_dir.mkdir(parents=True, exist_ok=True)

        template = conf.get("filename") or "{name}{suffix}"
        name = meta.get("name") or audio.stem
        target = target_dir / template.format(name=name, suffix=audio.suffix, song=meta.get("song", name))
        shutil.copy2(audio, target)
        log.done(f"已放到输出目录：{target.name}")
        return str(target)
