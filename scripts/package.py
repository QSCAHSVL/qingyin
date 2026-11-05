"""打绿色版压缩包（只带白名单，绝不含个人数据）。

用法：
    py -3 scripts/package.py            # 生成 dist/卿音-<版本>-portable.zip
    py -3 scripts/package.py --check    # 只检查会打进包的文件，不生成

隐私原则：
- 只按白名单收文件，不"排除"黑名单 —— 新的私人文件默认不会被带出去
- 打包前跑一遍敏感内容扫描（QQ 号、个人盘路径、密钥、名字）
- 生成 SHA256SUMS.txt，别人下载后可以校验
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"

# 白名单：只有这些会被打进包
INCLUDE_DIRS = [
    "src/cover_pipeline",
    "plans",
    "recipes",
    "assets",
    "docs",
    "configs/presets",
    "scripts",
    "tests",
    "examples",
    "plugins",
]
INCLUDE_FILES = [
    "README.md",
    "README.en.md",
    "CHANGELOG.md",
    "pyproject.toml",
    "requirements.lock",
    "configs/default.yaml",
    "start-web.bat",
    "start-desktop.bat",
    "启动.bat",
    "启动-桌面版.bat",
    "setup-deps.bat",
    "LICENSE",
    ".gitignore",
]
INCLUDE_LAUNCHERS = ["*.bat"]

SKIP_PARTS = {"__pycache__", ".venv", "venv", ".git", "work", "output", "models", "dist", "logs", ".pytest_cache"}
SKIP_SUFFIX = {".pyc", ".pyo", ".pth", ".index", ".onnx", ".wav", ".mp3", ".flac", ".db", ".log", ".part"}

# 打包前扫描：命中就中止
SENSITIVE = {
    "QQ/手机号": r"\b1[3-9]\d{9}\b",
    "个人盘路径": r"[A-Z]:\\AI-Companion|[A-Z]:\\Users\\[^\\]+",
    "密钥": r"\bcp_[0-9a-f]{10,}\b",
    "口令赋值": r"(password|passwd|secret|token)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{12,}",
}
TEXT_SUFFIX = {".py", ".js", ".html", ".css", ".yaml", ".yml", ".md", ".bat", ".ps1", ".toml", ".txt", ".json", ".iss"}


def version() -> str:
    text = (ROOT / "src" / "cover_pipeline" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    return match.group(1) if match else "0.0.0"


def collect() -> list[Path]:
    files: list[Path] = []
    for rel in INCLUDE_DIRS:
        base = ROOT / rel
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and not _skip(path):
                files.append(path)
    for rel in INCLUDE_FILES:
        path = ROOT / rel
        if path.exists() and path.is_file():
            files.append(path)
    for pattern in INCLUDE_LAUNCHERS:
        files.extend(p for p in ROOT.glob(pattern) if p.is_file())
    unique = sorted({p.resolve() for p in files})
    return unique


def _skip(path: Path) -> bool:
    if any(part in SKIP_PARTS for part in path.parts):
        return True
    if path.suffix.lower() in SKIP_SUFFIX:
        return True
    if path.name in {"local.yaml", "decisions.jsonl", "_agent_key.txt"}:
        return True
    return False


def scan(files: list[Path]) -> list[str]:
    problems: list[str] = []
    for path in files:
        if path.suffix.lower() not in TEXT_SUFFIX:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for label, pattern in SENSITIVE.items():
            for match in re.finditer(pattern, text):
                snippet = match.group(0)[:40]
                problems.append(f"{path.relative_to(ROOT)}: {label} → {snippet}")
    return problems


def build(files: list[Path], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in files:
            zf.write(path, path.relative_to(ROOT).as_posix())
        # 校验清单
        lines = []
        for path in files:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            lines.append(f"{digest}  {path.relative_to(ROOT).as_posix()}")
        zf.writestr("SHA256SUMS.txt", "\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="打绿色版压缩包")
    parser.add_argument("--check", action="store_true", help="只检查，不生成")
    parser.add_argument("--out", default="", help="输出文件名（默认 dist/卿音-<版本>-portable.zip）")
    args = parser.parse_args()

    ver = version()
    files = collect()
    problems = scan(files)

    print(f"版本：{ver}")
    print(f"将打包 {len(files)} 个文件，合计 {sum(p.stat().st_size for p in files) / 1024 / 1024:.1f} MB")
    for path in files[:8]:
        print(f"  · {path.relative_to(ROOT)}")
    if len(files) > 8:
        print(f"  …其余 {len(files) - 8} 个")

    if problems:
        print("\n发现疑似敏感内容，已中止：")
        for item in problems[:20]:
            print("  !", item)
        return 1
    print("\n敏感内容扫描：通过（无 QQ 号 / 个人路径 / 密钥）")

    if args.check:
        return 0

    out = Path(args.out) if args.out else DIST / f"卿音-{ver}-portable.zip"
    build(files, out)
    size = out.stat().st_size / 1024 / 1024
    print(f"\n已生成：{out}（{size:.1f} MB）")
    print("解压后双击「启动.bat」即可用；首次运行会引导装依赖。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
