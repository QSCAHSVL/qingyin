# 音源接口（插件）

主仓库**只内置** `local_file`：给一个已经能正常读取的音频文件，或者给歌名在配置的目录里模糊匹配。

其他来源请自己写在项目根目录的 `plugins/` 下。这个目录在 `.gitignore` 里，不会被提交。

## 为什么这样设计

- 项目只负责「拿到一个可读音频文件 → 出成品」，不关心文件怎么来的
- 音源获取涉及版权与各平台条款，**由使用者自行负责**，本项目不内置、不推荐、不解释任何绕过版权保护的做法
- 想接什么自己接，接完就能用，不用改主仓库代码

## 写一个适配器

在 `plugins/` 下新建任意 `.py`，例如 `plugins/my_source.py`：

```python
from pathlib import Path
from cover_pipeline.sources import SourceAdapter, register


@register
class MySource(SourceAdapter):
    name = "my_source"            # 唯一名字，配置里用它
    description = "我自己的音源"

    def resolve(self, query: str, work_dir: Path, cfg: dict) -> Path:
        # 你的逻辑：把 query 变成本地音频文件路径
        target = work_dir / "from_my_source.wav"
        # ... 下载 / 转换 / 复制 ...
        return target
```

然后在 `configs/local.yaml` 里指定：

```yaml
source:
  adapter: my_source
```

跑 `cover sources` 可以看到是否注册成功。

## 约定

- `resolve()` 必须返回一个真实存在的本地文件路径
- 出错时抛异常，带一句人能看懂的说明
- 不要在插件里硬编码密钥；用环境变量或 `configs/local.yaml`（后者已在 `.gitignore` 里）
- 插件抛异常不会拖垮主流程，只会打一条警告

## 关于本地文件

如果你手上的文件已经是 wav/flac/mp3，直接用内置的 `local_file` 就行：

```yaml
source:
  adapter: local_file
  search_dirs:
    - D:/music
```

或者命令里直接给路径：

```bash
cover sing --input D:/music/song.flac --name 歌名
```
