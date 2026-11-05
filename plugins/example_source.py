"""音源插件模板：复制这个文件改名，改成你自己的实现。

注意：
- 文件名不要以 _ 开头（会被跳过）
- name 必须唯一
- resolve() 返回一个真实存在的本地音频文件路径
"""

from __future__ import annotations

from pathlib import Path

from cover_pipeline.sources import SourceAdapter, register


@register
class ExampleSource(SourceAdapter):
    name = "example"
    description = "示例：把 query 当成一个远程地址下载下来（这里只演示结构）"

    def resolve(self, query: str, work_dir: Path, cfg: dict) -> Path:
        work_dir.mkdir(parents=True, exist_ok=True)
        target = work_dir / "downloaded.wav"

        # TODO: 你的获取逻辑。要求：
        #   1. 只处理你有权使用的来源
        #   2. 输出统一成 wav / flac / mp3 之一
        #   3. 失败时抛异常，附一句人能看懂的说明
        raise NotImplementedError("把这里换成你自己的实现")

        # return target