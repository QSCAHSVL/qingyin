"""在本机弹出原生「选择文件夹」对话框。

为什么放在服务端：浏览器出于安全限制，`<input type=file webkitdirectory>` 只能拿到相对路径，
拿不到绝对路径。而卿音本来就跑在用户自己机器上，服务端可以直接调 Windows 的对话框，
把选中的绝对路径回给页面 —— 体验和桌面软件一致。

实现要点：
- 起一个隐藏的 PowerShell（STA 模式）弹 FolderBrowserDialog
- 给它一个 TopMost 的透明 owner 窗口，否则对话框会跑到浏览器后面，看起来像「没弹出来」
- 结果写进临时文件（避免中文路径在管道里被代码页搞坏）
- 同一时间只允许一个选择框，避免点多次堆一堆窗口
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from . import log

_lock = threading.Lock()

PS_SCRIPT = """
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

# 透明置顶的 owner：让对话框一定出现在最前面，而不是躲在浏览器后面
$owner = New-Object System.Windows.Forms.Form
$owner.TopMost = $true
$owner.ShowInTaskbar = $false
$owner.FormBorderStyle = 'None'
$owner.Size = New-Object System.Drawing.Size(1, 1)
$owner.Opacity = 0
$owner.StartPosition = 'Manual'
$owner.Location = New-Object System.Drawing.Point(-2000, -2000)
$owner.Show()

$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = '{title}'
$dialog.ShowNewFolderButton = $true
{initial}
$result = $dialog.ShowDialog($owner)
$owner.Close()

if ($result -eq [System.Windows.Forms.DialogResult]::OK) {{
    [System.IO.File]::WriteAllText('{out}', $dialog.SelectedPath, [System.Text.Encoding]::UTF8)
}}
"""


def available() -> bool:
    """只有 Windows + 有 PowerShell 才支持。"""
    return shutil.which("powershell") is not None or shutil.which("powershell.exe") is not None


def build_script(title: str, initial: str | None, out_file: Path) -> str:
    """生成 PowerShell 脚本（抽出来是为了能单独做语法检查）。"""
    safe_title = (title or "选择文件夹").replace("'", "''")
    initial_line = ""
    if initial and Path(initial).expanduser().is_dir():
        safe_initial = str(Path(initial).expanduser()).replace("'", "''")
        initial_line = f"$dialog.SelectedPath = '{safe_initial}'"
    return PS_SCRIPT.format(title=safe_title, initial=initial_line, out=str(out_file).replace("'", "''"))


def pick_folder(title: str = "选择文件夹", initial: str | None = None, timeout: float = 180) -> Path | None:
    """弹出对话框，返回选中的目录；用户取消返回 None。"""
    if not available():
        raise RuntimeError("当前系统没有 PowerShell，无法弹出文件夹选择框")
    if not _lock.acquire(blocking=False):
        raise RuntimeError("已经有一个选择框在等你了，先去那边选完或关掉")

    try:
        exe = shutil.which("powershell") or shutil.which("powershell.exe")
        with tempfile.TemporaryDirectory() as tmp:
            out_file = Path(tmp) / "picked.txt"
            script_path = Path(tmp) / "pick.ps1"
            script_path.write_text(build_script(title, initial, out_file), encoding="utf-8-sig")

            log.info("已弹出文件夹选择框，请在桌面上选择…")
            started = time.time()
            try:
                done = subprocess.run(
                    [exe, "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-File", str(script_path)],
                    timeout=timeout,
                    capture_output=True,
                )
            except subprocess.TimeoutExpired as exc:
                raise TimeoutError(f"文件夹选择框 {timeout:.0f} 秒没操作，已自动关闭") from exc

            stderr = (done.stderr or b"").decode("utf-8", "replace").strip()
            if done.returncode != 0:
                tail = stderr[-400:] or "（没有错误输出）"
                raise RuntimeError(f"选择框启动失败（退出码 {done.returncode}）：{tail}")

            if not out_file.exists():
                log.info("用户取消了选择")
                return None
            picked = out_file.read_text(encoding="utf-8").strip()
            if not picked:
                return None
            log.done(f"已选择：{picked}（用时 {time.time() - started:.1f}s）")
            return Path(picked)
    finally:
        _lock.release()
