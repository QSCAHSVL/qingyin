# 下一个会话从这里开始

> 这份文件是给「接手的人」看的：读完就能接着干，不用翻聊天记录。
> 路径约定：`<repo>` 指仓库根目录（本项目所在目录），一律不写本机绝对路径——这个文件会进发布包。

## 现在的状态（2026-11-06 15:0x）

- 仓库：https://github.com/QSCAHSVL/qingyin ，第 6～7 轮 + 复审 + 收尾都已在 origin/main，CI 全绿
- 本地：`<repo>`，工作区干净，与 origin/main 同步
- 测试：122 条全绿（`PYTHONPATH=src py -3 -m unittest discover -s tests -t .`）
- 前端静态检查：`py -3 scripts/check_frontend.py`（语法 + import 路径 + export 名，16 个文件 0 问题）
- 版本：0.4.3，已发 Release（`qingyin-0.4.3-portable.zip` / `-setup.exe` / `SHA256SUMS.txt` 由工作流自动上传）
- 打包：`scripts\build-installer.ps1` 一条命令出 zip + 安装包
- 发版：`git tag v0.4.3 && git push origin v0.4.3` → `.github/workflows/release.yml` 自动打包并上传资产
  （首跑踩过：CI 上 choco 装的 Inno Setup 不带中文语言文件，已把 `installer/Languages/ChineseSimplified.isl` 收进仓库）
- 本机跑着网页界面的进程（`127.0.0.1:7801`）：静态文件是按请求读盘的，改完刷新即可；改了后端要重启进程

## 已完成（八轮）

1. 版本单一来源 `scripts/sync_version.py`（CI `--check`）、ruff 非阻断、Release 重建、安装包实测
2. 方案引擎闭环：`plan/stats.py` 实测回写 + `plan/heal.py` 失败自愈，已接进 `jobs/manager._record_plan_stat`
3. API 契约测试 `tests/test_api_contract.py`（前端调用 / 后端路由 / OpenAPI 三方对齐）、`config.validate` 接进 `load_config`
4. 首页状态同步（指标时间戳、进度标注、禁用按钮提示）
5. 12+3 个漏文档接口补进 `_EXTRA_PATHS`
6. CI 修编码（`PYTHONIOENCODING`）、JS 语法检查改 `pwsh`
7. 拆 `server/app.py`：1605 → 391 行，业务搬到 `server/services/*.py`，接口描述抽到 `server/openapi.py`
8. 拆 `static/app.js`：1917 行 → `core.js` + `nav.js` + `router.js` + `pages/*.js`(10) + `ui/*.js`(2)，
   原生 ES module，`index.html` 改成 `<script type="module" src="/static/app.js?v=10">`
9. 修 `POST /api/jobs/{id}/retry` 必然 500（`JobManager.get()` 返回 dict 且不含 payload），补 4 条回归测试
10. 复审：修 `core/pitch.py` 的 NameError（整首移调必崩）；`pyproject` 的 ruff `target-version` 修好；ruff 130 → 0 并转成 CI 阻断
11. 收尾：README 文档索引 + 英文 README 重写；测试 71 → 122（资源库/服务层/方案写入/配方/本地音源/混音）；
    打包合成一条命令；新增 Release 工作流

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

### 第 9 轮：上真机 + 补最后的空白
- 真机：Demucs 装一遍（约 2GB 模型）跑一首，确认 `separate.backend=demucs`（代码路径在，没跑过）
- 安装包交互：开始菜单、桌面图标、卸载残留（`dist/卿音-0.4.3-setup.exe`，需人工点一遍）
- 示例音频：仓库里一条试听样例都没有（`examples/` 不存在，git 里也没有 wav/mp3），新人看不到效果
- 可选：前端把页面模块改成按需 `import`（现在是全量载入，首屏多拉十几 KB）
- 可选：`core/convert.py`（RVC 命令拼装）目前只靠真机验证，可以像 `core/mix.py` 那样把 ffmpeg/子进程打桩补测试

## 开工前先做

```powershell
cd <repo>
$env:PYTHONPATH = "$PWD\src"
py -3 -m unittest discover -s tests -t .
py -3 scripts/check_frontend.py
py -3 -m ruff check src tests
```

## 打包与发版

```powershell
scripts\build-installer.ps1                 # 一条命令：绿色版 zip + Inno 安装包（需要 Inno Setup 6）
scripts\build-installer.ps1 -SkipInstaller  # 只出绿色版
git tag v0.4.3; git push origin v0.4.3      # 推标签 → Release 工作流自动打包上传
```

> `package.py` 会扫 `[A-Z]:\` 这种个人盘路径，命中就中止——文档里一律用 `<repo>` 之类的相对写法。
> `installer/cover-pipeline.iss` 的 `AppSource` 跟版本号联动，改版本只需改 `__init__.py` 再跑 `sync_version.py`。
> `scripts/build-installer.ps1` 里有中文，**改动后必须存成 UTF-8 with BOM**，否则 PowerShell 5.1 会解析成乱码。

## 可复用的验证脚本（都在仓库外，没提交）

- `_r7_split.py`：第 7 轮切分生成器（按 section 切片 + 跨模块改名 + 加 import/export），放在本机数据目录的
  `qq-bridge\state\agents\` 下（具体路径见 memory-handoff，不进仓库）
- `_r7_baseline.ps1`：**新旧两版逐页 dump DOM 对比**（换回旧 `app.js.bak-round7-*` → dump → 换新版 → dump → Compare-Object），同目录
- 第 6 轮的验证脚本（本机临时目录 `_tmp\round6\`，不进仓库）：
  - `baseline\`：HTTP 契约快照 + diff（`capture.py` / `diff.py`，64 个端点）
  - `audit\`：路由清单 / OpenAPI / 方法体 AST 三方比对（`run_audit.py` 一键跑）
  - `lead_smoke.py`：13 个「会起后台任务」的 service 冒烟测试（重活全部打桩）

第 8 轮照抄这套思路：**先抓行为基线，再动代码，最后用两套独立证据对账**。
