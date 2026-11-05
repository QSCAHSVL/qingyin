"""音色模型版本管理：训练出来的每一版权重都留档，可以随时切回旧的。

目录结构：
    models/
      <音色名>/
        versions/
          v1/  <音色名>.pth  meta.json
          v2/  ...
      active.json        当前各音色用的是哪一版

为什么不用「覆盖同名文件」：训练一次要几十分钟，训练翻车是常事，
没有回滚就只能重训。版本化之后切回去是一瞬间的事。
"""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from pathlib import Path
from typing import Any


def _models_dir(cfg: dict) -> Path:
    return Path(cfg.get("project", {}).get("models_dir") or "./models")


def _active_file(cfg: dict) -> Path:
    return _models_dir(cfg) / "active.json"


def _load_active(cfg: dict) -> dict[str, str]:
    path = _active_file(cfg)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_active(cfg: dict, data: dict[str, str]) -> None:
    path = _active_file(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]


def register(cfg: dict, voice: str, source: Path, meta: dict[str, Any] | None = None, *, activate: bool = True) -> dict[str, Any]:
    """把一个 .pth 登记成新版本。返回版本信息。"""
    source = Path(source)
    if not source.exists():
        raise FileNotFoundError(source)
    voice = (voice or "default").strip()
    root = _models_dir(cfg) / voice / "versions"
    root.mkdir(parents=True, exist_ok=True)

    existing = sorted(p.name for p in root.iterdir() if p.is_dir() and p.name.startswith("v"))
    index = len(existing) + 1
    version = f"v{index}"
    target_dir = root / version
    while target_dir.exists():
        index += 1
        version = f"v{index}"
        target_dir = root / version
    target_dir.mkdir(parents=True)

    dest = target_dir / f"{voice}.pth"
    shutil.copy2(source, dest)
    info = {
        "voice": voice,
        "version": version,
        "file": dest.name,
        "sha256": _sha256(dest),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "size_mb": round(dest.stat().st_size / 1024 / 1024, 1),
        **(meta or {}),
    }
    (target_dir / "meta.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    if activate:
        activate_version(cfg, voice, version)
    return info


def list_models(cfg: dict) -> list[dict[str, Any]]:
    base = _models_dir(cfg)
    if not base.exists():
        return []
    active = _load_active(cfg)
    out: list[dict[str, Any]] = []
    for voice_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        versions_dir = voice_dir / "versions"
        if not versions_dir.exists():
            continue
        versions = []
        for ver_dir in sorted(versions_dir.iterdir()):
            meta_path = ver_dir / "meta.json"
            meta: dict[str, Any] = {}
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except Exception:
                    meta = {}
            pth = ver_dir / f"{voice_dir.name}.pth"
            versions.append(
                {
                    "version": ver_dir.name,
                    "path": str(pth) if pth.exists() else "",
                    "active": active.get(voice_dir.name) == ver_dir.name,
                    **{k: v for k, v in meta.items() if k not in ("voice", "version")},
                }
            )
        out.append({"voice": voice_dir.name, "active": active.get(voice_dir.name, ""), "versions": versions})
    return out


def activate_version(cfg: dict, voice: str, version: str) -> dict[str, Any]:
    root = _models_dir(cfg) / voice / "versions" / version
    pth = root / f"{voice}.pth"
    if not pth.exists():
        raise FileNotFoundError(pth)
    active = _load_active(cfg)
    active[voice] = version
    _save_active(cfg, active)
    return {"voice": voice, "version": version, "path": str(pth)}


def active_model_path(cfg: dict, voice: str | None = None) -> Path | None:
    models = list_models(cfg)
    if not models:
        return None
    if voice:
        for item in models:
            if item["voice"] == voice:
                for ver in item["versions"]:
                    if ver["active"] and ver["path"]:
                        return Path(ver["path"])
        return None
    # 没指定音色：优先取有 active 的，否则第一个音色的最新版
    for item in models:
        if item["active"]:
            for ver in item["versions"]:
                if ver["active"] and ver["path"]:
                    return Path(ver["path"])
    first = models[0]
    for ver in reversed(first["versions"]):
        if ver["path"]:
            return Path(ver["path"])
    return None


def delete_version(cfg: dict, voice: str, version: str) -> bool:
    root = _models_dir(cfg) / voice / "versions" / version
    if not root.exists():
        return False
    active = _load_active(cfg)
    if active.get(voice) == version:
        raise RuntimeError("这是当前在用的版本，先切到别的版本再删")
    shutil.rmtree(root)
    return True
