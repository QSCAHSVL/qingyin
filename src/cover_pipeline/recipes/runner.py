"""配方执行：针对同一段素材，用不同配方各生成一版，放到 5-对比/ 供试听。

为了快，默认只处理歌曲前 N 秒（默认 60 秒），够听出接缝和爆音的区别。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..core import convert, mix
from ..utils import ffmpeg, log
from .loader import find_recipe

DEFAULT_SECONDS = 60.0


def compare(
    song_dir: Path,
    cfg: dict[str, Any],
    symptom_id: str,
    recipe_ids: list[str] | None = None,
    *,
    seconds: float = DEFAULT_SECONDS,
    progress: Callable[[float, str], None] | None = None,
) -> dict[str, Any]:
    """对指定症状跑一组配方，产出对比音频。"""
    symptom = find_recipe(symptom_id)
    if not symptom:
        raise RuntimeError(f"没有这个症状的配方：{symptom_id}")

    recipes = symptom.get("recipes") or []
    if recipe_ids:
        recipes = [r for r in recipes if str(r.get("id")) in recipe_ids]
    if not recipes:
        raise RuntimeError("没有可执行的配方")

    vocal = _find(song_dir / "2-人声", ("vocal.wav", "人声.wav"))
    backing = _find(song_dir / "2-人声", ("instrumental.wav", "伴奏.wav"))
    if not vocal:
        raise RuntimeError(f"没找到人声轨，先跑一次 cover sing：{song_dir / '2-人声'}")

    out_dir = song_dir / "5-对比"
    out_dir.mkdir(parents=True, exist_ok=True)
    clip_vocal = out_dir / "_clip_vocal.wav"
    clip_backing = out_dir / "_clip_backing.wav"

    duration = min(seconds, ffmpeg.duration(vocal))
    ffmpeg.slice_audio(vocal, clip_vocal, 0.0, duration)
    if backing and backing.exists():
        ffmpeg.slice_audio(backing, clip_backing, 0.0, duration)

    results: list[dict[str, Any]] = []
    for index, recipe in enumerate(recipes, start=1):
        rid = str(recipe.get("id"))
        label = str(recipe.get("name") or rid)
        if progress:
            progress((index - 1) / len(recipes), f"正在生成：{label}")
        log.step(f"配方 {rid}（{label}）")

        local_cfg = _apply_recipe(cfg, recipe)
        target = out_dir / f"{rid}.wav"
        converted = out_dir / f"_{rid}_converted.wav"
        convert.convert(clip_vocal, converted, local_cfg)
        mixed = out_dir / f"_{rid}_mixed.wav"
        mix.mix(converted, clip_backing if clip_backing.exists() else None, mixed, local_cfg)
        ffmpeg.to_wav(mixed, target, channels=2)
        converted.unlink(missing_ok=True)
        mixed.unlink(missing_ok=True)

        results.append(
            {
                "id": rid,
                "name": label,
                "path": str(target),
                "how": recipe.get("how", ""),
                "cost": recipe.get("cost", ""),
                "risk": recipe.get("risk", ""),
                "evidence": recipe.get("evidence", ""),
                "experimental": bool(recipe.get("experimental")),
                "recommended": rid == str(symptom.get("selected")),
            }
        )
        log.done(f"{label} → {target.name}")

    clip_vocal.unlink(missing_ok=True)
    clip_backing.unlink(missing_ok=True)
    if progress:
        progress(1.0, "对比生成完成")

    return {
        "symptom": symptom_id,
        "symptom_text": symptom.get("symptom", ""),
        "seconds": duration,
        "outputs": results,
        "recommended": str(symptom.get("selected") or ""),
    }


def _apply_recipe(cfg: dict[str, Any], recipe: dict[str, Any]) -> dict[str, Any]:
    """把配方参数覆盖到配置上（不改原对象）。

    支持两种写法：
      params: { protect: 0.66 }                  → 当成 convert 参数（老写法）
      params: { convert: {...}, mix: {...} }     → 按段覆盖
    """
    params = recipe.get("params") or {}
    local = {**cfg}
    sections = {"convert", "mix", "separate", "clip"}
    if any(key in sections for key in params):
        for section, values in params.items():
            if section in sections and isinstance(values, dict):
                local[section] = {**cfg.get(section, {}), **values}
        return local

    local["convert"] = {**cfg.get("convert", {}), **params}
    return local


def _find(directory: Path, names: tuple[str, ...]) -> Path | None:
    for name in names:
        path = directory / name
        if path.exists():
            return path
    return None
