"""内置音源：本地音频文件 / 目录模糊匹配。

支持三种 query：
1. 直接给文件路径：`--input D:\\music\\song.flac`
2. 给歌名：在 `source.search_dirs` 里按文件名模糊匹配
3. 给歌名 + `--input` 目录：在该目录里找

只处理已经可以正常读取的音频文件；不解析、不解密任何加密格式。
"""

from __future__ import annotations

import re
from pathlib import Path

from ..utils import log
from . import SourceAdapter, SourceNotFound, register

AUDIO_SUFFIXES = {".wav", ".flac", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".aiff", ".aif"}


def _normalize(text: str) -> str:
    """去掉空格、标点、大小写差异，方便模糊匹配。"""
    return re.sub(r"[\s\-_·.,，。、()（）\[\]【】]+", "", text).lower()


@register
class LocalFileSource(SourceAdapter):
    name = "local_file"
    description = "本地音频文件（路径或目录内模糊匹配）"

    def resolve(self, query: str, work_dir: Path, cfg: dict) -> Path:
        raw = Path(query).expanduser()
        if raw.is_file():
            if raw.suffix.lower() not in AUDIO_SUFFIXES:
                raise SourceNotFound(f"不是支持的音频格式：{raw.suffix}")
            log.info(f"使用本地文件：{raw}")
            return raw.resolve()

        search_dirs = [Path(p).expanduser() for p in (cfg.get("source", {}).get("search_dirs") or [])]
        if raw.is_dir():
            search_dirs.insert(0, raw)

        if not search_dirs:
            raise SourceNotFound(
                "给的是歌名，但没配置搜索目录。请在 configs/local.yaml 里设置 source.search_dirs，"
                "或者直接用 --input 指定文件。"
            )

        key = _normalize(query)
        best: tuple[float, Path] | None = None
        for directory in search_dirs:
            if not directory.exists():
                continue
            for path in directory.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in AUDIO_SUFFIXES:
                    continue
                score = _score(key, _normalize(path.stem))
                if score <= 0:
                    continue
                if best is None or score > best[0]:
                    best = (score, path)

        if best is None:
            raise SourceNotFound(f"本地没找到匹配「{query}」的音频文件")
        log.info(f"本地匹配：{best[1].name}（相似度 {best[0]:.2f}）")
        return best[1].resolve()


def _score(query: str, candidate: str) -> float:
    """简单的包含/前缀打分，够用且不引入依赖。"""
    if not query or not candidate:
        return 0.0
    if query == candidate:
        return 1.0
    if candidate.startswith(query) or query.startswith(candidate):
        return 0.9
    if query in candidate:
        return 0.8
    if candidate in query:
        return 0.7
    # 逐字覆盖率
    hit = sum(1 for ch in query if ch in candidate)
    return 0.6 * (hit / len(query)) if hit else 0.0
