"""极简日志：带步骤前缀，方便新手看懂跑到哪一步了。

除了打到控制台，还可以 `enable_file()` 同时落一份到 logs/ 里 ——
以后出问题不用靠记忆复述，翻文件就行。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

_LEVELS = {"debug": 10, "info": 20, "warn": 30, "error": 40}
_current = 20
_t0 = time.time()
_file = None

# 老机器/英文系统上控制台代码页可能是 437，直接 print 中文或符号会崩。
# 这里统一改成 UTF-8 + 容错，崩不了，实在显示不了也只是问号。
for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream and hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def set_level(name: str) -> None:
    global _current
    _current = _LEVELS.get(str(name).lower(), 20)


def enable_file(path: Path, *, append: bool = True) -> Path:
    """把日志同时写一份到文件（控制台照常输出）。"""
    global _file
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _file = path.open("a" if append else "w", encoding="utf-8", errors="replace")
    _emit(" ", f"日志同时写入：{path}", 20)
    return path


def disable_file() -> None:
    global _file
    if _file is not None:
        try:
            _file.close()
        finally:
            _file = None


def _redact(text: str) -> str:
    """把本机用户目录换成 ~，避免日志外传泄露路径。"""
    import os

    home = os.path.expanduser("~")
    if home and home in text:
        text = text.replace(home, "~")
    return text


def _emit(tag: str, message: str, level: int) -> None:
    if level < _current:
        return
    elapsed = time.time() - _t0
    stream = sys.stderr if level >= 30 else sys.stdout
    line = f"[{elapsed:6.1f}s] {tag} {message}"
    print(line, file=stream, flush=True)
    if _file is not None:
        try:
            _file.write(_redact(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {line}\n"))
            _file.flush()
        except Exception:
            pass


def step(message: str) -> None:
    _emit("▶", message, 20)


def info(message: str) -> None:
    _emit(" ", message, 20)


def debug(message: str) -> None:
    _emit("·", message, 10)


def warn(message: str) -> None:
    _emit("!", message, 30)


def error(message: str) -> None:
    _emit("✗", message, 40)


def done(message: str) -> None:
    _emit("✓", message, 20)
