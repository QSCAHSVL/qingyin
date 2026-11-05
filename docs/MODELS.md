# 卿音 · 音色模型版本管理

训练一次要几十分钟，翻车是常事。所以每一版权重都单独存档，随时切回去，不用重训。

## 目录长什么样

```
models/
  active.json                   # 每个音色当前用哪一版
  yuzhou/
    versions/
      v1/  yuzhou.pth  meta.json
      v2/  yuzhou.pth  meta.json
```

`meta.json` 里记着：来源文件、sha256（前 16 位）、大小、登记时间、训练轮数、数据集段数。

## 三条命令

```bash
cover models list                          # 看所有音色和版本，● 是当前生效的
cover models use yuzhou v1                 # 切回 v1
cover models import --path D:/xxx.pth --voice yuzhou   # 把外部模型登记成新版本
cover models delete yuzhou v2              # 删掉某个版本（当前在用的不让删）
```

界面上在「资源库 → 音色」里，一行一个版本，右边「设为当前」一点就切。

## 训练时发生什么

`cover train` 跑完如果找到了导出的 `.pth`，会自动登记成新版本并设为当前。
所以「训练 → 听着不满意 → 切回上一版」是一步操作，不用手动找文件。

## 转换时用哪一版

`convert.model` 是 `default`（默认）时，优先用 `active.json` 指向的那一版；
想临时换一版，把 `convert.model` 写成绝对路径，或者用 `cover models use` 切。

成品不会被旧版影响：音频已经导出成文件了，切模型只影响之后新跑的。

## 建议的对比流程

1. 用 v1 唱 45 秒副歌，存在 `4-成品/`
2. `cover train` 出新版本（自动变 v2）
3. `cover models use yuzhou v2`，再唱同一首（加 `--force` 忽略缓存）
4. 两个成品直接对比，不满意就 `cover models use yuzhou v1` 切回去
