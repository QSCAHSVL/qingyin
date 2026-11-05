"""失败自愈：按日志归类失败原因，给出降档方案。"""

from __future__ import annotations

import copy
import re
from typing import Any

RULES: list[tuple[str, str]] = [
    (r"out of memory|OOM|CUDA out of memory|显存不足|Allocation on device", "oom"),
    (r"timeout|timed out|超时|idle", "timeout"),
    (r"no such file|not found|找不到|missing|No module named", "missing_model"),
    (r"invalid|bad argument|解码失败|unsupported", "invalid_input"),
]

MAX_ATTEMPTS = 2


def classify(error_text: str) -> str:
    text = error_text or ""
    for pattern, kind in RULES:
        if re.search(pattern, text, re.IGNORECASE):
            return kind
    return "unknown"


def degrade(plan: dict[str, Any], kind: str) -> dict[str, Any] | None:
    """给一份更保守的方案；降不下去就返回 None。"""
    if kind == "invalid_input":
        return None
    out = copy.deepcopy(plan)
    params = out.setdefault("params", {})
    changed = False
    if kind == "oom":
        train = params.setdefault("train", {})
        batch = int(train.get("batch_size") or 1)
        if batch > 1:
            train["batch_size"] = batch - 1
            changed = True
        convert = params.setdefault("convert", {})
        if not convert.get("half"):
            convert["half"] = True
            changed = True
    if kind in {"oom", "timeout"}:
        clip = params.setdefault("clip", {})
        seconds = int(clip.get("seconds") or 45)
        if seconds > 30:
            clip["seconds"] = max(30, seconds - 10)
            changed = True
        sep = params.setdefault("separate", {})
        if kind == "oom" and not sep.get("fallback"):
            sep["fallback"] = "demucs"
            changed = True
    if kind == "missing_model":
        sep = params.setdefault("separate", {})
        if sep.get("backend") != "demucs":
            sep["backend"] = "demucs"
            changed = True
    if not changed:
        return None
    out["id"] = f"{plan.get('id')}+heal{kind}"
    out["name"] = f"{plan.get('name', '方案')}（自动降档：{kind}）"
    out["healed_from"] = plan.get("id")
    out["heal_kind"] = kind
    return out


def next_plan(plan: dict[str, Any], error_text: str, attempt: int) -> dict[str, Any] | None:
    """第 attempt 次失败后要不要再来一次。attempt 从 1 开始，最多 MAX_ATTEMPTS 次。"""
    if attempt >= MAX_ATTEMPTS:
        return None
    return degrade(plan, classify(error_text))
