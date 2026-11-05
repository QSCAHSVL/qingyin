#!/usr/bin/env python3
"""前端静态检查（第 7 轮：app.js 拆成 pages/*.js 之后，`node --check static/*.js` 不够用了）。

三件事：
  1. 语法：把 static 下的 .js 全拷进一个带 package.json(type=module) 的临时目录再 node --check，
     否则 Node 会把 ESM 当 CommonJS 解析，import 直接判语法错。
  2. 引用：每个 `import { a, b } from "./x.js"` 的相对路径必须存在。
  3. 导出：import 进来的名字必须在目标模块里真的 export 了（漏写 export 是最常见的拆包事故）。

用法：
  python scripts/check_frontend.py            # 全部检查，有问题返回 1
  python scripts/check_frontend.py --syntax   # 只查语法（CI 里当阻断步骤）
  python scripts/check_frontend.py --static   # 只查引用/导出（CI 里可以先非阻断）
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "cover_pipeline" / "server" / "static"

IMPORT_RE = re.compile(r'import\s*\{([^}]*)\}\s*from\s*"([^"]+)"')
EXPORT_DECL_RE = re.compile(r'^\s*export\s+(?:async\s+)?(?:function|class|const|let|var)\s+([A-Za-z_$][\w$]*)', re.M)
EXPORT_LIST_RE = re.compile(r'^\s*export\s*\{([^}]*)\}', re.M)


def _rel(path: Path) -> str:
    """相对仓库路径；不在仓库里（比如检查临时副本）就返回绝对路径。"""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def js_files() -> list[Path]:
    return sorted(p for p in STATIC.rglob("*.js") if p.is_file())


def check_syntax(files: list[Path]) -> list[str]:
    problems: list[str] = []
    node = shutil.which("node")
    if not node:
        return ["找不到 node，跳过语法检查（CI 的 windows-latest 自带）"]
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        (tmpdir / "package.json").write_text('{"type":"module"}', encoding="utf-8")
        for i, f in enumerate(files):
            target = tmpdir / ("%03d_%s" % (i, f.name))
            shutil.copyfile(f, target)
            res = subprocess.run([node, "--check", str(target)], capture_output=True, text=True)
            if res.returncode != 0:
                detail = (res.stderr or res.stdout).strip().splitlines()[:4]
                problems.append("%s: %s" % (_rel(f), " / ".join(detail)))
    return problems


def _exports_of(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    names = set(EXPORT_DECL_RE.findall(text))
    for block in EXPORT_LIST_RE.findall(text):
        for part in block.split(","):
            name = part.split(" as ")[-1].strip()
            if name:
                names.add(name)
    return names


def check_imports(files: list[Path]) -> list[str]:
    problems: list[str] = []
    cache: dict[Path, set[str]] = {}
    for f in files:
        text = f.read_text(encoding="utf-8")
        for names_blob, spec in IMPORT_RE.findall(text):
            if not spec.startswith("."):
                continue
            target = (f.parent / spec).resolve()
            if not target.exists():
                problems.append("%s: import 的 %s 不存在" % (_rel(f), spec))
                continue
            if target not in cache:
                cache[target] = _exports_of(target)
            exported = cache[target]
            for raw in names_blob.split(","):
                name = raw.split(" as ")[0].strip()
                if not name:
                    continue
                if name not in exported:
                    problems.append(
                        "%s: 从 %s 导入了 %s，但目标模块没 export 它" % (_rel(f), spec, name)
                    )
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="前端静态检查（语法 / 引用 / 导出）")
    ap.add_argument("--syntax", action="store_true", help="只查语法")
    ap.add_argument("--static", action="store_true", help="只查 import 路径与导出名")
    args = ap.parse_args(argv)
    only_syntax = args.syntax and not args.static
    only_static = args.static and not args.syntax

    files = js_files()
    if not files:
        print("没找到前端 .js，检查路径：%s" % STATIC)
        return 1

    problems: list[str] = []
    if not only_static:
        syntax_problems = check_syntax(files)
        print("[语法] %d 个文件，%d 个问题" % (len(files), len(syntax_problems)))
        problems += syntax_problems
    if not only_syntax:
        import_problems = check_imports(files)
        print("[引用/导出] %d 个问题" % len(import_problems))
        problems += import_problems

    for p in problems:
        print("  - " + p)
    if problems:
        print("\n失败：%d 个问题" % len(problems))
        return 1
    print("前端静态检查通过（%d 个文件）" % len(files))
    return 0


if __name__ == "__main__":
    sys.exit(main())
