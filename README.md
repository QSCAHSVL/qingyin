# 卿音（cover-pipeline）

[![CI](https://github.com/QSCAHSVL/qingyin/actions/workflows/ci.yml/badge.svg)](https://github.com/QSCAHSVL/qingyin/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10+-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)

**中文** ｜ [English](README.en.md)

> 本地翻唱流水线：找歌 → 人声分离 → 音色转换 → 混音出片，全在本机跑。

一条命令，从「歌名」到「成品翻唱」：**素材训练 → 人声分离 → 音色转换 → 混音 → 自动挑副歌 → 导出/发送**。

给 AI 新手的全流程翻唱流水线：不需要懂 RVC 参数，不需要会写脚本，装好、跑一条命令就行。

> 本项目只做**流程编排**。人声分离、音色转换依赖社区开源模型（UVR / RVC 等），音源与素材由使用者自行准备并确保合法授权。
> 本项目**不提供、不推荐、不内置**任何绕过版权保护的工具或方法。详见 [docs/DISCLAIMER.md](docs/DISCLAIMER.md)。

## 它解决什么问题

现有 RVC 生态大多停在「WebUI 点按钮」：分离要手动、参数要试、混音要自己拼、挑副歌靠耳朵。
本项目把这条链路固化成一条可复现的命令，并处理掉新手最容易踩的坑：

- **环境自检**：显卡/显存/依赖/模型，一次告诉你缺什么
- **训练向导**：素材丢进去，自动切分、清洗、提特征、训练、导出推理模型，并评估「素材够不够」
- **一键翻唱**：本地文件或链接进，成品音频出
- **自动挑段**：按能量挑副歌，默认 45 秒
- **自动降调**：按源人声音高判断，偏高整首降 1~3 半音
- **缓存复用**：成品比模型新就直接复用；模型重训后自动重跑

## 快速开始

```bash
pip install -e .
cover plan                      # 体检 + 回答三个问题 → 拿到 2~3 套方案
cover plan --apply vram8_balanced   # 选一套，写进配置
cover train --data ./materials  # 用你的素材训练音色（可选，也可直接用现成模型）
cover sing --song "歌名"        # 出成品
```

详细步骤见 [docs/QUICKSTART.md](docs/QUICKSTART.md)。

## 已经装过 RVC / UVR？直接用，不用重装

很多人机器上早就有 RVC 和 UVR5 了。本项目**不要求你再装一份**，它会自己找：

```bash
cover link --auto          # 自动探测本机的 RVC / UVR，写进配置
cover doctor               # 看有没有认到
```

探测顺序：配置文件里写的路径 → 常见默认位置（`E:/AI-Companion/tools/RVC`、`~/RVC` 等）→ 从 `uvr_sep.py` 往上找 GPT-SoVITS 的 venv。

找不到或者装在别处，手动指：

```bash
cover link --rvc-dir D:/RVC --rvc-python D:/RVC/.venv/Scripts/python.exe
cover link --uvr-script D:/tools/uvr_sep.py --uvr-python D:/tools/GPT-SoVITS/.venv/Scripts/python.exe
```

认到之后，`cover sing` 会直接调你本机这套程序：

- 分离：`<uvr_python> uvr_sep.py <输入> <输出> --model roformer`
- 转换：`<rvc_python> -m infer.cli ...`（工作目录 RVC 根目录，长音频自动分块 + 预热裁边拼接）

没有本地部署的人，也可以走 pip 版：`separate.backend: uvr` + `convert.backend: rvc`。

## 方案引擎（不知道选什么就让它选）

`cover plan` 会先体检你的机器（显卡、显存、内存、磁盘、ffmpeg、已装依赖），
再问三个问题（最在意什么、会不会自己训练、磁盘和等待时间），然后给出 2~3 套方案。

每套方案都写清楚：用什么分离模型、什么转换后端、训练多少轮、单曲多久、显存峰值、每首占多少磁盘，
以及**好处和代价**。推荐项会标 ★，但选哪个由你决定。

方案库在 `plans/`，是纯 YAML，想加自己的方案直接丢进去就行：

```yaml
id: my_plan
name: "我的 8G 方案"
for: { min_vram_gb: 7.5, max_vram_gb: 9.9, min_disk_gb: 25, needs_train: optional }
scores: { quality: 4, speed: 4, space: 3, stability: 5 }
params: { separate: {...}, convert: {...}, train: {...} }
estimate: { per_song_minutes: 4, vram_peak_gb: 6.8, disk_per_song_mb: 240, train_minutes: 50 }
pros: ["..."]
cons: ["..."]
explain: "一句话解释"
```

内置方案：`cpu_only`、`vram4_infer`、`vram6_balanced`、`vram8_balanced`、`vram8_quality`、
`vram12_quality`，以及进阶的 `svc_advanced`（默认不推荐给第一次用的人）。

## 命令一览

| 命令 | 作用 |
|---|---|
| `cover plan` | 体检 + 推荐方案，可 `--apply` 直接应用 |
| `cover link` | 探测/指定本机已装的 RVC 与 UVR |
| `cover serve` | 启动本地网页界面（默认 http://127.0.0.1:7801） |
| `cover desktop` | 桌面窗口模式（需要 pywebview） |
| `cover doctor` | 只做诊断，不改任何东西 |
| `cover init` | 环境自检 + 提示下一步 |
| `cover train --data <目录>` | 用素材训练音色模型 |
| `cover sing --song <歌名>` / `--input <文件>` | 生成翻唱成品 |
| `cover lib --scan` | 扫描资源库（模型/素材/成品/音源） |
| `cover fix --song <名字> --symptom seam_noise` | 症状诊断：同一段素材跑多种配方，试听对比 |
| `cover search "歌名"` | 在线找歌（B站 / iTunes），`--download N` 直接下第 N 个，`--sing` 顺带翻唱 |
| `cover sources` | 列出可用音源适配器 |
| `cover gui` | 旧版 gradio 界面（保留，推荐用 serve） |

## 界面

`cover serve` 起一个本地网页（http://127.0.0.1:7801），左侧十个入口：

- **开始**：一键翻唱（输歌名 → 自动找源 → 下载 → 翻唱）+ 五步引导（检查环境 → 接上本机 RVC/UVR → 选方案 → 准备模型 → 出第一首）
- **找歌**：B站 / iTunes / 网易云 / QQ音乐 四个平台一起搜；能下的直接「下载并翻唱」，只能给信息的会标「仅信息」并给「打开页面」「怎么用？」
- **翻唱**：给文件、文件夹或歌名。给文件夹会先列出曲目让你勾选（全选 / 全不选 / 取消），不会闷头开跑
- **任务**：进度、用时、日志，跑着的任务能一键取消
- **资源库**：模型 / 工程 / 成品 / 音源 / 收藏；点一行看详情，能试听、收藏、删除（挪到 `work/_trash`，不真删）
- **诊断**：6 类症状（接缝杂音、人声发闷、爆音削波、人声发干、伴奏盖人声、音色不像），每类 2~3 个解法，可以勾选多个一起跑对比
- **方案**：11 套内置方案，可按显存预算过滤，写入后能一键撤销回默认
- **训练**：素材目录 + 预检（总时长 / 段数 / 预计耗时 / 警告）、参数、开始训练；训完自动登记成新版本，可回滚
- **日志**：服务端日志与任务日志，按行数看尾部，不用去翻文件
- **设置**：三个数据目录（试写校验）、发布配置、备份
- **API**：接口一览页（`/docs`），GET 都能「试一下」；外部 Agent 接入见下

界面只用标准库（`http.server`）加原生 JS，不依赖 FastAPI/uvicorn，也不用打包。

## 给外部 Agent 用

界面右上角「API」页有本地 key，外部 Agent（DSH、WorkBuddy、自写脚本）可以这样调：

```bash
# 查接入信息（含本地 key）
curl http://127.0.0.1:7801/api/agent/info

# 让 cover-pipeline 唱一首
curl -X POST http://127.0.0.1:7801/api/agent/sing \
  -H "X-Api-Key: cp_xxx" -H "Content-Type: application/json" \
  -d '{"query":"千年食谱颂","full":false}'

# 查任务
curl "http://127.0.0.1:7801/api/agent/status?id=<job_id>"
```

不想带 key 也可以直接用公开接口 `/api/sing`、`/api/search`、`/api/jobs`。

## 打包成软件

| 版本 | 怎么出 | 用户怎么用 |
|---|---|---|
| v1 绿色版 | `scripts\portable.ps1` | 双击 `启动.bat` |
| v2 安装包 | `scripts\build-installer.ps1`（需 Inno Setup 6）→ 产出 2MB 的 `cover-pipeline-0.1.0-setup.exe` | 双击安装，向导里选依赖档位，默认复用本机 RVC/UVR |
| v3 桌面窗口 | `启动-桌面版.bat` 或 `cover desktop` | 独立窗口，不占浏览器 |

细节和体积、依赖分档见 [docs/PACKAGING.md](docs/PACKAGING.md)。

## 素材要求（训练）

- 10~30 分钟干净人声，尽量无伴奏、无混响、无背景音乐
- 单人、同设备、同环境最好
- 支持 wav / flac / mp3，可含子目录
- 素材不足时 `cover train` 会提示「建议至少 X 分钟」，但允许继续（效果自负）

## 目录结构

```
configs/            配置与预设（fast / balanced / hq）
plans/              方案库（按显存和偏好分档，纯 YAML）
src/cover_pipeline/
  cli.py            命令入口
  probe.py          硬件与环境探测
  plan/             方案引擎：打分、渲染方案卡、写入配置
  core/             分离、转换、混音、挑段、变调
  pipelines/        train / sing 两条编排
  sources/          音源适配层（本地文件 + 用户自备插件）
  utils/            ffmpeg、日志
plugins/            用户自己的音源插件放这里（不进仓库）
docs/               文档
scripts/            安装脚本
```

## 音源接口（重要）

主仓库只内置 `local_file`（本地音频文件）。
其他来源（在线平台、自己的下载工具、自己的解密工具）请放在 `plugins/`，本项目不内置、不附带、不解释。

接口说明见 [docs/SOURCES.md](docs/SOURCES.md)。

## 硬件门槛

| 显存 | 能做什么 |
|---|---|
| 8G+ | 训练 + 推理，推荐 |
| 6G | 训练降 batch，推理正常 |
| 4G | 仅推理 |

CPU 也能跑，但慢很多，不建议训练。

## 文档

| 想知道什么 | 看这个 |
|---|---|
| 15 分钟跑通第一次翻唱 | [QUICKSTART.md](docs/QUICKSTART.md) |
| 环境怎么一键配好 / 各组件下多大 | [SETUP.md](docs/SETUP.md)、[ASSETS.md](docs/ASSETS.md) |
| 参数怎么选、为什么这么选 | [PLANS.md](docs/PLANS.md) |
| 训练自己的音色模型、版本怎么管 | [TRAIN.md](docs/TRAIN.md)、[MODELS.md](docs/MODELS.md) |
| 音源怎么接别的平台 | [SOURCES.md](docs/SOURCES.md)、[PROVIDERS.md](docs/PROVIDERS.md) |
| 怎么打包发版 | [PACKAGING.md](docs/PACKAGING.md) |
| 版权与风险边界 | [DISCLAIMER.md](docs/DISCLAIMER.md)、[RISK.md](docs/RISK.md) |
| 这个项目是怎么长出来的 | [JOURNAL.md](docs/JOURNAL.md)（决策与踩坑流水）、[REVIEW.md](docs/REVIEW.md) |
| 接手继续开发 | [NEXT-SESSION.md](docs/NEXT-SESSION.md)、[PLAN.md](docs/PLAN.md) |

> [FINAL-PLAN.md](docs/FINAL-PLAN.md) 是最早的整体规划，部分条目已过时，只作历史参考。

## 许可

代码 MIT。依赖的开源项目各自遵循其许可证（UVR、RVC、ffmpeg 等）。
**音色模型与训练素材的授权由使用者自行负责**，请勿用他人声音训练或传播模型。

- 第三方组件（RVC / UVR / Demucs / FFmpeg / yt-dlp 等）的许可与来源见 [ATTRIBUTION.md](ATTRIBUTION.md)。
- 本项目**不内置**任何解密实现、**不打包**任何音色模型；权重与素材由使用者自行准备并承担责任。

## 状态

0.4.2，能直接用：`cover setup` 一键配置 → `cover sing` 出一首翻唱；本地网页界面（`cover serve`）有 10 个页面、59 个接口。
代码结构：后端 `server/app.py` 只留路由，业务在 `server/services/*.py`；前端按页面拆成原生 ES module（`static/pages/*.js`）。
59 条单元测试 + 前端静态检查（语法/import/export）进 CI，ruff 0 告警且已从「非阻断」转正。

还没做的：Demucs 后端只做了接口、没做真机验证；安装包的开始菜单/桌面图标/卸载残留要人工点一遍。

## 更新历史

每个版本的改动记在 [CHANGELOG.md](CHANGELOG.md)（最新 0.4.2，最早 0.2.0），README 不再逐版粘贴。
