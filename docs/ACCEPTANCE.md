# 安装包与真机验收清单

> 自动测试能覆盖代码，覆盖不了「图标好不好看」「卸载干不干净」。这份清单是 0.4.4 人工验收时
> 一条条点出来的，照着走一遍大概 15 分钟。发现问题就补到对应条目下面，别只记在聊天里。

## 一、安装包（Windows）

前提：`scripts\build-installer.ps1` 出好 `dist/卿音-<版本>-setup.exe`。

| # | 操作 | 预期 | 备注 |
|---|---|---|---|
| 1 | 双击 setup.exe，走完向导，**勾上「创建桌面快捷方式」** | 装完提示成功 | 没管理员权限时会装到 `%LOCALAPPDATA%\Programs\QingYin`，正常 |
| 2 | 看桌面快捷方式 | 有「卿音」图标（Q 版小鲸鱼），不是白板 | 0.4.3 曾出现白板：`.bat` 不带图标且 iss 没写 `IconFilename` |
| 3 | 看开始菜单「卿音」文件夹 | 三个：`卿音`、`卿音 环境自检`、`卸载 卿音`，**三个都有图标** | 卸载那条要靠 `SetupIconFile` / `UninstallDisplayIcon`，否则用 Inno 默认图标 |
| 4 | 点「卿音」 | 起本地网页（默认 7801），侧边十个入口都在 | 用 `curl 127.0.0.1:7801/api/health` 看 version 对不对 |
| 5 | 点「卿音 环境自检」 | 控制台跑 `cover doctor`，不闪退 | |
| 6 | **先关掉资源管理器里打开的安装目录**，再点「卸载 卿音」 | 卸完安装目录整个消失 | 目录被资源管理器占着时 Windows 删不掉根目录，会剩空壳——不是安装包的问题 |
| 7 | 卸载后复查 | 开始菜单文件夹、桌面快捷方式、`控制面板 → 应用` 里的条目都没了 | 注册表项 `HKCU\...\Uninstall\{6C1F8A22-...}_is1` 应一起消失 |

自动化可代劳的部分（不用手点）：

```powershell
# 静默安装 / 卸载（带桌面图标）
Start-Process .\dist\卿音-0.4.4-setup.exe -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/TASKS="desktopicon"' -Wait
Start-Process "$env:LOCALAPPDATA\Programs\QingYin\unins000.exe" -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART' -Wait
```

## 二、Demucs 分离后端（真机）

代码路径在 `core/separate.py::_separate_demucs`，配置项 `separate.backend: demucs`，
但**没在真机验证过**（要装 300MB 依赖 + 首次跑还要下模型）。

1. `cover setup --separation demucs`（或 `py -3 -m pip install demucs`，必须装在跑卿音的那个解释器里）
2. `configs/local.yaml` 里把 `separate.backend` 改成 `demucs`
3. `cover sing --input 某首.wav --name demucs测试`
4. 通过标准：日志出现「用 Demucs 分离（htdemucs）…」，`2-分离轨道/` 下有 `vocal.wav` 和 `instrumental.wav`；
   和 UVR 版同一首对比，人声残留更少
5. 验完把 `separate.backend` 改回 `local_uvr`，否则以后每首都走 Demucs（慢）

## 三、验收记录

- 2026-11-06 0.4.3：发现快捷方式无图标（`.bat` 无内嵌图标 + iss 没写 `IconFilename`）、
  卸载残留 `logs/` `work/` `output/` `plugins/*/__pycache__`（`[UninstallDelete]` 只列了 `.venv` 和 `src/**/__pycache__`）
- 2026-11-06 0.4.4：图标修复（含卸载器图标）、卸载改为清空整个 `{app}` + `dirifempty` 兜底；
  自动化安装/卸载全通过，人工只确认了图标与启动
- 待办：Demucs 真机（上述第二节）
