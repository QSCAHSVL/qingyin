# plugins/

放你自己的音源插件。这个目录里的东西**不会**被提交到仓库（`.gitignore` 已排除）。

- 想接自己的音源：参考 `example_source.py`，复制改名，实现 `resolve()`
- 注册后在 `configs/local.yaml` 里把 `source.adapter` 改成你的名字
- `cover sources` 可以确认有没有加载成功

详见 [../docs/SOURCES.md](../docs/SOURCES.md)。