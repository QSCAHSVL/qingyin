"""示例：接自己的高音质解密服务。

本项目不提供解密实现，这个文件只是接口模板。
用法：
1. 复制到 plugins/providers/decrypt_mine.py
2. 把 fetch() 换成你自己的调用（调本地解密程序、调你自己搭的服务都行）
3. configs/local.yaml 里写：
     providers:
       decrypt: mine
4. 找歌页把音质切到「高音质」，就会走这个插件
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cover_pipeline.providers import DecryptProvider, register_decrypt


@register_decrypt
class MyDecrypt(DecryptProvider):
    name = "mine"

    def fetch(self, track: dict[str, Any], dest_dir: Path) -> Path:
        source = track.get("source")
        track_id = track.get("id")
        raise NotImplementedError(
            f"还没接解密服务：{source} / {track_id}。"
            "把你自己的解密程序接到这里，返回解密后的音频路径。"
        )