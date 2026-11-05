# 下一个会话从这里开始

> 这份文件是给「接手的人」看的：读完就能接着干，不用翻聊天记录。

## 现在的状态（2026-11-06 03:19）

- 仓库：https://github.com/QSCAHSVL/qingyin ，第 6 轮已在本地提交（**还没 push**，所以 CI 还没跑）
- 本地：`E:\AI-Companion\tools\cover-pipeline`，工作区干净
- 测试：55 条全绿（`PYTHONPATH=src py -3 -m unittest discover -s tests -t .`）
- 已发布：`v0.4.1`，Release 里有 `qingyin-0.4.1-portable.zip` 与 `-setup.exe`（安装包已静默安装+卸载验证）
- 环境：git 代理 `http.proxy=http://127.0.0.1:7897`（仓库本地配置）；GitHub 凭据在 Windows 凭据管理器

## 已完成（七轮）

1. 版本单一来源 `scripts/sync_version.py`（CI `--check`）、ruff 非阻断、Release 重建、安装包实测
2. 方案引擎闭环：`plan/stats.py` 实测回写 + `plan/heal.py` 失败自愈，已接进 `jobs/manager._record_plan_stat`
3. API 契约测试 `tests/test_api_contract.py`（前端调用 / 后端路由 / OpenAPI 三方对齐）、`config.validate` 接进 `load_config`
4. 首页状态同步（指标时间戳、进度标注、禁用按钮提示）
5. 12+3 个漏文档接口补进 `_EXTRA_PATHS`
6. CI 修编码（`PYTHONIOENCODING`）、JS 语法检查改 `pwsh`
7. **拆 `server/app.py`**：1605 → 391 行，业务搬到 `server/services/*.py`，接口描述抽到 `server/openapi.py`

## 第 6 轮拆完的结构（下轮动 app.js 之前先看这个）

```
server/
  app.py        391 行  AppState（只放状态）+ make_handler（纯路由）+ _profile_from_query + serve
  openapi.py    252 行  API_CATEGORIES / _EXTRA_PATHS / openapi_spec
  services/
    __init__.py         约定说明
    common.py    35 行  ffmpeg_duration / gpu_used_gb / is_inside
    probe.py    117 行  cached_probe / snapshot_payload / resources / onboarding
    plans.py    169 行  recommend_payload / available / current / apply_by_id / clear / setup_plan / submit_setup / link_tools
    library.py   97 行  list_payload / stats / favorites / item / delete / set_favorite / batch / scan
    models.py    42 行  voices / activate / import_model / delete_model
    jobs.py     248 行  list_jobs / get_job / tail_log / cancel_job / retry_job / submit_sing|fix|tracks / plan_tracks / create_backup / recipes / adopt_recipe
    search.py   106 行  providers / search / submit_search_download / submit_oneclick
    train.py    104 行  config / preview / submit_train / save_config
    settings.py 153 行  settings / save_settings / save_send_config / disclaimer / ack_disclaimer / agent_key / agent_info
    system.py   203 行  logs_list / logs_tail / fs_list / pick_folder / reveal / assets_list / install_asset
```

约定（加新接口照这个来）：

- service 函数签名 `func(state, ...) -> dict`，**返回值就是响应体**；状态码、鉴权、query 解析留在 app.py
- app.py 里一条路由 = 解析参数 → 调一个 service → `self._json(...)`，不写业务
- 新接口要同时改三处：app.py 路由、openapi.py 的 `paths`、前端 `static/app.js`
- `tests/test_api_contract.py` 现在扫两个文件：路由字面量只在 `app.py` 找，接口文档在 `app.py` + `openapi.py` 里找

## 下一轮任务

### 第 7 轮：拆 `app.js`（1896 行）+ 最小构建
- 按页面拆成 `pages/*.js`，用原生 ES module（`type="module"`），不引框架
- 加 `node --check` 之外的静态检查（可选 eslint，先非阻断）
- **验收：界面行为不变，无控制台报错**

### 顺手要修的 bug（第 6 轮发现，本轮要求纯重构所以没改）
- `POST /api/jobs/{id}/retry` 必然 500：`jobs/manager.py::JobManager.get()` 返回的是 `job.as_dict()`（dict），
  而 `server/services/jobs.py::retry_job` 却按对象用（`job.kind`、`getattr(job, "payload", None)`）→ `AttributeError`。
  修法：改成 `job["kind"]` / `job["payload"]`，再补一条测试。
  已用 HEAD 副本确认这是**重构前就有**的 bug，不是第 6 轮引入的（代码是原样搬过去的）。
  复现：`py -3 E:\AI-Companion\_tmp\round6\retry_proof.py`

## 必须真机（我做不了）
- Demucs：装一遍（约 2GB 模型）跑一首，确认 `separate.backend=demucs` 可用
- 安装包交互：开始菜单、桌面图标、卸载残留

## 开工前先做

```powershell
cd E:\AI-Companion\tools\cover-pipeline
$env:PYTHONPATH = "$PWD\src"
py -3 -m unittest discover -s tests -t .
```

## 可复用的验证脚本（都在仓库外，没提交）

- `E:\AI-Companion\_tmp\round6\baseline\`：重构前后 HTTP 契约快照 + diff（`capture.py` / `diff.py`，64 个端点）
- `E:\AI-Companion\_tmp\round6\audit\`：路由清单 / OpenAPI / 方法体 AST 三方比对（`run_audit.py` 一键跑）
- `E:\AI-Companion\_tmp\round6\lead_smoke.py`：13 个「会起后台任务」的 service 冒烟测试（重活全部打桩）

第 7 轮拆 `app.js` 可以照抄这套思路：**先抓行为基线，再动代码，最后用两套独立证据对账**。
