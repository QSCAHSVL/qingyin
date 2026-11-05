"""把技术报错翻译成人话：出错时说清「哪一步、什么原因、怎么改」。"""

from __future__ import annotations

import re
from typing import Any

RULES: list[tuple[str, str, str]] = [
    # (正则, 标题, 建议)
    (r"CUDA out of memory|out of memory", "显存不够了", "把方案里的分块时长调小（convert.chunk_seconds）、或先关掉浏览器/游戏；也可以在方案页把「显存预算」调低再重新推荐。"),
    (r"No module named 'audio_separator'", "没装人声分离依赖", "装一下：pip install audio-separator[gpu]；或者用 cover link 指向本机已有的 UVR。"),
    (r"No module named 'rvc_python'", "没装 RVC 推理依赖", "装一下：pip install rvc-python；或者用 cover link 指向本机已有的 RVC。"),
    (r"No module named 'torch'", "缺 PyTorch", "装一下：pip install torch torchaudio（显卡版加 --index-url https://download.pytorch.org/whl/cu121）。"),
    (r"No module named '(demucs|librosa|soundfile)'", "缺音频依赖", "装一下：pip install demucs librosa soundfile。"),
    (r"ffmpeg|ffprobe", "找不到 ffmpeg", "装一下：winget install Gyan.FFmpeg；或者在 configs/local.yaml 的 tools.ffmpeg_dir 填 ffmpeg 的 bin 目录。"),
    (r"没配置搜索目录|给的是歌名", "按歌名找歌需要先配目录", "两种办法：去「找歌」页在线搜一首，或者直接给音频文件的完整路径；也可以在 configs/local.yaml 里设置 source.search_dirs。"),
    (r"没在 .* 里找到音频文件|没找到音频", "这个位置没有音频文件", "确认目录里真的有 mp3/wav/flac；子目录也会扫，但压缩包不会解。"),
    (r"FileNotFoundError|No such file|系统找不到", "路径不对", "检查文件/文件夹是不是真的存在，路径里有没有多余的引号或空格。"),
    (r"PermissionError|拒绝访问|Access is denied", "没有权限", "换个可写的目录，或者用管理员身份跑一次；也可能是文件正被别的程序占用。"),
    (r"HTTP Error 412|Precondition Failed", "被平台拦了", "B 站对频繁请求会限流，等一两分钟再搜；或者直接用链接下载。"),
    (r"HTTP Error 403|403 Forbidden", "访问被拒", "这首歌可能限地区/限会员，换个来源试试。"),
    (r"HTTP Error 404", "找不到资源", "链接失效了，重新搜一次。"),
    (r"文件太小|会员|已下架", "这首歌拿不到完整音频", "平台只给片段或需要会员。换一个来源，或者用自己的文件。"),
    (r"TimeoutError|命令超时", "跑太久超时了", "先看日志最后一行停在哪一步；如果是分离/转换，检查显卡是不是被别的程序占满。"),
    (r"没有任何输出，疑似卡住", "程序卡住了", "已经自动结束。多半是显存/内存不够或模型文件损坏，重启一次再试。"),
    (r"UnicodeEncodeError|codec can't encode", "编码问题", "控制台编码不是 UTF-8，用 启动.bat 启动，或设置 PYTHONIOENCODING=utf-8。"),
    (r"Cancelled|已取消", "任务被取消", "这是你点取消的结果，不是故障。"),
]


def explain(exc: BaseException | str) -> dict[str, Any]:
    """返回 {title, hint, raw}，给界面和命令行共用。"""
    raw = str(exc)
    for pattern, title, hint in RULES:
        if re.search(pattern, raw, re.IGNORECASE):
            return {"title": title, "hint": hint, "raw": raw[-800:]}
    return {"title": "出错了", "hint": "把下面这段日志发给开发者，或者去「任务」页看完整日志。", "raw": raw[-800:]}


def format_short(exc: BaseException | str) -> str:
    info = explain(exc)
    return f"{info['title']}：{info['hint']}"