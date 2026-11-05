"""方案实测统计：把每次跑的结果回写，供推荐时加权。"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
_DEFAULT = ROOT / "work" / "plan_stats.jsonl"
_path_override: Path | None = None


def stats_path() -> Path:
    return _path_override or _DEFAULT


def record(plan_id: str, ok: bool, seconds: float | None = None, kind: str | None = None,
           note: str | None = None) -> None:
    """记一条实测。kind 用失败类型：oom / timeout / missing_model / invalid_input。"""
    path = stats_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"plan": plan_id, "ok": bool(ok), "seconds": seconds, "kind": kind,
           "note": (note or "")[:200], "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def summary() -> dict[str, dict[str, Any]]:
    """按方案聚合：跑了几次、成功几次、平均耗时、各失败类型计数。"""
    out: dict[str, dict[str, Any]] = {}
    path = stats_path()
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        pid = str(row.get("plan") or "")
        if not pid:
            continue
        item = out.setdefault(pid, {"runs": 0, "ok": 0, "seconds": [], "kinds": {}})
        item["runs"] += 1
        if row.get("ok"):
            item["ok"] += 1
        if isinstance(row.get("seconds"), (int, float)):
            item["seconds"].append(float(row["seconds"]))
        kind = row.get("kind")
        if kind:
            item["kinds"][kind] = item["kinds"].get(kind, 0) + 1
    for item in out.values():
        secs = item.pop("seconds")
        item["avg_seconds"] = round(sum(secs) / len(secs), 1) if secs else None
        item["success_rate"] = round(item["ok"] / item["runs"], 2) if item["runs"] else None
    return out


def adjust(plan_id: str, score: float, table: dict[str, dict[str, Any]] | None = None) -> float:
    """按实测微调分数：成功率高给加成，OOM/超时扣分。幅度控制在 ±8%。"""
    table = table if table is not None else summary()
    item = table.get(plan_id)
    if not item or not item.get("runs"):
        return score
    rate = item.get("success_rate") or 0.0
    factor = 0.92 + 0.16 * rate
    kinds = item.get("kinds") or {}
    if kinds.get("oom"):
        factor -= 0.03 * min(kinds["oom"], 3)
    if kinds.get("timeout"):
        factor -= 0.02 * min(kinds["timeout"], 3)
    return round(score * max(0.86, min(1.08, factor)), 2)
