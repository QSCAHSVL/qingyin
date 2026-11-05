"""接口描述（OpenAPI 片段）：/docs 页和外部调用者看的就是这里的内容。

只放文档，不放业务；路由实现仍在 app.py。
"""

from __future__ import annotations

from typing import Any

from .. import __version__

# 接口分类：给 /docs 页和外部调用者用
API_CATEGORIES: list[dict[str, Any]] = [
    {"name": "环境与配置", "description": "探测硬件、推荐方案、一键装依赖和模型", "match": (
        "/api/onboarding", "/api/setup/", "/api/link", "/api/probe", "/api/resources")},
    {"name": "方案", "description": "硬件驱动的参数方案：推荐、应用、撤销", "match": (
        "/api/plan", "/api/plans/")},
    {"name": "找歌", "description": "四个平台搜索、下载、一键翻唱", "match": (
        "/api/search", "/api/oneclick")},
    {"name": "翻唱与任务", "description": "跑翻唱、批量、任务状态与取消、症状配方", "match": (
        "/api/sing", "/api/jobs", "/api/fix", "/api/recipes")},
    {"name": "资源库", "description": "模型/工程/成品/音源：列表、收藏、删除、定位、试听", "match": (
        "/api/library", "/api/reveal", "/api/audio")},
    {"name": "音色模型", "description": "训练出来的版本：查看、切换、导入、删除", "match": (
        "/api/models",)},
    {"name": "训练", "description": "素材预检、训练音色、训练命令配置", "match": ("/api/train",)},
    {"name": "本机交互", "description": "调用系统对话框、备份、日志", "match": ("/api/pick-folder", "/api/logs", "/api/backup")},
    {"name": "组件", "description": "清单里缺什么，一键装", "match": ("/api/assets",)},
    {"name": "Agent 接入", "description": "给外部 Agent 用的精简入口（带 X-Api-Key）", "match": (
        "/api/agent/",)},
    {"name": "设置", "description": "数据目录、服务信息", "match": ("/api/settings",)},
    {"name": "系统", "description": "健康检查、接口清单", "match": ("/api/health", "/api/openapi.json")},
]


def category_for(path: str) -> str:
    for item in API_CATEGORIES:
        for prefix in item["match"]:
            if path.startswith(prefix):
                return item["name"]
    return "系统"


_EXTRA_PATHS: dict[str, Any] = {
    "/api/assets": {"get": {"summary": "列出可安装的组件清单", "responses": {"200": {"description": "组件列表"}}}},
    "/api/assets/install": {"post": {"summary": "安装指定组件", "responses": {"200": {"description": "任务对象"}}}},
    "/api/backup": {"post": {"summary": "打包备份数据目录", "responses": {"200": {"description": "任务对象"}}}},
    "/api/disclaimer": {"get": {"summary": "读取免责声明确认状态", "responses": {"200": {"description": "确认状态"}}}},
    "/api/disclaimer/ack": {"post": {"summary": "确认已阅读免责声明", "responses": {"200": {"description": "确认结果"}}}},
    "/api/fs/list": {
        "get": {
            "summary": "列出目录内容（文件浏览器）",
            "parameters": [
                {"name": "path", "in": "query", "required": False, "schema": {"type": "string"}},
                {"name": "ext", "in": "query", "required": False, "schema": {"type": "string"}},
            ],
            "responses": {"200": {"description": "目录条目"}},
        }
    },
    "/api/pick-folder": {"post": {"summary": "调系统文件夹选择框（可选 dry_run）", "responses": {"200": {"description": "选中的路径或降级提示"}}}},
    "/api/jobs/{job_id}/retry": {"post": {"summary": "重跑失败的任务", "responses": {"200": {"description": "任务对象"}}}},
    "/api/logs": {"get": {"summary": "列出日志文件", "responses": {"200": {"description": "日志列表"}}}},
    "/api/logs/tail": {
        "get": {
            "summary": "读取某个日志的尾部",
            "parameters": [
                {"name": "name", "in": "query", "required": True, "schema": {"type": "string"}},
                {"name": "lines", "in": "query", "required": False, "schema": {"type": "integer"}},
            ],
            "responses": {"200": {"description": "日志行"}},
        }
    },
    "/api/settings/send": {"post": {"summary": "保存外发配置（默认关闭）", "responses": {"200": {"description": "保存结果"}}}},
    "/api/train/config": {"get": {"summary": "读取训练配置与命令模板", "responses": {"200": {"description": "训练配置"}}}},
    "/api/settings": {
        "get": {"summary": "读取当前配置（隐藏敏感项）", "responses": {"200": {"description": "配置快照"}}},
        "post": {"summary": "局部修改配置", "responses": {"200": {"description": "保存结果"}}},
    },
    "/api/train": {"post": {"summary": "提交一次训练任务", "responses": {"200": {"description": "任务对象"}}}},
    "/api/train/preview": {"post": {"summary": "训练参数预览（不执行）", "responses": {"200": {"description": "预览结果"}}}},
}


