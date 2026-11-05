"""示例：把成品发到自己的地方（这里只是打印路径）。

用法：
1. 复制本文件到 plugins/providers/my_publish.py 并改名字
2. 在 configs/local.yaml 里设 providers.publish: my_publish
3. 之后 cover sing 结束时会自动调用 send()

注意：plugins/ 在 .gitignore 里，不会进仓库；不要把密钥写进代码，
      放到 configs/local.yaml（同样不进仓库）里读。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cover_pipeline.providers import PublishProvider, register_publish


@register_publish
class MyPublish(PublishProvider):
    name = "my_publish"

    def send(self, audio: Path, meta: dict[str, Any], cfg: dict[str, Any]) -> str:
        options = (cfg.get("providers") or {}).get("publish_options") or {}
        token = options.get("token", "")
        target = options.get("target", "default")

        # 在这里接你自己的接口，例如：
        #   requests.post(url, headers={"Authorization": f"Bearer {token}"}, files={...})
        print(f"[my_publish] 假装把 {audio.name} 发到 {target}（token 长度 {len(token)}）")
        return f"已发送：{audio.name} → {target}"