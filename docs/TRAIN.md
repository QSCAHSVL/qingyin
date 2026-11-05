# 训练说明

## 素材准备

| 项目 | 要求 |
|---|---|
| 时长 | 10~30 分钟干净人声；少于 10 分钟效果不稳 |
| 内容 | 说话或唱歌都行，但**要和你打算生成的内容同类型**（唱歌模型最好用唱歌素材） |
| 质量 | 无伴奏、无混响、无背景音乐、无他人声音 |
| 格式 | wav / flac / mp3，可以放子目录 |
| 一致性 | 同一设备、同一环境录的最好，别混着来 |

素材不干净时，训练出来的模型会带底噪或串音。宁可少而干净，不要多而杂。

## 跑训练

```bash
cover train --data D:\voice\mine --name mysing
```

这个命令会：

1. 扫描素材、统计总时长，不够会提示
2. 统一采样率、转单声道
3. 按 8 秒切段（少于 2.5 秒的碎片丢掉）
4. 输出到 `work/mysing/0-数据集/`

## 接入真正的训练

本项目不内置训练器，因为它依赖 RVC 的训练代码与环境。两种接法：

### 方式 A：配置命令模板（推荐）

在 `configs/local.yaml`：

```yaml
train:
  epochs: 80
  command: python D:/RVC/train_cli.py --data {dataset} --name {name} --epochs {epochs} --batch {batch} --sr {sample_rate}
```

占位符：

| 占位符 | 含义 |
|---|---|
| `{dataset}` | 切好的数据集目录 |
| `{name}` | 模型名 |
| `{epochs}` | 轮数 |
| `{batch}` | batch size |
| `{sample_rate}` | 采样率 |

### 方式 B：用 RVC WebUI 手动训练

把 `work/<name>/0-数据集/` 整个目录当成素材喂给 RVC WebUI 的训练页即可。
训练完成后把导出的 `.pth`（和可选的 `.index`）放到 `models/` 下，命名和 `convert.model` 对应。

## 训练完怎么用

模型放进 `models/` 后：

```yaml
convert:
  model: mysing
```

```bash
cover sing --input D:\music\song.flac --name 歌名
```

模型文件比成品新时，同一首歌会自动重跑，不会拿旧成品糊弄你。

## 参数怎么调

| 现象 | 调整 |
|---|---|
| 咬字糊 | `protect` 调高（0.5 → 0.66） |
| 音色不够像 | `index_rate` 调高（0.75 → 0.9） |
| 有电流/杂音 | 检查素材是否干净；`protect` 调低一点 |
| 音高别扭 | 关掉 `auto_pitch`，手动 `pitch` 试 -1 / -2 |
| 训练过拟合 | 减少 `epochs`，或增加素材多样性 |

## 时间参考

RTX 4060 8G、约 370 段样本、80 轮：约 45~50 分钟。
显存越小越慢，6G 大约翻倍。