def openapi_spec() -> dict[str, Any]:
    """手写的接口描述，给 /docs 页和外部调用者看。"""
    def ok(desc: str) -> dict[str, Any]:
        return {"description": desc, "content": {"application/json": {"schema": {"type": "object"}}}}

    paths: dict[str, Any] = {
            "/api/health": {"get": {"summary": "存活检查", "responses": {"200": ok("服务信息")}}},
            "/api/probe": {"get": {"summary": "硬件与环境探测", "responses": {"200": ok("探测结果")}}},
            "/api/resources": {"get": {"summary": "显存/内存/磁盘/库容量", "responses": {"200": ok("资源快照")}}},
            "/api/onboarding": {"get": {"summary": "引导清单状态", "responses": {"200": ok("五个步骤的完成情况")}}},
            "/api/plan": {
                "get": {
                    "summary": "推荐配置方案",
                    "parameters": [
                        {"name": "prefer", "in": "query", "schema": {"type": "string", "enum": ["quality", "speed", "space", "stability"]}},
                        {"name": "train", "in": "query", "schema": {"type": "string", "enum": ["yes", "no", "unsure"]}},
                        {"name": "disk", "in": "query", "schema": {"type": "number"}},
                        {"name": "patience", "in": "query", "schema": {"type": "number"}},
                    ],
                    "responses": {"200": ok("方案卡列表")},
                }
            },
            "/api/plan/apply": {
                "post": {
                    "summary": "应用某个方案",
                    "requestBody": {"content": {"application/json": {"schema": {"type": "object", "properties": {"id": {"type": "string"}}}}}},
                    "responses": {"200": ok("写入结果")},
                }
            },
            "/api/search": {
                "get": {
                    "summary": "在线找歌（B站 / iTunes / 网易云 / QQ音乐）",
                    "parameters": [
                        {"name": "q", "in": "query", "required": True, "schema": {"type": "string"}},
                        {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 12}},
                    ],
                    "responses": {"200": ok("搜索结果")},
                }
            },
            "/api/search/download": {
                "post": {
                    "summary": "下载搜索结果（可选接着翻唱）",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "url": {"type": "string"},
                                        "title": {"type": "string"},
                                        "name": {"type": "string"},
                                        "sing": {"type": "boolean"},
                                        "full": {"type": "boolean"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": ok("任务对象")},
                }
            },
            "/api/sing": {
                "post": {
                    "summary": "翻唱（本地文件 / 歌名 / 在线链接）",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "input": {"type": "string"},
                                        "song": {"type": "string"},
                                        "name": {"type": "string"},
                                        "full": {"type": "boolean"},
                                        "force": {"type": "boolean"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": ok("任务对象")},
                }
            },
            "/api/jobs": {"get": {"summary": "任务列表", "responses": {"200": ok("任务数组")}}},
            "/api/jobs/{id}": {"get": {"summary": "任务状态", "responses": {"200": ok("任务详情")}}},
            "/api/jobs/{id}/log": {"get": {"summary": "任务日志", "responses": {"200": {"description": "纯文本"}}}},
            "/api/library": {
                "get": {
                    "summary": "资源库列表（支持 kind / q / page / size）",
                    "parameters": [
                        {"name": "kind", "in": "query", "schema": {"type": "string", "enum": ["model", "song", "output", "source"]}},
                        {"name": "q", "in": "query", "schema": {"type": "string"}},
                    ],
                    "responses": {"200": ok("条目数组")},
                }
            },
            "/api/library/scan": {"post": {"summary": "重建资源库索引", "responses": {"200": ok("任务对象")}}},
            "/api/library/stats": {"get": {"summary": "资源库统计", "responses": {"200": ok("按类型汇总")}}},
            "/api/search/providers": {"get": {"summary": "可用的搜索来源", "responses": {"200": ok("平台列表")}}},
            "/api/sing/plan": {
                "post": {
                    "summary": "判断给的是文件/文件夹/歌名",
                    "requestBody": {"content": {"application/json": {"schema": {"type": "object", "properties": {"input": {"type": "string"}, "song": {"type": "string"}}}}}},
                    "responses": {"200": ok("曲目列表")},
                }
            },
            "/api/sing/tracks": {"post": {"summary": "按选中的曲目批量翻唱", "responses": {"200": ok("任务对象")}}},
            "/api/oneclick": {"post": {"summary": "一键翻唱（自动找源+下载+翻唱）", "responses": {"200": ok("任务对象")}}},
            "/api/jobs/{id}/cancel": {"post": {"summary": "取消任务", "responses": {"200": ok("取消结果")}}},
            "/api/library/item": {"get": {"summary": "单个资源详情", "responses": {"200": ok("详情")}}},
            "/api/library/favorite": {"post": {"summary": "收藏 / 取消收藏", "responses": {"200": ok("结果")}}},
            "/api/library/delete": {"post": {"summary": "删除到回收站", "responses": {"200": ok("结果")}}},
            "/api/library/favorites": {"get": {"summary": "收藏列表", "responses": {"200": ok("列表")}}},
            "/api/plan/current": {"get": {"summary": "当前生效的方案", "responses": {"200": ok("方案信息")}}},
            "/api/plan/clear": {"post": {"summary": "撤销方案，恢复默认", "responses": {"200": ok("结果")}}},
            "/api/agent/info": {"get": {"summary": "给外部 Agent 的接入信息（含本地 key）", "responses": {"200": ok("接入信息")}}},
            "/api/agent/sing": {"post": {"summary": "外部 Agent 调一键翻唱（X-Api-Key）", "responses": {"200": ok("任务对象")}}},
            "/api/agent/status": {"get": {"summary": "外部 Agent 查任务状态", "responses": {"200": ok("任务详情")}}},
            "/api/setup/plan": {
                "get": {"summary": "探测环境并给出配置步骤（GET 用默认偏好）", "responses": {"200": ok("方案 + 步骤")}},
                "post": {"summary": "同上，可带 prefer/train/max_vram", "responses": {"200": ok("方案 + 步骤")}},
            },
            "/api/setup/run": {"post": {"summary": "确认后执行配置（装依赖/下模型/写配置）", "responses": {"200": ok("任务对象")}}},
            "/api/link": {"post": {"summary": "接上本机已有的 RVC / UVR（写进配置）", "responses": {"200": ok("结果")}}},
            "/api/plans/available": {"get": {"summary": "所有方案（不做推荐排序）", "responses": {"200": ok("方案列表")}}},
            "/api/reveal": {"post": {"summary": "在资源管理器里定位文件（限定项目目录内）", "responses": {"200": ok("结果")}}},
            "/api/library/batch": {"post": {"summary": "批量收藏 / 取消收藏 / 删除", "responses": {"200": ok("处理条数")}}},
            "/api/openapi.json": {"get": {"summary": "本接口清单（机器可读）", "responses": {"200": ok("OpenAPI 片段")}}},
            "/api/models": {"get": {"summary": "音色模型版本列表", "responses": {"200": ok("按音色分组的版本")}}},
            "/api/models/activate": {"post": {"summary": "切换模型版本", "responses": {"200": ok("结果")}}},
            "/api/models/import": {"post": {"summary": "导入 .pth 作为新版本", "responses": {"200": ok("结果")}}},
            "/api/models/delete": {"post": {"summary": "删除某个版本（当前在用的不能删）", "responses": {"200": ok("结果")}}},
            "/api/recipes": {"get": {"summary": "症状与配方", "responses": {"200": ok("配方列表")}}},
            "/api/fix": {
                "post": {
                    "summary": "跑一组配方做对比",
                    "requestBody": {"content": {"application/json": {"schema": {"type": "object", "properties": {"song": {"type": "string"}, "symptom": {"type": "string"}, "seconds": {"type": "number"}}}}}},
                    "responses": {"200": ok("任务对象")},
                }
            },
            "/api/fix/adopt": {"post": {"summary": "采纳某个配方", "responses": {"200": ok("记录结果")}}},
            "/api/audio": {
                "get": {
                    "summary": "播放项目内的音频（只读）",
                    "parameters": [{"name": "path", "in": "query", "required": True, "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "音频字节"}},
                }
            },
                }

    paths.update(_EXTRA_PATHS)

    for path, entry in paths.items():
        tag = category_for(path)
        for method_spec in entry.values():
            if isinstance(method_spec, dict):
                method_spec["tags"] = [tag]

    return {
        "openapi": "3.0.3",
        "info": {
            "title": "QingYin API",
            "version": __version__,
            "description": "本地翻唱流水线的 HTTP 接口。全部在本机 127.0.0.1 上，除 /api/agent/* 外不需要鉴权。",
        },
        "servers": [{"url": "http://127.0.0.1:7801"}],
        "tags": [{"name": item["name"], "description": item["description"]} for item in API_CATEGORIES],
        "paths": paths,
    }
