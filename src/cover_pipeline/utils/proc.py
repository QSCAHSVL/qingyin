"""可取消的子进程执行。

两个坑都要防：
1. 子进程输出（tqdm 进度条之类）写满管道缓冲会把子进程卡死 —— 用临时文件接输出；
2. 有的程序会静默卡住 —— 盯着输出文件，长时间没动静就杀掉报错。
"""

from __future__ import annotations

import subprocess
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path

IDLE_TIMEOUT = 300.0  # 秒：这么久没有任何输出就认为卡住了


class Cancelled(RuntimeError):
    """任务被用户取消。"""


def run(
    cmd: Sequence[str],
    *,
    cwd: str | Path | None = None,
    env: dict | None = None,
    timeout: float | None = None,
    cancel_event=None,
    capture: bool = True,
    idle_timeout: float | None = IDLE_TIMEOUT,
) -> tuple[str, str]:
    """跑一个子进程，返回 (stdout, stderr)。被取消时抛 Cancelled。"""
    if not capture:
        proc = subprocess.Popen(
            list(cmd), cwd=str(cwd) if cwd else None, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        _wait(proc, timeout, cancel_event, None, idle_timeout)
        return "", ""

    with tempfile.TemporaryFile(mode="w+b") as out_f, tempfile.TemporaryFile(mode="w+b") as err_f:
        proc = subprocess.Popen(
            list(cmd), cwd=str(cwd) if cwd else None, env=env,
            stdout=out_f, stderr=err_f, stdin=subprocess.DEVNULL,
        )
        _wait(proc, timeout, cancel_event, (out_f, err_f), idle_timeout)
        out_f.seek(0)
        err_f.seek(0)
        out = out_f.read().decode("utf-8", "replace")
        err = err_f.read().decode("utf-8", "replace")

    if proc.returncode != 0:
        raise RuntimeError(f"命令失败（{proc.returncode}）：{(err or out or '')[-1500:]}")
    return out, err


def _wait(proc, timeout, cancel_event, files, idle_timeout) -> None:
    started = time.time()
    last_size = 0
    last_change = time.time()
    try:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                _terminate(proc)
                raise Cancelled("任务已取消")
            if proc.poll() is not None:
                return
            now = time.time()
            if timeout and now - started > timeout:
                _terminate(proc)
                raise TimeoutError(f"命令超时（{timeout:.0f}s）")
            if files:
                size = sum(f.tell() for f in files)
                if size != last_size:
                    last_size = size
                    last_change = now
                elif idle_timeout and now - last_change > idle_timeout:
                    _terminate(proc)
                    raise RuntimeError(f"命令 {idle_timeout:.0f}s 没有任何输出，疑似卡住，已结束")
            time.sleep(0.3)
    finally:
        if proc.poll() is None:
            _terminate(proc)


def _terminate(proc: subprocess.Popen) -> None:
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
