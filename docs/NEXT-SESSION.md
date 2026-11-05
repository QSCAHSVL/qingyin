# 下一个会话从这里开始

> 这份文件是给「接手的人」看的：读完就能接着干，不用翻聊天记录。

## 现在的状态（2026-11-06 02:55）

- 仓库：https://github.com/QSCAHSVL/qingyin ，`main` = `4d5798c`，CI 全绿
- 本地：`E:\AI-Companion\tools\cover-pipeline`，工作区干净
- 测试：55 条全绿（`PYTHONPATH=src py -3 -m unittest discover -s tests -t .`）
- 已发布：`v0.4.1`，Release 里有 `qingyin-0.4.1-portable.zip` 与 `-setup.exe`（安装包已静默安装+卸载验证）
- 环境：git 代理 `http.proxy=http://127.0.0.1:7897`（仓库本地配置）；GitHub 凭据在 Windows 凭据管理器

## 已完成（六轮）

1. 版本单一来源 `scripts/sync_version.py`（CI `--check`）、ruff 非阻断、Release 重建、安装包实测
2. 方案引擎闭环：`plan/stats.py` 实测回写 + `plan/heal.py` 失败自愈，已接进 `jobs/manager._record_plan_stat`
3. API 契约测试 `tests/test_api_contract.py`（前端调用 / 后端路由 / OpenAPI 三方对齐）、`config.validate` 接进 `load_config`
4. 首页状态同步（指标时间戳、进度标注、禁用按钮提示）
5. 12+3 个漏文档接口补进 `_EXTRA_PATHS`
6. CI 修编码（`PYTHONIOENCODING`）、JS 语法检查改 `pwsh`

## 下一轮任务

### 第 6 轮：拆 `app.py`（1563 行）
- 目标：`server/app.py` 只留 HTTP 适配，业务搬到 `server/services/*.py`
- 顺序建议：probe → plans → library → jobs → train → settings
- **验收：55 条测试保持全绿，`/api/*` 路径与返回结构不变**

### 第 7 轮：拆 `app.js`（1896 行）+ 最小构建
- 按页面拆成 `pages/*.js`，用原生 ES module（`type="module"`），不引框架
- 加 `node --check` 之外的静态检查（可选 eslint，先非阻断）
- **验收：界面行为不变，无控制台报错**

### 必须真机（我做不了）
- Demucs：装一遍（约 2GB 模型）跑一首，确认 `separate.backend=demucs` 可用
- 安装包交互：开始菜单、桌面图标、卸载残留

## 开工前先做

```powershell
cd E:\AI-Companion\tools\cover-pipeline
$env:PYTHONPATH = "$PWD\src"
py -3 -m unittest discover -s tests -t .
```
