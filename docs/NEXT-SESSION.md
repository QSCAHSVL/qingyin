# 下一个会话从这里开始

> 这份文件是给「接手的人」看的：读完就能接着干，不用翻聊天记录。

## 现在的状态（2026-11-06 03:5x）

- 仓库：https://github.com/QSCAHSVL/qingyin ，第 7 轮已在本地提交（**还没 push**，所以 CI 还没跑）
- 本地：`E:\AI-Companion\tools\cover-pipeline`，工作区干净
- 测试：55 条全绿（`PYTHONPATH=src py -3 -m unittest discover -s tests -t .`）
- 前端静态检查：`py -3 scripts/check_frontend.py`（语法 + import 路径 + export 名，16 个文件 0 问题）
- 已发布：`v0.4.1`，Release 里有 `qingyin-0.4.1-portable.zip` 与 `-setup.exe`（安装包已静默安装+卸载验证）
- 环境：git 代理 `http.proxy=http://127.0.0.1:7897`（仓库本地配置）；GitHub 凭据在 Windows 凭据管理器
- 本机跑着网页界面的老进程（`127.0.0.1:7801`，PID 会变）：静态文件是按请求读盘的，改完刷新即可，不用重启

## 已完成（七轮）

1. 版本单一来源 `scripts/sync_version.py`（CI `--check`）、ruff 非阻断、Release 重建、安装包实测
2. 方案引擎闭环：`plan/stats.py` 实测回写 + `plan/heal.py` 失败自愈，已接进 `jobs/manager._record_plan_stat`
3. API 契约测试 `tests/test_api_contract.py`（前端调用 / 后端路由 / OpenAPI 三方对齐）、`config.validate` 接进 `load_config`
4. 首页状态同步（指标时间戳、进度标注、禁用按钮提示）
5. 12+3 个漏文档接口补进 `_EXTRA_PATHS`
6. CI 修编码（`PYTHONIOENCODING`）、JS 语法检查改 `pwsh`
7. 拆 `server/app.py`：1605 → 391 行，业务搬到 `server/services/*.py`，接口描述抽到 `server/openapi.py`
8. 拆 `static/app.js`：1917 行 → `core.js` + `nav.js` + `router.js` + `pages/*.js`(10) + `ui/*.js`(2)，
   原生 ES module，`index.html` 改成 `<script type="module" src="/static/app.js?v=10">`

## 第 6 轮拆完的后端结构（动 `app.py` 之前先看这个）

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
- 新接口要同时改三处：app.py 路由、openapi.py 的 `paths`、前端 `static/pages/<页>.js`
- `tests/test_api_contract.py` 现在扫两个文件：路由字面量只在 `app.py` 找，接口文档在 `app.py` + `openapi.py` 里找

## 第 7 轮拆完的前端结构（动前端之前先看这个）

```
static/
  index.html     <script type="module" src="/static/app.js?v=10">
  core.js    $, $$, el, api(), toast(), openModal/closeModal, net.connFailures, on()
  nav.js     go() / setNavigator()——路由与页面之间的回调，避免 ESM 循环依赖
  router.js  pages 名单 + go(page)：切 .page.active、按页触发 loadXxx()
  app.js     入口：import 各模块 + 绑定所有按钮 + boot()
  pages/     home search sing jobs library fix plan logs settings train
  ui/        picker（页内文件浏览器） theme（宣纸/墨）
```

约定：

- **页面模块只 import `core.js` / `nav.js` / 别的 `pages/`，不许 import `app.js`**
- 跨页面调用直接 `import { loadHome } from "../pages/home.js"`；真正环状的地方（`go`）走 `nav.js`
- 页面之间共享的可变状态别用 `export let`（导进来的绑定不能赋值）：要么用对象属性
  （`libState.kind`），要么导出 setter（`setSingJobId()`）。第 7 轮就这三处：`net.connFailures` / `libState` / `singJobId`
- 新增页面按钮：在 `pages/<页>.js` 里定义函数并 `export`，在 `app.js` 末尾绑定
- 改完跑 `py -3 scripts/check_frontend.py`（CI 里 `--syntax` 阻断、`--static` 先非阻断）

## 下一轮任务

### 第 8 轮：修 P0 bug + 上真机验证
- **`POST /api/jobs/{id}/retry` 必然 500**：`jobs/manager.py::JobManager.get()` 返回 `job.as_dict()`（dict），
  而 `server/services/jobs.py::retry_job` 按对象用（`job.kind`、`getattr(job, "payload", None)`）→ `AttributeError`。
  修法：改成 `job["kind"]` / `job["payload"]`，再补一条测试（这是重构前就有的 bug）。
  复现：`py -3 E:\AI-Companion\_tmp\round6\retry_proof.py`
- push 之后看 CI（第 7 轮新增的 `check_frontend.py` 两个步骤要全绿）
- 真机：Demucs 装一遍（约 2GB 模型）跑一首，确认 `separate.backend=demucs`；安装包交互（开始菜单/桌面图标/卸载残留）

## 开工前先做

```powershell
cd E:\AI-Companion\tools\cover-pipeline
$env:PYTHONPATH = "$PWD\src"
py -3 -m unittest discover -s tests -t .
py -3 scripts/check_frontend.py
```

## 可复用的验证脚本（都在仓库外，没提交）

- `D:\AI-Companion-Data\qq-bridge\state\agents\_r7_split.py`：第 7 轮切分生成器（按 section 切片 + 跨模块改名 + 加 import/export）
- `D:\AI-Companion-Data\qq-bridge\state\agents\_r7_baseline.ps1`：**新旧两版逐页 dump DOM 对比**（换回旧 `app.js.bak-round7-*` → dump → 换新版 → dump → Compare-Object）
- `E:\AI-Companion\_tmp\round6\baseline\`：第 6 轮的 HTTP 契约快照 + diff（`capture.py` / `diff.py`，64 个端点）
- `E:\AI-Companion\_tmp\round6\audit\`：路由清单 / OpenAPI / 方法体 AST 三方比对（`run_audit.py` 一键跑）
- `E:\AI-Companion\_tmp\round6\lead_smoke.py`：13 个「会起后台任务」的 service 冒烟测试（重活全部打桩）

第 8 轮照抄这套思路：**先抓行为基线，再动代码，最后用两套独立证据对账**。
