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


def _assert_ruff_target_ok(pyproject_text: str) -> None:
    """pyproject 里的 [tool.ruff] target-version 必须是 py310 这种，不能被版本号顶掉。"""
    match = re.search(r'(?m)^target-version = "([^"]+)"$', pyproject_text)
    if match and not re.fullmatch(r"py3\d{1,2}", match.group(1)):
        raise SystemExit(
            "pyproject 的 [tool.ruff] target-version 不合法：%r（应该是 py310）。"
            "历史上版本号同步脚本误改过它，先修好再同步。" % match.group(1)
        )


def sync(check_only: bool = False) -> int:
    version = current_version()
    changed: list[str] = []

    pyproject = ROOT / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    new = re.sub(r'(?m)^version = ".*"$', f'version = "{version}"', text, count=1)
    # 守卫：以前这条正则没锚行首，把 [tool.ruff] target-version 也改成了 0.x.y，
    # 结果 ruff 直接起不来、而 CI 的 lint 是非阻断，谁都没发现。改动前后都验一遍。
    _assert_ruff_target_ok(new)
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
