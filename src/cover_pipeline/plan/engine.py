"""方案引擎：把硬件快照 + 用户偏好，变成 2~3 张可选的方案卡。

设计原则：
- 硬约束先过滤（显存、磁盘、能不能训练），软偏好再打分
- RVC 是默认候选，但参数由方案库决定，不写死在代码里
- 每个方案都带「利 / 弊 / 预计」，让人能自己判断
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .. import config as cfg_mod
from . import stats

PLANS_DIR = cfg_mod.ROOT / "plans"

PREFERENCE_WEIGHTS: dict[str, dict[str, float]] = {
    "quality": {"quality": 3.0, "speed": 0.5, "space": 0.3, "stability": 1.0},
    "speed": {"speed": 3.0, "quality": 1.0, "space": 0.5, "stability": 1.0},
    "space": {"space": 3.0, "quality": 1.0, "speed": 0.5, "stability": 1.0},
    "stability": {"stability": 3.0, "quality": 1.0, "speed": 1.0, "space": 1.0},
}


@dataclass
class Profile:
    """用户问卷结果。"""

    prefer: str = "stability"          # quality / speed / space / stability
    will_train: str = "unsure"         # yes / no / unsure
    disk_budget_gb: float = 30.0
    patience_minutes: float = 10.0     # 单曲能等多久
    frequency: str = "weekly"          # rare / weekly / daily
    allow_advanced: bool = False
    song_count: int = 10               # 预计要唱多少首（算磁盘）
    max_vram_gb: float | None = None   # 显存预算：峰值超过它的方案直接排除

    def as_dict(self) -> dict[str, Any]:
        return {
            "prefer": self.prefer,
            "will_train": self.will_train,
            "disk_budget_gb": self.disk_budget_gb,
            "patience_minutes": self.patience_minutes,
            "frequency": self.frequency,
            "allow_advanced": self.allow_advanced,
            "song_count": self.song_count,
            "max_vram_gb": self.max_vram_gb,
        }


@dataclass
class ScoredPlan:
    plan: dict[str, Any]
    score: float
    recommended: bool = False
    notes: list[str] = field(default_factory=list)
    excluded_reason: str = ""

    @property
    def id(self) -> str:
        return str(self.plan.get("id", "?"))

    @property
    def name(self) -> str:
        return str(self.plan.get("name", self.id))


def load_plans(plans_dir: Path | None = None) -> list[dict[str, Any]]:
    directory = plans_dir or PLANS_DIR
    if not directory.exists():
        return []
    plans: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.yaml")):
        if path.name.startswith(("_", ".")):
            continue  # 模板/草稿不参与推荐
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if isinstance(data, dict) and data.get("id"):
            plans.append(data)
    return plans


def recommend(probe: dict[str, Any], profile: Profile, plans: list[dict[str, Any]] | None = None) -> list[ScoredPlan]:
    """返回排好序的方案，第一条标记为推荐。"""
    plans = plans if plans is not None else load_plans()
    vram = _max_vram(probe)
    has_gpu = vram > 0
    disk_free = float(probe.get("disk", {}).get("free_gb", 0) or 0)
    weights = PREFERENCE_WEIGHTS.get(profile.prefer, PREFERENCE_WEIGHTS["stability"])

    scored: list[ScoredPlan] = []
    for plan in plans:
        reason = _exclude_reason(plan, has_gpu, vram, disk_free, profile)
        if reason:
            scored.append(ScoredPlan(plan=plan, score=-1, excluded_reason=reason))
            continue

        base = sum(float(plan.get("scores", {}).get(key, 3)) * weight for key, weight in weights.items())
        try:
            base = stats.adjust(str(plan.get("id") or ""), base)
        except Exception:
            pass
        notes: list[str] = []

        # 软调整
        estimate = plan.get("estimate", {})
        per_song = float(estimate.get("per_song_minutes", 10) or 10)
        if per_song > profile.patience_minutes:
            base -= 2.0
            notes.append(f"单曲约 {per_song:.0f} 分钟，超过你能等的 {profile.patience_minutes:.0f} 分钟")

        need_disk = float(estimate.get("disk_per_song_mb", 200) or 200) * profile.song_count / 1024
        if need_disk > profile.disk_budget_gb * 0.8:
            base -= 1.5
            notes.append(f"唱 {profile.song_count} 首要占约 {need_disk:.0f}G，接近你给的预算")

        wants_train = str(plan.get("for", {}).get("needs_train", "optional"))
        if profile.will_train == "yes" and wants_train == "optional":
            base += 0.5
            notes.append("这套参数支持自己训练音色")
        if profile.will_train == "unsure" and int(plan.get("params", {}).get("train", {}).get("epochs", 0) or 0) > 0:
            base += 0.3
            notes.append("以后想训练不用换方案")

        if profile.frequency == "daily" and per_song > 6:
            base -= 0.5

        scored.append(ScoredPlan(plan=plan, score=round(base, 2), notes=notes))

    available = sorted([s for s in scored if not s.excluded_reason], key=lambda s: s.score, reverse=True)
    excluded = [s for s in scored if s.excluded_reason]
    if available:
        available[0].recommended = True
    return available[:3] + excluded


def render_card(scored: ScoredPlan, index: int | None = None) -> str:
    plan = scored.plan
    params = plan.get("params", {})
    estimate = plan.get("estimate", {})
    sep = params.get("separate", {})
    conv = params.get("convert", {})
    train = params.get("train", {})

    title = scored.name
    if scored.recommended:
        title = f"★ 推荐｜{title}"
    head = f"{index}. {title}" if index is not None else title

    lines = [head]
    lines.append(
        f"   分离 {sep.get('model', '-')} ｜ 转换 {conv.get('backend', 'rvc').upper()}"
        f"（index {conv.get('index_rate', '-')} / protect {conv.get('protect', '-')}）"
    )
    epochs = int(train.get("epochs", 0) or 0)
    train_text = f"训练 {epochs} 轮约 {estimate.get('train_minutes', 0):.0f} 分钟" if epochs else "不训练（用现成模型）"
    lines.append(f"   {train_text} ｜ 单曲约 {estimate.get('per_song_minutes', '?')} 分钟")
    lines.append(
        f"   显存峰值 {estimate.get('vram_peak_gb', '?')}G ｜ 每首占盘 {estimate.get('disk_per_song_mb', '?')}MB"
    )
    pros = plan.get("pros") or []
    cons = plan.get("cons") or []
    if pros:
        lines.append("   好处：" + "；".join(pros))
    if cons:
        lines.append("   代价：" + "；".join(cons))
    if plan.get("explain"):
        lines.append(f"   说明：{plan['explain']}")
    for note in scored.notes:
        lines.append(f"   · {note}")
    return "\n".join(lines)


def _max_vram(probe: dict[str, Any]) -> float:
    gpus = probe.get("gpu") or []
    if not gpus:
        return 0.0
    return max(float(g.get("vram_gb", 0) or 0) for g in gpus)


def _exclude_reason(
    plan: dict[str, Any], has_gpu: bool, vram: float, disk_free: float, profile: Profile
) -> str:
    rules = plan.get("for", {})
    needs_gpu = rules.get("gpu_required", True)
    if needs_gpu and not has_gpu:
        return "需要独立显卡"
    if not needs_gpu and has_gpu:
        return "你有独显，用不到这套纯 CPU 方案"
    if has_gpu:
        if vram < float(rules.get("min_vram_gb", 0) or 0):
            return f"显存不够（要 {rules.get('min_vram_gb')}G，你是 {vram:.0f}G）"
        if vram > float(rules.get("max_vram_gb", 99) or 99):
            return "显存超出这套方案的目标区间（有更合适的方案）"
    if disk_free and disk_free < float(rules.get("min_disk_gb", 0) or 0):
        return f"磁盘不够（要 {rules.get('min_disk_gb')}G，剩 {disk_free:.0f}G）"
    if plan.get("advanced") and not profile.allow_advanced:
        return "进阶方案，默认不推荐给第一次用的人"
    peak = float(plan.get("estimate", {}).get("vram_peak_gb", 0) or 0)
    if profile.max_vram_gb and peak > profile.max_vram_gb:
        return f"显存预算不够（峰值要 {peak:g}G，你给了 {profile.max_vram_gb:g}G）"
    needs_train = str(rules.get("needs_train", "optional"))
    if needs_train == "yes" and profile.will_train == "no":
        return "这套方案必须自己训练音色"
    if needs_train == "no" and profile.will_train == "yes":
        return "这套方案不支持训练音色"
    return ""

def _blend_numeric(a, b, t):
    """递归把两套方案的数值参数按比例插值；非数值取靠近的一侧。"""
    if isinstance(a, dict) and isinstance(b, dict):
        out = {}
        for key, val in a.items():
            if key in b:
                out[key] = _blend_numeric(val, b[key], t)
            else:
                out[key] = val
        for key in b:
            if key not in out:
                out[key] = b[key]
        return out
    if isinstance(a, bool) or isinstance(b, bool):
        return b if t >= 0.5 else a
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        value = a + (b - a) * t
        if isinstance(a, int) and isinstance(b, int):
            return round(value)
        return round(value, 3)
    return b if t >= 0.5 else a


def fit_to_probe(probe: dict[str, Any], plans: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    """按实际显存把相邻两套方案插值成一台机器专属的方案。

    显存刚好落在某套方案的区间里、且不是边界情况时，返回 None（用现成方案即可）。
    """
    plans = plans if plans is not None else load_plans()
    vram = 0.0
    try:
        vram = float(_max_vram(probe) or 0)
    except Exception:
        gpu = probe.get("gpu")
        if isinstance(gpu, dict):
            vram = float(gpu.get("vram_gb") or 0)
        elif isinstance(gpu, list) and gpu:
            vram = float((gpu[0] or {}).get("vram_gb") or 0)
    if vram <= 0:
        return None
    usable = [p for p in plans if (p.get("for") or {}).get("gpu_required", True)]
    if len(usable) < 2:
        return None
    usable.sort(key=lambda p: float((p.get("for") or {}).get("min_vram_gb") or 0))
    # 显存正好贴着某一档的下沿 → 直接用现成方案，不做插值
    for plan in usable:
        lo = float((plan.get("for") or {}).get("min_vram_gb") or 0)
        if abs(vram - lo) <= 0.6:
            return None
    lower = upper = None
    for plan in usable:
        lo = float((plan.get("for") or {}).get("min_vram_gb") or 0)
        if lo <= vram:
            lower = plan
        elif lower is not None:
            upper = plan
            break
    if lower is None or upper is None:
        return None
    lo = float((lower.get("for") or {}).get("min_vram_gb") or 0)
    hi = float((upper.get("for") or {}).get("min_vram_gb") or 0)
    if hi <= lo:
        return None
    ratio = max(0.0, min(1.0, (vram - lo) / (hi - lo)))
    blended = dict(lower)
    blended["params"] = _blend_numeric(lower.get("params", {}), upper.get("params", {}), ratio)
    blended["scores"] = _blend_numeric(lower.get("scores", {}), upper.get("scores", {}), ratio)
    blended["for"] = dict(lower.get("for") or {})
    blended["for"]["min_vram_gb"] = round(vram, 2)
    blended["for"]["max_vram_gb"] = round(vram, 2)
    blended["id"] = f"fit_{lower.get('id')}__{upper.get('id')}"
    blended["name"] = f"{round(vram, 1)}G 显存 · 插值方案（{lower.get('tier')}G↔{upper.get('tier')}G）"
    blended["tier"] = round(vram, 1)
    blended["generated"] = True
    blended["derived_from"] = [lower.get("id"), upper.get("id")]
    return blended
