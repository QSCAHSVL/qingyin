# 卿音（cover-pipeline）

[![CI](https://github.com/QSCAHSVL/qingyin/actions/workflows/ci.yml/badge.svg)](https://github.com/QSCAHSVL/qingyin/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10+-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)


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

`cover serve` 起一个本地网页（http://127.0.0.1:7801），左侧八个入口：

- **开始**：一键翻唱（输歌名 → 自动找源 → 下载 → 翻唱）+ 五步引导（检查环境 → 接上本机 RVC/UVR → 选方案 → 准备模型 → 出第一首）
- **找歌**：B站 / iTunes / 网易云 / QQ音乐 四个平台一起搜；能下的直接「下载并翻唱」，只能给信息的会标「仅信息」并给「打开页面」「怎么用？」
- **翻唱**：给文件、文件夹或歌名。给文件夹会先列出曲目让你勾选（全选 / 全不选 / 取消），不会闷头开跑
- **任务**：进度、用时、日志，跑着的任务能一键取消
- **资源库**：模型 / 工程 / 成品 / 音源 / 收藏；点一行看详情，能试听、收藏、删除（挪到 `work/_trash`，不真删）
- **诊断**：6 类症状（接缝杂音、人声发闷、爆音削波、人声发干、伴奏盖人声、音色不像），每类 2~3 个解法，可以勾选多个一起跑对比
- **方案**：11 套内置方案，可按显存预算过滤，写入后能一键撤销回默认
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

## 许可

代码 MIT。依赖的开源项目各自遵循其许可证（UVR、RVC、ffmpeg 等）。
**音色模型与训练素材的授权由使用者自行负责**，请勿用他人声音训练或传播模型。

## 状态

骨架阶段：命令、配置、接口、文档已就位，核心算法正在接入。
## 0.2.0 更新（2026-11-05）

- 正式命名 **卿音**（代码包仍叫 cover-pipeline）
- 找歌支持四个平台：B站、iTunes、网易云、QQ音乐；**标准音质（mp3/m4a）免解密直接下**，高音质需要自己接解密插件
- 解密插件接口：`providers.DecryptProvider`，模板 `plugins/providers/example_decrypt.py`
- 资源库重做：分页 + 每页条数 + 跳页、多选批量收藏/删除、行内按钮、点名字在资源管理器定位
- 诊断：6 类症状，可勾选多个解法一起对比；工程选择框改成可滚动列表
- 方案：支持显存预算过滤、撤销方案；「为什么没有别的方案」收进折叠区
- 一键翻唱：首页输入歌名，自动找源 → 下载 → 翻唱
- 外部 Agent：`/api/agent/info`、`/api/agent/sing`（X-Api-Key）、`/api/agent/status`
- 静态资源禁缓存，改完刷新就生效
## 界面设计（0.2.1）

按 `ui-design` skill 重做了一遍，规则写死在 `style.css` 顶部的令牌里：

- **颜色/字阶/间距/半径/阴影/动效** 全部走 CSS 变量，组件里不写魔法数字
  （字阶 11/12/13/14/15/20/26，间距 4/8/12/16/20/24/32，动效 120/180/240ms ease-out）
- **图标**换成一套内联 SVG symbol（24×24、stroke 1.75、圆角端点），导航和按钮都用 `<use>`，不再用 emoji
- **动效**：页面切换 180ms 淡入 + 6px 上移；卡片悬停只改阴影不改尺寸；按钮按下 1px；
  进度条带流光；列表加载用骨架屏；弹层 240ms 缩放进入；`prefers-reduced-motion` 下全关
- **交互**：每个控件都有 hover / focus-visible / active / disabled / loading 状态；
  弹层有焦点管理和 Esc 关闭、打开时锁页面滚动；键盘 `/` 聚焦搜索、`Ctrl+Enter` 触发当前页主按钮
- **状态**：数据区有 loading（骨架）/ empty（带下一步）/ error（带原因）三态
## 0.2.2 更新（2026-11-05）

- **音色模型版本管理**：每版权重单独存档，`cover models use` 一键切换，界面上「资源库 → 音色」也能点；训练完成后自动登记新版本（见 [docs/MODELS.md](docs/MODELS.md)）
- **报错翻译成人话**：`utils/errors.py` 把 OOM、缺依赖、找不到 ffmpeg、平台限流、路径错误等翻译成「原因 + 怎么办」，任务页和命令行都用
- **整首移调**：不再只对人声移调，人声和伴奏一起移，避免和原曲对不上
- **分轨导出**：成品旁边多一份人声和伴奏（`4-成品/stems/`），方便二次处理
- **单元测试**：`tests/` 里 14 个用例（模型版本、错误分类、方案引擎、资源库、在线解析），跑法 `py -3 -m unittest discover -s tests -t .`
- **依赖锁** `requirements.lock`、英文 [README.en.md](README.en.md)
## 0.2.3 更新（2026-11-05）

- 全面复核了需求和配置：把 7 个「写了但没读」的僵尸配置全部接上
  （`clip.mode` / `clip.energy_window` / `separate.keep_backing` / `device.gpu_index` /
  `train.clean` / `send.enabled+target+account` / `project.log_level`）
- 训练前会按音量过滤过安静片段（`train.clean_threshold_db`，默认 -40dB）
- 成品生成后可选择走发布插件（`send.enabled: true` 时）
- 详细复核结论与遗留项见 [docs/REVIEW.md](docs/REVIEW.md)
## 0.2.4 更新（2026-11-05）

- **新用户模型推荐**：`cover init` / `cover plan` 会按显卡、显存、磁盘、是否训练、是否已有 RVC/UVR，
  算出「还需要下什么、多大、从哪拿」；界面方案页可展开看明细，接口是 `GET /api/plan` 的 `assets` 字段
- 清单本体在 `assets/manifest.yaml`，可自己加模型条目；说明见 [docs/ASSETS.md](docs/ASSETS.md)
## 0.2.5 更新（2026-11-05）

- **一键配置**：`cover setup` 探测环境 → 推荐方案 → 列出要装的依赖和要下的模型 → 确认后自动执行（pip + 断点续传下载 + 写配置 + 自检）
- 界面首页多了「环境配置」卡片：显示探测结果、步骤清单和「确认并自动配置」按钮，进度可取消
- 权重下载默认走 hf-mirror（国内可达），官方 HF 兜底，可配置换源；已存在的权重自动跳过
- 接口：`GET/POST /api/setup/plan`（预览）、`POST /api/setup/run`（执行）；说明见 [docs/SETUP.md](docs/SETUP.md)
## 0.2.6 更新（2026-11-05）

- 修「环境配置卡隔一会闪一下」：首页指标轮询从 5s 改成 10s，且只在首页可见时跑
  （切到别的页或标签隐藏就不请求）；环境配置只在进入首页时拉一次，「重新检查」按钮才重拉
- 指标卡原地更新数值，不再整块重建，避免视觉跳动
- `/api/health` 增加 `counters`（如 `setup_plan` 请求次数），排查「界面是不是在反复请求」用
  - 页脚连接状态改为「连续失败两次才提示」，浏览器切页造成的连接中断不再误报
## 0.2.7 更新（2026-11-05）

- **环境探测改为手动**：进首页什么都不查，显示「还没检测」+ 一个「检测环境」按钮；
  点一下才跑 `nvidia-smi` 和扫目录，同时填好指标卡。指标另有「刷新指标」按钮，不再定时轮询。
- 服务端探测加 60 秒缓存，`?refresh=1` 强制刷新（实测首次 293ms，命中缓存 25ms）
- 删掉首页的定时刷新，界面不再「隔一会卡一下」
## 0.2.8 更新（2026-11-05）

- **接口按用途分类**（8 类 44 个）：环境与配置 / 方案 / 找歌 / 翻唱与任务 / 资源库 / 音色模型 / Agent 接入 / 系统
- `/docs` 页重做：左侧分类导航带数量，右侧按类分组，GET 接口仍可直接「试一下」
- `/api/openapi.json` 里每个接口带 `tags`，顶层带 `tags` 描述，Agent 可以按类筛选
## 0.2.9 更新（2026-11-05）· 新中式视觉

- 配色改成宣纸/墨/朱砂/竹青/赭石：浅色是米白纸面，深色是墨底；朱砂只用在主按钮、当前导航、标题竖线
- 标题换思源宋体系（Songti / Noto Serif SC，缺字体回退宋体），正文仍用黑体
- 圆角收到 4~6px，去阴影靠发丝线分层，进度条改成细线+缓流光
- 品牌标识改成朱砂印章「音」，导航当前项用左侧朱砂竖线而不是整块底色
- 动效放慢到 200/300/420ms，位移 4~8px，去掉弹跳
- 新增主题切换：页脚「主题：跟随系统 / 宣纸 / 墨」，也可用 `?theme=light|dark`
- 设计参考（GitHub）：Tabler/Lucide 的线条图标语言、Radix Colors 与 Open Props 的令牌组织、
  Arco/Semi/TDesign 的克制版式、anime.js 与 Motion One 的时长曲线；「新中式」本身没有成熟设计系统，靠宣纸色与宋体排版自己定
## 打包发布

```bash
py -3 scripts/package.py --check   # 只检查会打进包的文件
py -3 scripts/package.py           # 生成 dist/卿音-<版本>-portable.zip
```

打包用**白名单**而不是黑名单：只有 `src/ plans/ recipes/ assets/ docs/ configs/default.yaml plugins/ tests/ examples/`
和几个启动脚本会进包，新产生的私人文件默认不会被带出去。打包前会自动扫描 QQ 号、个人盘路径、密钥口令，
命中就中止。压缩包里带 `SHA256SUMS.txt`，下载后可校验。

**不会进包的东西**：`work/`（你的工程和成品）、`output/`、`models/`（训练出的音色权重）、
`configs/local.yaml`（本机路径和设置）、`decisions.jsonl`、`work/_agent_key.txt`（Agent 密钥）、`dist/`。

## 隐私

- 全程本地运行，不上传任何音频或日志；只有「在线找歌」和「下载模型」会联网
- 服务默认只监听 `127.0.0.1`，不对外网开放
- `/api/agent/*` 用 `work/_agent_key.txt` 里的本地密钥校验，密钥不进包也不进版本库
- 训练出的音色模型属于个人信息，只存在本机 `models/`，永远不进发布包
## 项目档案

| 文件 | 内容 |
|---|---|
| [CHANGELOG.md](CHANGELOG.md) | 每个版本改了什么 |
| [docs/JOURNAL.md](docs/JOURNAL.md) | 项目日志：当天做了什么、撞了什么坑、为什么这么决定、还欠什么 |
| [docs/REVIEW.md](docs/REVIEW.md) | 需求复核与遗留项 |
| `logs/` | 运行日志：`server-<日期>.log`、`jobs/<任务id>.log` |

看日志：`cover logs`（默认最新文件尾 30 行），或 `cover logs --tail 200`。
`logs/` 不进版本库也不进发布包，属于本机运行记录。
## 0.3.1 更新（2026-11-05）

- **训练闭环打通**：`train.command` 支持 `{rvc_dir}`/`{rvc_python}`/`{model_name}`，训练完自动从 `output_dirs` 和 RVC `assets/weights` 找模型并登记版本；轮数 <20 会提示（RVC 每 20 轮才存检查点）
- **Demucs 可选分离**：`separate.backend: demucs`；`cover setup --separation auto|uvr|demucs|both|none`，配置时按磁盘/显存推荐（紧张选 Demucs，否则 UVR）
- **安装包**：`dist/卿音-0.3.1-setup.exe`（开始菜单、桌面快捷方式、卸载项）

## 0.3.2 更新（2026-11-05）

- **设置页**：可视化改三个数据目录（work / output / models），显示解析后路径、文件数与占用；
  保存前逐个试写校验，写入 `configs/local.yaml`（自动备份），提示重启生效
- 接口 `GET /api/settings`、`POST /api/settings`；接口分类新增「设置」
- 各页面副标题改短，从「解释功能」改成「一句操作提示」

## 0.3.3 更新（2026-11-05）· 训练页

- **训练页**：填素材目录 → 「预检」（文件数、总时长、预计段数、预计耗时、警告）→ 填音色名/轮数/batch/采样率 → 「开始训练」，
  后台跑、有进度，训练完自动登记新版本并提示去「资源库 → 音色」切回旧版
- 训练命令可视化配置：页内填 `train.command`（含两个模板按钮：RVC 官方 train.py / train_model.py），
  保存进 `configs/local.yaml`，下次生效
- 接口：`GET /api/train/config`、`GET /api/train/preview?data=…`、`POST /api/train`、`POST /api/train/config`

## 0.3.4 更新（2026-11-05）

- 路径不用手打了：素材目录、数据目录、音频目录旁边都有「选择…」，点开就是系统原生的文件夹选择框
- 实现方式：浏览器拿不到绝对路径，所以由本机服务端弹对话框（`POST /api/pick-folder`），选完把路径回填到页面

## 0.3.5 更新（2026-11-05）

- 「选择…」改成页内文件浏览器：盘符 → 目录 → 文件，双击进入、底部「选择此文件夹」，不依赖系统窗口
- 系统对话框保留为「用系统对话框」（只在服务跑在你自己的交互会话里才弹得出来），并加了置顶 owner
- 输入框和按钮统一 36px 高

## 0.3.7 更新（2026-11-05）

- 按钮统一尺寸（36/30），新增危险态；表单行统一底部对齐，去掉临时对齐补丁
- 资源库筛选改分段控件；找歌平台开关改 chip；页脚连接状态全局统一

## 声明与致谢

- 使用前请读 [docs/DISCLAIMER.md](docs/DISCLAIMER.md)：仅供个人学习与自娱，不得商用、不得传播他人声音模型。
- 第三方组件（RVC / UVR / Demucs / FFmpeg / yt-dlp 等）的许可与来源见 [ATTRIBUTION.md](ATTRIBUTION.md)。
- 本项目**不内置**任何解密实现、**不打包**任何音色模型；权重与素材由使用者自行准备并承担责任。

