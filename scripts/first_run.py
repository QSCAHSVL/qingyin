"""首次运行：按安装时选的依赖档位装依赖，然后认一下本机已有的 RVC/UVR。

安装包会写一个 deps.ini，内容形如：
    [deps]
    separate=0
    convert=0

用法：
    python scripts/first_run.py [--yes]
"""

from __future__ import annotations

import configparser
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPS_INI = ROOT / "deps.ini"
VENV = ROOT / ".venv"
MARKER = ROOT / ".first-run-done"


def log(text: str) -> None:
    print(text, flush=True)


def read_tier() -> dict[str, bool]:
    conf = configparser.ConfigParser()
    conf.read(DEPS_INI, encoding="utf-8")
    if "deps" not in conf:
        return {"separate": False, "convert": False}
    section = conf["deps"]
    return {
        "separate": section.getboolean("separate", False),
        "convert": section.getboolean("convert", False),
    }


def find_python() -> Path:
    if VENV.exists():
        exe = VENV / "Scripts" / "python.exe"
        if exe.exists():
            return exe
    return Path(sys.executable)


def ensure_venv() -> Path:
    if VENV.exists() and (VENV / "Scripts" / "python.exe").exists():
        return VENV / "Scripts" / "python.exe"
    log("[1/3] 创建独立环境 .venv（以后不会污染系统 Python）")
    subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
    return VENV / "Scripts" / "python.exe"


def pip(python: Path, *args: str) -> None:
    cmd = [str(python), "-m", "pip", "install", "--disable-pip-version-check", *args]
    log("  > " + " ".join(args))
    subprocess.run(cmd, check=False)


def install(python: Path, tier: dict[str, bool]) -> None:
    log("[2/3] 安装依赖")
    pip(python, "--upgrade", "pip")
    pip(python, "pyyaml")

    if tier["separate"]:
        log("  · 人声分离：audio-separator（会顺带装 torch，几百 MB 到 1G+）")
        result = subprocess.run(
            [str(python), "-m", "pip", "install", "--disable-pip-version-check", "audio-separator[gpu]"],
            check=False,
        )
        if result.returncode != 0:
            log("    GPU 版失败，改用 CPU 版")
            pip(python, "audio-separator[cpu]")
    else:
        log("  · 人声分离：跳过（用本机已有的 UVR）")

    if tier["convert"]:
        log("  · 音色转换：torch(CUDA) + rvc-python（4~6GB，慢）")
        pip(python, "torch", "torchaudio", "--index-url", "https://download.pytorch.org/whl/cu121")
        pip(python, "rvc-python")
    else:
        log("  · 音色转换：跳过（用本机已有的 RVC）")


def link(python: Path) -> None:
    log("[3/3] 认一下本机已有的 RVC / UVR")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["PYTHONIOENCODING"] = "utf-8"
    subprocess.run(
        [str(python), "-m", "cover_pipeline.cli", "link", "--auto"],
        cwd=str(ROOT), env=env, check=False,
    )
    subprocess.run(
        [str(python), "-m", "cover_pipeline.cli", "doctor"],
        cwd=str(ROOT), env=env, check=False,
    )


def main() -> int:
    tier = read_tier()
    log("=" * 52)
    log("cover-pipeline 首次设置")
    log(f"  人声分离依赖：{'装' if tier['separate'] else '跳过（用本地 UVR）'}")
    log(f"  音色转换依赖：{'装' if tier['convert'] else '跳过（用本地 RVC）'}")
    log("=" * 52)

    python = ensure_venv()
    install(python, tier)
    link(python)

    MARKER.write_text("done\n", encoding="utf-8")
    log("")
    log("好了。以后双击「启动.bat」就能用。")
    log("想改依赖档位：编辑 deps.ini 后重新跑一次本脚本。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())