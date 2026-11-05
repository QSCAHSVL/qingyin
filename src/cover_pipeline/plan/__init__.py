"""方案层：硬件探测 → 问卷 → 方案卡 → 写入配置。"""

from .assets import print_summary as print_assets
from .assets import recommend as recommend_assets
from .assets import render as render_assets
from .engine import Profile, ScoredPlan, load_plans, recommend, render_card
from .writer import apply_plan, current_plan

__all__ = [
    "Profile",
    "ScoredPlan",
    "apply_plan",
    "current_plan",
    "load_plans",
    "print_assets",
    "recommend",
    "recommend_assets",
    "render_assets",
    "render_card",
]
