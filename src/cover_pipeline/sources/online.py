"""在线找歌：搜索 + 下载。

来源分两类：
- 能直接下音频的：bilibili（yt-dlp）、iTunes（30 秒试听）
- 只能给元数据的：网易云、QQ 音乐（版权保护，本项目不做解密，只帮你确认是哪首）

抖音：关键词搜索需要签名，这里不做；但把抖音分享链接贴进来可以用 yt-dlp 试下。
用户想接别的平台，写个 plugins/providers/search_*.py 注册进 SEARCH_PROVIDERS 即可。
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

from ..utils import log

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "Referer": "https://www.bilibili.com/", "Accept": "application/json"}
_TAG = re.compile(r"<[^>]+>")

# 平台登记表：插件可以往里加自己的
SEARCH_PROVIDERS: dict[str, dict[str, Any]] = {
    "bilibili": {"label": "B站", "playable": True, "note": "可直接下载音轨"},
    "itunes": {"label": "iTunes", "playable": True, "note": "30 秒试听片段"},
    "netease": {"label": "网易云", "playable": True, "note": "标准音质 mp3 可直接下；高音质要接解密服务"},
    "qqmusic": {"label": "QQ音乐", "playable": True, "note": "标准音质 m4a 可直接下；高音质要接解密服务"},
}

# 音质档位
QUALITIES = {
    "standard": {"label": "标准（mp3/m4a，免解密）", "needs_plugin": False},
    "high": {"label": "高音质（需接入解密服务）", "needs_plugin": True},
}


def providers() -> list[dict[str, Any]]:
    return [{"id": key, **value} for key, value in SEARCH_PROVIDERS.items()]


def search(query: str, limit: int = 12, sources: list[str] | None = None) -> list[dict[str, Any]]:
    """多平台一起搜，按来源分组交替返回，避免某一平台刷屏。"""
    query = (query or "").strip()
    if not query:
        return []
    wanted = sources or ["bilibili", "netease", "qqmusic", "itunes"]
    per_source: dict[str, list[dict[str, Any]]] = {}
    errors: list[str] = []

    fns = {
        "bilibili": _search_bilibili,
        "itunes": _search_itunes,
        "netease": _search_netease,
        "qqmusic": _search_qqmusic,
    }
    for name in wanted:
        fn = fns.get(name)
        if not fn:
            continue
        try:
            per_source[name] = fn(query, limit)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: {exc}")

    merged: list[dict[str, Any]] = []
    index = 0
    while len(merged) < limit:
        added = False
        for name in wanted:
            items = per_source.get(name) or []
            if index < len(items):
                merged.append(items[index])
                added = True
                if len(merged) >= limit:
                    break
        if not added:
            break
        index += 1

    if errors and not merged:
        log.warn("在线搜索没成功：" + "；".join(errors))
    return merged


def download(
    item: dict[str, Any],
    dest_dir: Path,
    on_progress: Callable[[str], None] | None = None,
    ffmpeg_dir: str | None = None,
    cancel_event=None,
    quality: str = "standard",
) -> Path:
    """把搜索结果下成音频文件，返回本地路径。"""
    url = str(item.get("url") or "")
    if not url:
        raise ValueError("这条结果没有可下载的地址")
    if not item.get("playable", True):
        raise RuntimeError("这个平台只提供信息，不能直接下载。请用自己的音频文件，或在支持下载的平台里找同一首。")

    quality = str(item.get("quality") or quality or "standard")
    if quality == "high":
        from ..providers import get_decrypt

        provider = get_decrypt()
        if provider is None:
            raise RuntimeError(
                "高音质需要先接一个解密服务（本项目不提供）。\n"
                "写法：在 plugins/providers/decrypt_xxx.py 里注册 DecryptProvider，"
                "实现 fetch(track) 返回音频路径；然后在 configs/local.yaml 里设 providers.decrypt: xxx"
            )
        return provider.fetch(item, dest_dir)

    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    source = item.get("source")
    if source == "itunes":
        return _download_direct(url, dest_dir, str(item.get("title") or "preview"))
    if source == "netease":
        return _download_netease(item, dest_dir, on_progress)
    if source == "qqmusic":
        return _download_qqmusic(item, dest_dir, on_progress)
    return _download_ytdlp(url, dest_dir, on_progress, ffmpeg_dir, cancel_event)


# --------------------------------------------------------------------------- 各平台搜索

def _search_bilibili(query: str, limit: int) -> list[dict[str, Any]]:
    url = "https://api.bilibili.com/x/web-interface/search/all/v2?keyword=" + urllib.parse.quote(query)
    data = _get_json(url)
    if data.get("code") != 0:
        raise RuntimeError(f"接口返回 code={data.get('code')} {data.get('message')}")
    out: list[dict[str, Any]] = []
    for block in (data.get("data") or {}).get("result") or []:
        if block.get("result_type") != "video":
            continue
        for item in block.get("data") or []:
            bvid = item.get("bvid") or ""
            if not bvid:
                continue
            out.append(
                {
                    "source": "bilibili",
                    "id": bvid,
                    "title": _clean(item.get("title")),
                    "author": _clean(item.get("author")),
                    "duration": _duration_text(item.get("duration")),
                    "url": f"https://www.bilibili.com/video/{bvid}",
                    "play": int(item.get("play") or 0),
                    "playable": True,
                }
            )
            if len(out) >= limit:
                return out
    return out


def _search_itunes(query: str, limit: int) -> list[dict[str, Any]]:
    url = (
        "https://itunes.apple.com/search?media=music&entity=song&limit="
        f"{max(1, min(limit, 20))}&term=" + urllib.parse.quote(query)
    )
    data = _get_json(url, headers={"User-Agent": UA})
    out: list[dict[str, Any]] = []
    for item in data.get("results") or []:
        preview = item.get("previewUrl")
        if not preview:
            continue
        ms = int(item.get("trackTimeMillis") or 30000)
        out.append(
            {
                "source": "itunes",
                "id": str(item.get("trackId") or ""),
                "title": f"{item.get('trackName') or ''} - {item.get('artistName') or ''}".strip(" -"),
                "author": item.get("artistName") or "",
                "duration": f"{ms // 60000}:{(ms // 1000) % 60:02d}",
                "url": preview,
                "playable": True,
            }
        )
    return out


def _search_netease(query: str, limit: int) -> list[dict[str, Any]]:
    url = (
        "https://music.163.com/api/search/get/web?s="
        + urllib.parse.quote(query)
        + f"&type=1&limit={max(1, min(limit, 30))}&offset=0"
    )
    data = _get_json(url, headers={"User-Agent": UA, "Referer": "https://music.163.com/", "Cookie": "appver=2.0.2"})
    songs = (data.get("result") or {}).get("songs") or []
    out: list[dict[str, Any]] = []
    for song in songs:
        song_id = song.get("id")
        if not song_id:
            continue
        artists = ",".join(a.get("name", "") for a in (song.get("artists") or []))
        ms = int(song.get("duration") or 0)
        out.append(
            {
                "source": "netease",
                "id": str(song_id),
                "title": _clean(song.get("name")),
                "author": artists,
                "duration": f"{ms // 60000}:{(ms // 1000) % 60:02d}" if ms else "--:--",
                "url": f"https://music.163.com/#/song?id={song_id}",
                "playable": True,
                "quality": "standard",
                "note": "网易云只给信息，版权音频要你自己准备",
            }
        )
    return out


def _search_qqmusic(query: str, limit: int) -> list[dict[str, Any]]:
    url = (
        "https://c.y.qq.com/soso/fcgi-bin/client_search_cp?w="
        + urllib.parse.quote(query)
        + f"&format=json&n={max(1, min(limit, 30))}&p=1&cr=1&new_json=1"
    )
    data = _get_json(url, headers={"User-Agent": UA, "Referer": "https://y.qq.com/"})
    songs = ((data.get("data") or {}).get("song") or {}).get("list") or []
    out: list[dict[str, Any]] = []
    for song in songs:
        mid = song.get("mid") or (song.get("file") or {}).get("media_mid")
        if not mid:
            continue
        singers = ",".join(s.get("name", "") for s in (song.get("singer") or []))
        secs = int(song.get("interval") or 0)
        out.append(
            {
                "source": "qqmusic",
                "id": str(mid),
                "title": _clean(song.get("name") or song.get("title")),
                "author": singers,
                "duration": f"{secs // 60}:{secs % 60:02d}" if secs else "--:--",
                "url": f"https://y.qq.com/n/ryqq/songDetail/{mid}",
                "playable": True,
                "quality": "standard",
                "note": "QQ音乐只给信息，版权音频要你自己准备",
            }
        )
    return out


# --------------------------------------------------------------------------- 下载

def _download_ytdlp(
    url: str,
    dest_dir: Path,
    on_progress: Callable[[str], None] | None,
    ffmpeg_dir: str | None = None,
    cancel_event=None,
) -> Path:
    import os
    import sys

    from ..utils import proc as proc_util

    out_tpl = str(dest_dir / "%(title)s.%(ext)s")
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--no-warnings", "--no-playlist",
        "-f", "bestaudio/best",
        "-x", "--audio-format", "wav",
        "--audio-quality", "0",
        "-o", out_tpl,
        "--print", "after_move:filepath",
    ]
    env = dict(os.environ)
    if ffmpeg_dir:
        cmd += ["--ffmpeg-location", str(ffmpeg_dir)]
        env["PATH"] = str(ffmpeg_dir) + os.pathsep + env.get("PATH", "")
    cmd.append(url)

    log.step("下载中（yt-dlp）")
    if on_progress:
        on_progress("正在下载音频…")
    out, err = proc_util.run(cmd, env=env, cancel_event=cancel_event)
    lines = [line.strip() for line in (out or "").splitlines() if line.strip()]
    candidates = [Path(line) for line in lines if Path(line).suffix.lower() in (".wav", ".m4a", ".webm", ".opus", ".mp3")]
    for path in reversed(candidates):
        if path.exists():
            if on_progress:
                on_progress(f"下载完成：{path.name}")
            log.done(f"下载完成：{path.name}")
            return path
    raise RuntimeError("下载完了但没找到输出文件（可能被 yt-dlp 改了格式）")


def _download_direct(url: str, dest_dir: Path, name: str) -> Path:
    safe = re.sub(r'[\\/:*?"<>|]+', "_", name)[:60] or "preview"
    target = dest_dir / f"{safe}.m4a"
    log.step("下载试听片段")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp, target.open("wb") as fh:
        fh.write(resp.read())
    log.done(f"下载完成：{target.name}")
    return target


# --------------------------------------------------------------------------- 工具

def _get_json(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    req = urllib.request.Request(url, headers=headers or HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _clean(text: Any) -> str:
    return _TAG.sub("", str(text or "")).replace("&quot;", '"').strip()


def _duration_text(value: Any) -> str:
    if isinstance(value, (int, float)) and value:
        total = int(value)
        return f"{total // 60}:{total % 60:02d}"
    text = str(value or "")
    return text if re.match(r"^\d+:\d{2}", text) else "--:--"


# --------------------------------------------------------------------------- 网易云 / QQ 音乐（标准音质）

def _download_netease(item: dict[str, Any], dest_dir: Path, on_progress) -> Path:
    """网易云：走公开的 outer 外链，普通音质是免解密的 mp3。"""
    song_id = str(item.get("id") or "")
    if not song_id:
        raise RuntimeError("这条结果没有网易云歌曲 id")
    url = f"https://music.163.com/song/media/outer/url?id={song_id}.mp3"
    if on_progress:
        on_progress("下载中（网易云标准音质）")
    return _download_http(url, dest_dir, str(item.get("title") or song_id), ".mp3",
                          headers={"User-Agent": UA, "Referer": "https://music.163.com/"})


def _download_qqmusic(item: dict[str, Any], dest_dir: Path, on_progress) -> Path:
    """QQ音乐：先取 vkey，再拼 sip + purl 下载标准音质。"""
    mid = str(item.get("id") or "")
    if not mid:
        raise RuntimeError("这条结果没有 QQ音乐 songmid")
    payload = {
        "req_0": {
            "module": "vkey.GetVkeyServer",
            "method": "CgiGetVkey",
            "param": {"guid": "10000", "songmid": [mid], "songtype": [0], "uin": "0", "platform": "20"},
        }
    }
    url = "https://u.y.qq.com/cgi-bin/musicu.fcg?format=json&data=" + urllib.parse.quote(json.dumps(payload))
    data = _get_json(url, headers={"User-Agent": UA, "Referer": "https://y.qq.com/"})
    info = ((data.get("req_0") or {}).get("data") or {})
    urls = info.get("midurlinfo") or []
    sip = (info.get("sip") or [""])[0]
    purl = (urls[0] or {}).get("purl") if urls else ""
    if not purl:
        raise RuntimeError("QQ音乐没返回可用地址（可能要会员或这首歌受限）")
    if on_progress:
        on_progress("下载中（QQ音乐标准音质）")
    return _download_http(sip + purl, dest_dir, str(item.get("title") or mid), ".m4a",
                          headers={"User-Agent": UA, "Referer": "https://y.qq.com/"})


def _download_http(url: str, dest_dir: Path, name: str, suffix: str, headers: dict | None = None) -> Path:
    safe = re.sub(r'[\\/:*?"<>|]+', "_", name)[:60] or "audio"
    target = dest_dir / f"{safe}{suffix}"
    req = urllib.request.Request(url, headers=headers or {"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as resp, target.open("wb") as fh:
        fh.write(resp.read())
    if target.stat().st_size < 50_000:
        target.unlink(missing_ok=True)
        raise RuntimeError("下载到的文件太小，可能这首歌要会员或已下架")
    log.done(f"下载完成：{target.name}")
    return target
