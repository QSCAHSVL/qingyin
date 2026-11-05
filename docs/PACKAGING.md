# 打包与交付（v1 / v2 / v3）

> **2026-11-05 更新：v1/v2/v3 已按要求全部卸载下线，当前版本是 v4（网页界面重做 + 在线找歌 + API 页）。**
> 下面这套打包脚本还能用，等 v4 稳定后再重新出包；日常直接用 `cover serve` 或 `cover desktop`。

三个版本不是三个产品，是同一套代码的三种外壳，按用户能力递进。

| 版本 | 形态 | 用户要做什么 | 体积 | 适合谁 |
|---|---|---|---|---|
| v1 | 绿色版目录 + `启动.bat` | 双击 | 0.3MB（不含 Python/模型） | 装过 Python 的人、想先试 |
| v2 | 安装包 `cover-pipeline-0.1.0-setup.exe` | 双击安装，向导里选依赖档位 | **2.06MB** | 普通用户 |
| v3 | 桌面窗口（pywebview） | 双击，出来一个窗口，不占浏览器 | 多约 30MB | 嫌浏览器标签乱的人 |

## v1 绿色版

```powershell
powershell -ExecutionPolicy Bypass -File scripts\portable.ps1
```

产出 `dist\cover-pipeline-portable\`，里面带 `启动.bat`。脚本会依次找：

1. `python\python.exe`（便携版 Python，放在目录里就是完全免装）
2. `py -3`
3. `python`

找不到就提示怎么装。依赖只查 `pyyaml`，缺了自动 `pip install`。

**为什么要留一个 `python\` 位置**：Windows 上最常见的失败就是「没装 Python」和「装的是 Microsoft Store 的假 python」。把 [python-build-standalone](https://github.com/astral-sh/python-build-standalone) 的解压版丢进 `python\`，就彻底不用管环境了。

## v2 安装包

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build-installer.ps1
```

先跑 v1 的打包，再调 Inno Setup 6 编译 `installer\cover-pipeline.iss`。
没装 Inno Setup 会明确提示去哪下（`winget install --id JRSoftware.InnoSetup -e`）。

### 装到哪、要不要管理员

`PrivilegesRequired=lowest`：**按当前用户装，不弹 UAC**，默认 `%LOCALAPPDATA%\Programs\cover-pipeline`。
卸载时连 `work\` `output\` `.venv\` `src\` `plugins\` `configs\` 一起删干净（实测卸载后目录不残留）。

### 依赖档位（三选一，默认「仅框架」）

| 档位 | 装什么 | 下载量 | 什么时候选 |
|---|---|---|---|
| 仅框架（默认） | 只装 pyyaml，然后 `cover link --auto` 认本机 RVC/UVR | ~1MB | **已经装过 RVC 或 UVR 的机器（推荐）** |
| 加上分离 | `audio-separator[gpu]`（失败自动退 `[cpu]`） | 0.3~1.5GB | 从没装过 UVR |
| 加上转换 | `torch`(cu121) + `rvc-python` | 4~6GB | 从没装过 RVC |

档位写在安装目录的 `deps.ini`，由安装向导里的 [Tasks] 勾选生成；
装完自动跑 `scripts\first_run.py`：建 `.venv` → 按档位装依赖 → `cover link --auto` → `cover doctor`。

**为什么默认只装框架**：torch 那 4~6GB 对已经跑过翻唱的人是纯浪费。
本项目的主路径就是「复用你机器上已有的 RVC/UVR」，只有全新机器才需要下载。
安装包本体因此只有 2MB，不背 torch 的锅。

`first_run.py` 也支持手动重跑（改了 deps.ini 之后），或直接双击安装目录里的 `setup-deps.bat`。

**装完会自动打开界面**（`启动.bat` 作为第二条 [Run]），不用自己找图标。
启动脚本的查找顺序是 `.venv` → `python\` → `py -3` → `python`，所以装过依赖的机器会直接用那个独立环境。

> 踩过的坑：Inno Setup 默认会记住上次的安装目录（`UsePreviousAppDir`）。
> 第一次选过别的盘，之后装会继续装到那儿——不是 bug，想换目录在向导里改。

## v3 桌面窗口

```powershell
pip install pywebview
cover desktop --port 7801
```

或双击 `启动-桌面版.bat`（第一次会自动装 pywebview）。

用 pywebview 而不是 Electron/Tauri 的原因：

- 不用装 Node、不用装 Rust，纯 Python 一条命令
- 复用系统自带的 WebView2（Win11 自带），体积只多几十 MB
- 界面代码和浏览器版完全同一份，不用维护两套

代价是窗口能力弱（托盘、多窗口、自动更新都要自己写）。真到需要这些的时候再换 Tauri 壳，界面不用改。

## 发布前检查清单

- [x] 安装包静默安装 → 运行 → 卸载，全流程实测通过（85 个文件、deps.ini 正确、卸载无残留）
- [x] 三种依赖档位的 deps.ini 写入正确（tier_core / tier_convert 各测一次）
- [ ] 绿色版在一台没装过 Python 的机器上验证 `python\` 兜底
- [ ] 仓库里没有 `plugins/`、`models/`、`work/`、`configs/local.yaml`
- [ ] 没有随包分发任何音色模型、解密代码或密钥
- [ ] README 第一屏能让人看懂「这是干什么的、怎么跑起来」

## 安装包（0.3.1 起）

```powershell
py -3 scripts/package.py                       # 先生成绿色版 zip
Expand-Archive dist\卿音-<版本>-portable.zip dist\卿音-<版本>-portable -Force
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" installer\cover-pipeline.iss
```

产物：`dist/卿音-<版本>-setup.exe`。安装到 `%LOCALAPPDATA%\Programs\QingYin`（免管理员），
带开始菜单、桌面快捷方式和卸载项；大依赖不进包，由程序内「环境配置」按机器装。
