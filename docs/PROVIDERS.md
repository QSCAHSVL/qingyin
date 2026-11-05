# 接入自己的服务（providers）

三类扩展点，都在 `plugins/` 下，都不进仓库：

| 类型 | 目录 | 干什么 |
|---|---|---|
| source | `plugins/*.py` | 去哪找原曲（本地曲库、网盘、自己的接口） |
| publish | `plugins/providers/*.py` | 成品发到哪（网盘、自己的群、自己的 App） |
| ai | `plugins/providers/*.py` | 额外的 AI 处理（降噪、修音、字幕） |

## 发布插件

```python
from cover_pipeline.providers import PublishProvider, register_publish

@register_publish
class MyPublish(PublishProvider):
    name = "my_publish"

    def send(self, audio, meta, cfg):
        ...
        return "已发送"
```

然后在 `configs/local.yaml`：

```yaml
providers:
  publish: my_publish
  publish_options:
    token: "从环境变量或这里读，别提交"
    target: "my-target"
```

模板见 `plugins/providers/example_publish.py`。

## 内置的

- `local_folder`：拷到 `output/`（或 `providers.publish_options.dir`），可以按 `{name}{suffix}` 模板改名。

## 为什么只留接口不写实现

不同人的成品去向差别太大：有人发网盘、有人发自己搭的 Web、有人直接丢群。
主仓库只保留「本地文件夹」这一种最通用、零配置的实现，其余让用户自己接，
避免仓库里出现别人的地址、密钥和私有协议。