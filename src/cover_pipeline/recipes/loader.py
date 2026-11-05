"""配方库：症状 → 多个候选解法 → 试听对比 → 采纳。

每条配方都必须写清楚：怎么做（how）、花多少时间（cost）、有什么风险（risk）、
有没有实测证据（evidence）。没有证据的标成实验性，别装成结论。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import yaml

from .. import config as cfg_mod

RECIPES_DIR = cfg_mod.ROOT / "recipes"


def load_recipes(directory: Path | None = None) -> list[dict[str, Any]]:
    directory = directory or RECIPES_DIR
    if not directory.exists():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.yaml")):
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if isinstance(data, dict) and data.get("id"):
            data.setdefault("source", path.name)
            out.append(data)
    return out


def find_recipe(symptom_id: str, directory: Path | None = None) -> dict[str, Any] | None:
    for item in load_recipes(directory):
        if str(item.get("id")) == symptom_id:
            return item
    return None


def recommended_of(symptom: dict[str, Any]) -> str:
    """返回该症状的推荐配方 id（配方表里的 selected，没有就用第一个）。"""
    selected = symptom.get("selected")
    if selected:
        return str(selected)
    recipes = symptom.get("recipes") or []
    return str(recipes[0].get("id")) if recipes else ""


def describe(symptom: dict[str, Any]) -> str:
    """给界面用的一段文字说明。"""
    lines = [f"症状：{symptom.get('symptom', '')}"]
    rec = recommended_of(symptom)
    for item in symptom.get("recipes") or []:
        mark = "★ 推荐" if item.get("id") == rec else "  "
        lines.append(f"{mark} {item.get('name')}：{item.get('how', '')}")
        lines.append(f"      代价 {item.get('cost', '?')}｜风险 {item.get('risk', '?')}")
        if item.get("evidence"):
            lines.append(f"      证据：{item['evidence']}")
        if item.get("experimental"):
            lines.append("      状态：实验性，效果不保证")
    return "\n".join(lines)


# --------------------------------------------------------------------------- 决策记录

def decisions_path(cfg: dict[str, Any]) -> Path:
    root = Path(cfg.get("project", {}).get("root") or cfg_mod.ROOT)
    return root / "decisions.jsonl"


def record_decision(cfg: dict[str, Any], symptom: str, chosen: str, candidates: list[str], note: str = "") -> None:
    path = decisions_path(cfg)
    entry = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "symptom": symptom,
        "chosen": chosen,
        "candidates": candidates,
        "note": note,
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def last_choice(cfg: dict[str, Any], symptom: str) -> str | None:
    path = decisions_path(cfg)
    if not path.exists():
        return None
    chosen = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            data = json.loads(line)
        except Exception:
            continue
        if data.get("symptom") == symptom:
            chosen = data.get("chosen")
    return chosen
