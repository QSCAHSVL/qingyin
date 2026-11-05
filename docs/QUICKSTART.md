# 快速开始

> 界面：`cover serve` 打开 http://127.0.0.1:7801 。首页可以直接「一键翻唱」（输歌名自动找源），也可以按五步引导走。

> v4 界面：cover serve 打开 http://127.0.0.1:7801 ，首页有五步引导，找不到歌就用「找歌」页在线搜。
（Windows / 新手向）

## 0. 先确认硬件

- NVIDIA 显卡，8G 显存最舒服；6G 能用；4G 只能推理
- 硬盘留 20G 以上（模型和中间产物）
- 没独显也能跑，但训练会非常慢

## 1. 装环境

需要 Python 3.10 或更新版本。装好后在这个目录里执行：

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

再装 ffmpeg（音频处理都要它）：

```bat
winget install Gyan.FFmpeg
```

装完**重开一个终端**，敲 `ffmpeg -version` 能看到版本号才算成功。

## 1.5 已经装过 RVC / UVR？先认一下

如果你机器上早就有 RVC 和 UVR5（比如之前跑过翻唱），不用重装：

```bat
cover link --auto
```

它会自己找 `RVC` 目录、RVC 的 python、`uvr_sep.py`、跑 UVR 的 python，写进配置。
装在别处就用参数指：

```bat
cover link --rvc-dir D:/RVC --rvc-python D:/RVC/.venv/Scripts/python.exe
cover link --uvr-script D:/tools/uvr_sep.py --uvr-python D:/tools/GPT-SoVITS/.venv/Scripts/python.exe
```

认完 `cover doctor` 里会显示「本地 RVC / 本地 UVR」，之后跑翻唱直接调用它们。

## 2. 自检并选方案

```bat
cover plan
```

这一步会先体检，再问你三个问题（最在意什么、会不会自己训练、磁盘和等待时间），
然后给出 2~3 套方案，每套都写清楚好处和代价，推荐项标 ★。

选好之后：

```bat
cover plan --apply vram8_balanced
```

想只做诊断、不改任何东西：

```bat
cover doctor
```

看到 `✗` 就按提示补；看到 `!` 是提醒，可以先继续。

## 3. 准备素材并训练

把你唱歌的录音放到一个目录，比如 `D:\voice\mine`。要求：

- 尽量干净：无伴奏、无混响、无背景音
- 10~30 分钟足够；少于 10 分钟会提示效果可能不稳
- wav / flac / mp3 都行，可以放子目录

```bat
cover train --data D:\voice\mine --name mysing
```

跑完会得到一个数据集目录，并告诉你怎么接训练。如果你已经装好 RVC 训练环境，
在 `configs/local.yaml` 里配一行 `train.command` 就能全自动。

## 4. 出成品

用本地文件：

```bat
cover sing --input D:\music\song.flac --name 歌名
```

用歌名（需要先在配置里填搜索目录）：

```bat
cover sing --song "歌名" --name 歌名
```

成品默认在 `work\<歌名>\4-成品\` 下，是一个 45 秒的副歌片段。
想要全曲：

```bat
cover sing --input D:\music\song.flac --name 歌名 --full
```

## 5. 常见问题

**跑一半报 ffmpeg 找不到**
PATH 没生效，重开终端；或者把 ffmpeg 的 bin 目录手动加进 PATH。

**显存不够**
加 `--preset fast`，或者先把 `train.batch_size` 调小。

**想听效果但不想等训练**
不训练也能跑：给 `convert.backend: none`，就只做分离和混音，输出「伴奏 + 原人声」。

**想换音色**
训练多个模型，用 `--preset` 之外的方式指定 `convert.model`，或在 `configs/local.yaml` 里改。

**结果咬字糊**
把 `convert.protect` 调高（0.5 → 0.66），`index_rate` 适当降低。

## 5. 用界面（可选但推荐）

```bat
cover serve
```

浏览器会打开 http://127.0.0.1:7801 。六个页签：概览（显存/内存/磁盘/资源库）、方案、翻唱、任务、资源库、诊断。

## 6. 打包给不会用命令行的人

```bat
:: v1 绿色版
powershell -ExecutionPolicy Bypass -File scripts\portable.ps1

:: v2 安装包（需要 Inno Setup 6）
powershell -ExecutionPolicy Bypass -File scripts\build-installer.ps1

:: v3 桌面窗口
启动-桌面版.bat
```

详见 [PACKAGING.md](PACKAGING.md)。