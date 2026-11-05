"""把 __init__.py 的版本号同步到 pyproject.toml 与安装脚本，保证只有一处手改。"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _safe(text: str) -> str:
    """CI 控制台可能是 cp1252，打印中文会炸，这里降级成 ASCII。"""
    try:
        text.encode("utf-8")
        return text
    except Exception:
        return text.encode("ascii", "replace").decode("ascii")


def current_version() -> str:
    text = (ROOT / "src/cover_pipeline/__init__.py").read_text(encoding="utf-8")
    return re.search(r'__version__\s*=\s*"([^"]+)"', text).group(1)


def sync(check_only: bool = False) -> int:
    version = current_version()
    changed: list[str] = []

    pyproject = ROOT / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    new = re.sub(r'(?m)^version = ".*"$', f'version = "{version}"', text, count=1)
    if new != text:
        if not check_only:
            pyproject.write_text(new, encoding="utf-8")
        changed.append("pyproject.toml")

    iss = ROOT / "installer/cover-pipeline.iss"
    if iss.exists():
        text = iss.read_text(encoding="utf-8-sig")
        new = re.sub(r"(?m)^#define AppVersion .*$", f'#define AppVersion "{version}"', text, count=1)
        new = re.sub(r"(?m)^AppVersion=.*$", f"AppVersion={version}", new, count=1)
        if new != text:
            if not check_only:
                iss.write_text(new, encoding="utf-8-sig")
            changed.append("installer/cover-pipeline.iss")

    if check_only:
        if changed:
            print(_safe("版本不一致，需要同步：" + ", ".join(changed)))
            return 1
        print(_safe(f"版本一致：{version}"))
        return 0
    print(_safe(f"版本 {version} 已同步：" + (", ".join(changed) if changed else "无需改动")))
    return 0


if __name__ == "__main__":
    sys.exit(sync(check_only="--check" in sys.argv))
