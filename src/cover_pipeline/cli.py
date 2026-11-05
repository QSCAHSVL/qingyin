"""命令行入口：cover init / doctor / train / sing / sources / gui。"""

from __future__ import annotations

import argparse
import platform
import shutil
import sys
import time
from pathlib import Path

from . import __version__
from . import config as cfg_mod
from .utils import ffmpeg, log


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cover",
        description="一条命令完成翻唱全流程：训练、分离、转换、混音、挑段",
    )
    parser.add_argument("--version", action="version", version=f"cover-pipeline {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--preset", help="配置预设：fast / balanced / hq")
    common.add_argument("--verbose", action="store_true", help="打印更多细节")

    sub.add_parser("doctor", parents=[common], help="环境自检（不改任何东西）")
    sub.add_parser("init", parents=[common], help="环境自检 + 下载基础模型")
    sub.add_parser("sources", parents=[common], help="列出可用的音源适配器")

    plan = sub.add_parser("plan", parents=[common], help="体检 + 推荐一套配置方案")
    plan.add_argument("--yes", action="store_true", help="用默认答案，不提问")
    plan.add_argument("--json", action="store_true", help="输出 JSON（给界面用）")
    plan.add_argument("--apply", metavar="ID", help="直接应用指定方案，不询问")
    plan.add_argument("--prefer", choices=["quality", "speed", "space", "stability"], help="最在意什么")
    plan.add_argument("--train", dest="will_train", choices=["yes", "no", "unsure"], help="会不会自己训练音色")
    plan.add_argument("--disk", type=float, help="能给多少磁盘（GB）")
    plan.add_argument("--patience", type=float, help="单曲最多等几分钟")
    plan.add_argument("--songs", type=int, default=10, help="预计要唱多少首（算磁盘用，默认 10）")
    plan.add_argument("--advanced", action="store_true", help="把进阶方案也算进来")

    link = sub.add_parser("link", parents=[common], help="检测/指定本地已装的 RVC 与 UVR")
    link.add_argument("--rvc-dir", help="RVC 根目录（含 infer/cli.py）")
    link.add_argument("--rvc-python", help="RVC 用的 python.exe")
    link.add_argument("--uvr-script", help="uvr_sep.py 路径")
    link.add_argument("--uvr-python", help="跑 uvr_sep.py 的 python.exe")
    link.add_argument("--uvr-model", help="分离模型：roformer / hp2 / becruily")
    link.add_argument("--auto", action="store_true", help="只自动探测并写入（默认行为）")

    search = sub.add_parser("search", parents=[common], help="在线找歌（B站 / iTunes）")
    search.add_argument("query", help="歌名或关键词")
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--download", type=int, metavar="N", help="直接下第 N 个结果（从 1 开始）")
    search.add_argument("--sing", action="store_true", help="下载后直接翻唱")

    serve = sub.add_parser("serve", parents=[common], help="启动本地网页界面")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=7801)
    serve.add_argument("--no-open", action="store_true", help="不自动打开浏览器")

    setup = sub.add_parser("setup", parents=[common], help="一键配置：探测 → 推荐 → 确认 → 自动装好")
    setup.add_argument("--yes", action="store_true", help="不询问，直接执行")
    setup.add_argument("--dry-run", action="store_true", help="只打印将执行的步骤，不动手")
    setup.add_argument("--prefer", choices=["quality", "speed", "space", "stability"], default="stability")
    setup.add_argument("--train", dest="will_train", choices=["yes", "no", "unsure"], default="unsure")
    setup.add_argument("--max-vram", type=float, help="显存预算(G)")
    setup.add_argument("--separation", choices=["auto", "uvr", "demucs", "both", "none"],
                       default="auto", help="人声分离方案（auto=按环境推荐）")

    models = sub.add_parser("models", parents=[common], help="音色模型：版本、切换、导入")
    models.add_argument("action", nargs="?", default="list", choices=["list", "use", "import", "delete"])
    models.add_argument("voice", nargs="?", help="音色名")
    models.add_argument("version", nargs="?", help="版本号（v1/v2…）")
    models.add_argument("--path", help="import 时的 .pth 路径")

    logs = sub.add_parser("logs", parents=[common], help="看日志：目录、最近文件、尾部")
    logs.add_argument("file", nargs="?", help="指定某个日志文件（默认最新的）")
    logs.add_argument("--tail", type=int, default=30, help="看最后多少行")

    lib = sub.add_parser("lib", parents=[common], help="资源库：扫描与查看")
    lib.add_argument("--scan", action="store_true", help="重建索引")
    lib.add_argument("--kind", choices=["model", "song", "output", "source"], help="只看某一类")
    lib.add_argument("--q", default="", help="按名字搜索")

    fix = sub.add_parser("fix", parents=[common], help="症状诊断：同一段素材跑多种配方")
    fix.add_argument("--song", required=True, help="work 下的歌曲目录名")
    fix.add_argument("--symptom", default="seam_noise", help="症状 id，默认 seam_noise")
    fix.add_argument("--recipes", help="只跑指定配方，逗号分隔")
    fix.add_argument("--seconds", type=float, default=60.0, help="只对比前 N 秒，默认 60")
    fix.add_argument("--adopt", help="采纳某个配方 id，写进决策记录")

    desktop = sub.add_parser("desktop", parents=[common], help="桌面窗口模式（需要 pywebview）")
    desktop.add_argument("--port", type=int, default=7801)

    sing = sub.add_parser("sing", parents=[common], help="生成翻唱")
    sing.add_argument("--song", help="歌名（用本地曲库/搜索目录匹配）")
    sing.add_argument("--input", help="本地音频文件或目录")
    sing.add_argument("--name", help="输出名（默认用歌名或文件名）")
    sing.add_argument("--full", action="store_true", help="输出全曲并切段")
    sing.add_argument("--force", action="store_true", help="忽略缓存重跑")
    sing.add_argument("--dry-run", action="store_true", help="只打印计划")
    sing.add_argument("--pitch", type=int, help="手动变调半音（覆盖自动判断）")
    sing.add_argument("--no-separate", action="store_true", help="跳过人声分离")
    sing.add_argument("--no-convert", action="store_true", help="跳过音色转换（只做分离混音）")

    train = sub.add_parser("train", parents=[common], help="用素材训练音色")
    train.add_argument("--data", required=True, help="素材目录（wav/flac/mp3）")
    train.add_argument("--name", help="模型名（默认 default）")
    train.add_argument("--epochs", type=int, help="训练轮数")
    train.add_argument("--dry-run", action="store_true", help="只统计素材，不训练")

    sub.add_parser("gui", parents=[common], help="启动本地网页界面（需要 gradio）")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    log.set_level("debug" if getattr(args, "verbose", False) else "info")

    try:
        cfg = cfg_mod.load_config(getattr(args, "preset", None), _overrides(args))
        for key in ("work_dir", "output_dir", "models_dir"):
            cfg_mod.resolve_path(cfg, key)
        ffmpeg.configure(cfg.get("tools", {}).get("ffmpeg_dir"))
        from . import probe as _probe

        cfg["local"] = _probe.local_installs(cfg)

        from .providers import load_plugins

        load_plugins()

        # 日志级别：命令行 --verbose 优先，其次 logging.level，再其次 project.log_level
        if not getattr(args, "verbose", False):
            level = (
                ((cfg.get("logging") or {}).get("level"))
                or ((cfg.get("project") or {}).get("log_level"))
                or "info"
            )
            log.set_level(str(level))
    except Exception as exc:
        log.error(str(exc))
        return 2

    handler = {
        "doctor": cmd_doctor,
        "init": cmd_init,
        "sources": cmd_sources,
        "plan": cmd_plan,
        "link": cmd_link,
        "search": cmd_search,
        "serve": cmd_serve,
        "setup": cmd_setup,
        "models": cmd_models,
        "logs": cmd_logs,
        "lib": cmd_lib,
        "fix": cmd_fix,
        "desktop": cmd_desktop,
        "sing": cmd_sing,
        "train": cmd_train,
        "gui": cmd_gui,
    }[args.command]
    try:
        return handler(args, cfg)
    except KeyboardInterrupt:
        log.warn("已中断")
        return 130
    except Exception as exc:
        log.error(str(exc))
        if getattr(args, "verbose", False):
            raise
        return 1


def _overrides(args: argparse.Namespace) -> dict:
    overrides: dict = {}
    if getattr(args, "no_separate", False):
        overrides.setdefault("separate", {})["backend"] = "none"
    if getattr(args, "no_convert", False):
        overrides.setdefault("convert", {})["backend"] = "none"
    if getattr(args, "pitch", None) is not None:
        overrides.setdefault("convert", {})["pitch"] = args.pitch
        overrides["convert"]["auto_pitch"] = False
    if getattr(args, "epochs", None):
        overrides.setdefault("train", {})["epochs"] = args.epochs
    return overrides


def cmd_link(args: argparse.Namespace, cfg: dict) -> int:
    from . import probe as probe_mod
    from .plan.writer import apply_tools

    detected = probe_mod.local_installs(cfg)
    rvc = dict(detected.get("rvc", {}))
    uvr = dict(detected.get("uvr", {}))

    if args.rvc_dir:
        rvc["dir"] = str(Path(args.rvc_dir).expanduser())
        rvc["ok"] = (Path(rvc["dir"]) / "infer" / "cli.py").exists() and bool(rvc.get("python") or args.rvc_python)
    if args.rvc_python:
        rvc["python"] = str(Path(args.rvc_python).expanduser())
        rvc["ok"] = bool(rvc.get("dir")) and Path(rvc["python"]).exists()
    if args.uvr_script:
        uvr["script"] = str(Path(args.uvr_script).expanduser())
        uvr["ok"] = Path(uvr["script"]).exists() and bool(uvr.get("python") or args.uvr_python)
    if args.uvr_python:
        uvr["python"] = str(Path(args.uvr_python).expanduser())
        uvr["ok"] = bool(uvr.get("script")) and Path(uvr["python"]).exists()
    if args.uvr_model:
        uvr["model"] = args.uvr_model

    log.step("本地已部署检测")
    log.info(f"RVC  {rvc.get('dir') or '未找到'}")
    log.info(f"     解释器 {rvc.get('python') or '未找到'}")
    if rvc.get("weights"):
        log.info(f"     权重 {', '.join(rvc['weights'][:5])}")
    log.info(f"UVR  {uvr.get('script') or '未找到'}")
    log.info(f"     解释器 {uvr.get('python') or '未找到'} ｜ 模型 {uvr.get('model') or 'roformer'}")

    if not rvc.get("ok") and not uvr.get("ok"):
        log.warn("两边都没找到。可以用参数指路径，例如：")
        log.info("  cover link --rvc-dir D:/RVC --rvc-python D:/RVC/.venv/Scripts/python.exe")
        log.info("  cover link --uvr-script D:/tools/uvr_sep.py --uvr-python D:/tools/GPT-SoVITS/.venv/Scripts/python.exe")
        return 1

    path = apply_tools({"rvc": rvc, "uvr": uvr})
    log.done(f"已写入 {path}")
    log.info("之后跑 sing 会自动用这些本地程序，不需要再装 pip 包")
    return 0


def cmd_doctor(args: argparse.Namespace, cfg: dict) -> int:
    log.step("环境自检")
    log.info(f"Python      {platform.python_version()}  ({sys.executable})")
    log.info(f"系统        {platform.system()} {platform.release()}")

    ok = True
    if ffmpeg.has_ffmpeg():
        log.done("ffmpeg      已安装")
    else:
        ok = False
        log.error("ffmpeg      缺失（winget install Gyan.FFmpeg，或去 ffmpeg.org 下载后加 PATH）")

    gpu = _gpu_info()
    if gpu:
        log.done(f"显卡        {gpu}")
    else:
        log.warn("显卡        没检测到 NVIDIA GPU（CPU 也能跑，但很慢）")

    local = cfg.get("local") or {}
    rvc = local.get("rvc", {})
    uvr = local.get("uvr", {})

    if uvr.get("ok"):
        log.done(f"人声分离    本地 UVR（{Path(uvr['script']).name}，模型 {uvr.get('model')}）")
    elif _has_module("audio_separator"):
        log.done("人声分离    audio-separator 已安装")
    else:
        log.warn("人声分离    没找到本地 UVR，也没装 audio-separator（跑 cover link 或 pip install）")

    if rvc.get("ok"):
        weights = rvc.get("weights") or []
        extra = f"，权重 {', '.join(weights[:3])}" if weights else "，权重目录为空"
        log.done(f"音色转换    本地 RVC（{Path(rvc['dir']).name}{extra}）")
    elif _has_module("rvc_python"):
        log.done("音色转换    rvc-python 已安装")
    else:
        log.warn("音色转换    没找到本地 RVC，也没装 rvc-python（跑 cover link 或 pip install）")

    models_dir = Path(cfg["project"]["models_dir"])
    models = sorted(models_dir.glob("*.pth"))
    if models:
        log.done(f"音色模型    {', '.join(m.name for m in models)}")
    else:
        log.warn(f"音色模型    没有（{models_dir} 为空），先跑 cover train")

    log.info(f"工作目录    {cfg['project']['work_dir']}")
    log.info(f"输出目录    {cfg['project']['output_dir']}")
    return 0 if ok else 1


def _has_module(name: str) -> bool:
    import importlib.util

    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def cmd_init(args: argparse.Namespace, cfg: dict) -> int:
    code = cmd_doctor(args, cfg)

    # 按这台机器的实际情况，告诉他还缺什么文件
    from . import probe as probe_mod
    from .plan import Profile, print_assets, recommend_assets

    snapshot = probe_mod.probe(cfg)
    profile = Profile(will_train="unsure")
    assets = recommend_assets(snapshot, profile)
    log.step("要准备的文件")
    print_assets(assets)

    log.step("下一步")
    if not assets.get("items"):
        log.info("1) 环境齐了，直接来一首：cover sing --song \"歌名\"")
        log.info("2) 想训练自己的音色：cover train --data <素材目录>")
    else:
        log.info("1) 先把上面这些装好/下好（pip 那几行直接复制执行）")
        log.info("2) 再跑一次 cover init 确认，然后 cover sing --song \"歌名\"")
    if code != 0:
        log.warn("上面有标红的依赖没装好，先把它们补上再继续")
    return code


def cmd_sources(args: argparse.Namespace, cfg: dict) -> int:
    from .sources import available, load_plugins

    loaded = load_plugins()
    log.step("可用音源适配器")
    for name in available():
        log.info(f"  {name}")
    if loaded:
        log.info(f"已加载插件：{', '.join(loaded)}")
    else:
        log.info("没有插件。想接自己的音源，把脚本放到 plugins/ 下（见 docs/SOURCES.md）")
    return 0


def cmd_plan(args: argparse.Namespace, cfg: dict) -> int:
    from . import probe as probe_mod
    from .plan import Profile, apply_plan, current_plan, load_plans, recommend, render_card

    snapshot = probe_mod.probe(cfg)

    if not args.json:
        log.step("先看看这台机器")
        log.info(probe_mod.summary(snapshot))
        mem = snapshot["memory"]
        disk = snapshot["disk"]
        log.info(
            f"内存 {mem['total_gb']:.0f}G（可用 {mem['available_gb']:.1f}G）"
            f"｜{disk['drive'] or '当前盘'} 剩余 {disk['free_gb']:.0f}G"
        )
        if mem["available_gb"] < 2.5:
            log.warn(f"可用内存只剩 {mem['available_gb']:.1f}G，跑分离或训练前先关掉些程序，不然容易卡")
        ff = snapshot["ffmpeg"]
        log.info(f"ffmpeg {'已就绪' if ff['available'] else '缺失（装完再回来跑）'}")
        local = snapshot.get("local", {})
        if local.get("rvc", {}).get("ok"):
            log.done(f"本地 RVC：{local['rvc']['dir']}（权重 {len(local['rvc'].get('weights') or [])} 个）")
        if local.get("uvr", {}).get("ok"):
            log.done(f"本地 UVR：{Path(local['uvr']['script']).name}（模型 {local['uvr'].get('model')}）")
        if not (local.get("rvc", {}).get("ok") and local.get("uvr", {}).get("ok")):
            log.info("没检测全，可以跑 cover link 指路径，或装 pip 版依赖")
        if snapshot["assets"]["model_count"]:
            log.info(f"已有音色模型 {snapshot['assets']['model_count']} 个")

    current = current_plan()
    if current and not args.json:
        log.info(f"当前方案：{current.get('name') or current.get('id')}（{current.get('applied_at', '')}）")

    if args.apply:
        plans = load_plans()
        target = next((p for p in plans if str(p.get("id")) == args.apply), None)
        if target is None:
            log.error(f"没有这个方案：{args.apply}。可用：{', '.join(str(p.get('id')) for p in plans)}")
            return 2
        from .plan.writer import apply_tools

        apply_tools(snapshot.get("local", {}))
        path = apply_plan(target)
        log.done(f"已应用方案「{target.get('name')}」→ {path}")
        return _post_apply_check(snapshot)

    profile = _build_profile(args)
    scored = recommend(snapshot, profile)
    available = [s for s in scored if not s.excluded_reason]
    excluded = [s for s in scored if s.excluded_reason]

    if args.json:
        import json as _json

        payload = {
            "probe": snapshot,
            "profile": profile.as_dict(),
            "plans": [
                {
                    "id": s.id,
                    "name": s.name,
                    "score": s.score,
                    "recommended": s.recommended,
                    "plan": s.plan,
                    "notes": s.notes,
                }
                for s in available
            ],
            "excluded": [{"id": s.id, "reason": s.excluded_reason} for s in excluded],
        }
        print(_json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if not available:
        log.error("没有匹配的方案。可能是显存或磁盘太少，试试调低要求或换台机器。")
        for item in excluded:
            log.info(f"  {item.id}：{item.excluded_reason}")
        return 1

    log.step("给你挑了几个方案")
    for index, item in enumerate(available, start=1):
        print()
        print(render_card(item, index))
    if excluded:
        print()
        log.info("没列出来的：" + "；".join(f"{i.id}（{i.excluded_reason}）" for i in excluded))

    print()
    from .plan import print_assets, recommend_assets

    assets = recommend_assets(snapshot, profile, available[0].plan)
    log.step("这套方案还需要准备")
    print_assets(assets)
    print()
    log.info("推荐项已经标了 ★。利弊都写在上面，选哪个由你。")
    log.info(f"应用推荐方案：cover plan --apply {available[0].id}")
    if len(available) > 1:
        log.info("想换一个：把上面的 id 换进命令即可，例如 cover plan --apply " + available[1].id)
    return 0


def _post_apply_check(snapshot: dict) -> int:
    log.step("检查这套方案能不能跑")
    ok = True
    if not snapshot["ffmpeg"]["available"]:
        ok = False
        log.error("缺 ffmpeg，先装上（winget install Gyan.FFmpeg），否则跑不了")

    local = snapshot.get("local", {})
    rvc = local.get("rvc", {})
    uvr = local.get("uvr", {})
    if not uvr.get("ok") and not snapshot["deps"].get("audio_separator"):
        log.warn("分离还没着落：跑 `cover link --uvr-script ... --uvr-python ...`，或装 audio-separator")
    if not rvc.get("ok") and not snapshot["deps"].get("rvc_python"):
        log.warn("转换还没着落：跑 `cover link --rvc-dir ... --rvc-python ...`，或装 rvc-python")
    if not snapshot["assets"]["model_count"] and not (rvc.get("weights") or []):
        log.warn("还没有音色模型，下一步：cover train --data <你的素材目录>")
    if ok:
        log.done("配置已就绪")
    return 0 if ok else 1


def _build_profile(args: argparse.Namespace) -> "Profile":
    from .plan import Profile

    flags = {
        "prefer": getattr(args, "prefer", None),
        "will_train": getattr(args, "will_train", None),
        "disk_budget_gb": getattr(args, "disk", None),
        "patience_minutes": getattr(args, "patience", None),
        "allow_advanced": bool(getattr(args, "advanced", False)),
        "song_count": getattr(args, "songs", 10),
    }
    if all(value is None for key, value in flags.items() if key not in ("allow_advanced", "song_count")):
        if getattr(args, "yes", False) or not sys.stdin.isatty():
            return Profile(**{k: v for k, v in flags.items() if v is not None})

        print()
        log.step("三个问题，帮你选方案（直接回车用括号里的默认值）")
        prefer = _ask(
            "最在意什么？1 音质 2 速度 3 省空间 4 稳定不折腾",
            default="4",
            mapping={"1": "quality", "2": "speed", "3": "space", "4": "stability"},
            fallback="stability",
        )
        will_train = _ask(
            "会自己训练音色吗？1 会 2 不会 3 不确定",
            default="3",
            mapping={"1": "yes", "2": "no", "3": "unsure"},
            fallback="unsure",
        )
        disk = _ask_number("磁盘能给多少 G？", default=30.0)
        patience = _ask_number("单曲最多等几分钟？", default=10.0)
        freq = _ask(
            "多久用一次？1 偶尔 2 每周几次 3 每天",
            default="2",
            mapping={"1": "rare", "2": "weekly", "3": "daily"},
            fallback="weekly",
        )
        return Profile(
            prefer=prefer,
            will_train=will_train,
            disk_budget_gb=disk,
            patience_minutes=patience,
            frequency=freq,
            allow_advanced=flags["allow_advanced"],
            song_count=flags["song_count"],
        )

    return Profile(**{k: v for k, v in flags.items() if v is not None})


def _ask(prompt: str, default: str, mapping: dict[str, str], fallback: str) -> str:
    try:
        raw = input(f"  {prompt} [{default}]：").strip() or default
    except (EOFError, KeyboardInterrupt):
        return fallback
    return mapping.get(raw, fallback)


def _ask_number(prompt: str, default: float) -> float:
    try:
        raw = input(f"  {prompt} [{default:g}]：").strip()
    except (EOFError, KeyboardInterrupt):
        return default
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


def cmd_search(args: argparse.Namespace, cfg: dict) -> int:
    from .sources import online

    log.step(f"在线搜索：{args.query}")
    items = online.search(args.query, args.limit)
    if not items:
        log.warn("没搜到")
        return 1
    for index, item in enumerate(items, start=1):
        mark = "▶" if args.download == index else " "
        print(f"  {mark}{index:>2}. [{item['source']}] {item['title']}")
        print(f"       {item.get('duration', '')}  {item['url']}")
    if args.download:
        if args.download < 1 or args.download > len(items):
            log.error(f"没有第 {args.download} 个结果")
            return 2
        chosen = items[args.download - 1]
        cache = Path(cfg["project"]["work_dir"]) / "_cache"
        path = online.download(chosen, cache, ffmpeg_dir=cfg.get("tools", {}).get("ffmpeg_dir"))
        log.done(f"已下载：{path}")
        if args.sing:
            from .pipelines import sing as sing_pipeline

            sing_pipeline.run(str(path), Path(path).stem[:40], cfg)
    else:
        log.info('想下载：cover search "歌名" --download 1 [--sing]')
    return 0


def cmd_serve(args: argparse.Namespace, cfg: dict) -> int:
    from . import config as cfg_mod

    log_dir = cfg_mod.ROOT / "logs"
    log.enable_file(log_dir / f"server-{time.strftime('%Y%m%d')}.log")

    from .server.app import serve

    serve(cfg, host=args.host, port=args.port, open_browser=not args.no_open)
    return 0


def cmd_desktop(args: argparse.Namespace, cfg: dict) -> int:
    """桌面窗口模式：起本地服务，再用 pywebview 套一个窗口。"""
    import threading
    import time
    import webbrowser

    from .server.app import AppState, make_handler
    from http.server import ThreadingHTTPServer

    try:
        import webview  # type: ignore
    except Exception:
        log.warn("没装 pywebview，先用浏览器打开；想要独立窗口：pip install pywebview")
        return cmd_serve(argparse.Namespace(host="127.0.0.1", port=args.port, no_open=False), cfg)

    state = AppState(cfg)
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(state))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{args.port}/"
    log.done(f"桌面窗口已启动：{url}")
    webview.create_window("cover-pipeline", url, width=1180, height=820)
    webview.start()
    httpd.shutdown()
    return 0


def cmd_setup(args: argparse.Namespace, cfg: dict) -> int:
    from .setup import apply_all

    return apply_all(
        cfg,
        prefer=args.prefer,
        will_train=args.will_train,
        max_vram=args.max_vram,
        separation=args.separation,
        yes=args.yes,
        dry_run=args.dry_run,
    )


def cmd_models(args: argparse.Namespace, cfg: dict) -> int:
    from .models import activate_version, delete_version, list_models, register

    action = args.action or "list"
    if action == "list":
        items = list_models(cfg)
        if not items:
            log.warn("还没有登记过模型版本。训练完成后会自动登记，也可以用 cover models import 手动加。")
            return 1
        for item in items:
            log.step(f"{item['voice']}（当前：{item['active'] or '未设置'}）")
            for ver in item["versions"]:
                mark = "●" if ver["active"] else " "
                extra = []
                if ver.get("epochs"):
                    extra.append(f"{ver['epochs']} 轮")
                if ver.get("created_at"):
                    extra.append(ver["created_at"][:10])
                if ver.get("size_mb"):
                    extra.append(f"{ver['size_mb']}MB")
                log.info(f"  {mark} {ver['version']}  {'  '.join(extra)}")
        return 0

    if action == "use":
        if not args.voice or not args.version:
            log.error("用法：cover models use <音色> <版本>")
            return 2
        info = activate_version(cfg, args.voice, args.version)
        log.done(f"已切换到 {info['voice']} {info['version']}")
        return 0

    if action == "import":
        if not args.path:
            log.error("用法：cover models import --path <xxx.pth> [--voice 名字]")
            return 2
        path = Path(args.path).expanduser()
        voice = args.voice or path.stem
        info = register(cfg, voice, path, {"note": "手动导入"})
        log.done(f"已登记 {info['voice']} {info['version']}（当前生效）")
        return 0

    if action == "delete":
        if not args.voice or not args.version:
            log.error("用法：cover models delete <音色> <版本>")
            return 2
        delete_version(cfg, args.voice, args.version)
        log.done(f"已删除 {args.voice} {args.version}")
        return 0

    return 0


def cmd_logs(args: argparse.Namespace, cfg: dict) -> int:
    """看日志：默认列目录 + 尾部；--tail N 看指定行数。"""
    from . import config as cfg_mod

    log_dir = cfg_mod.ROOT / "logs"
    if not log_dir.exists():
        log.warn(f"还没有日志：{log_dir}（跑一次 cover serve 或 cover sing 就会生成）")
        return 1

    log.step(f"日志目录：{log_dir}")
    files = sorted(log_dir.rglob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in files[:15]:
        size_kb = path.stat().st_size / 1024
        stamp = time.strftime("%m-%d %H:%M", time.localtime(path.stat().st_mtime))
        log.info(f"  {stamp}  {size_kb:6.1f}KB  {path.relative_to(log_dir)}")
    if len(files) > 15:
        log.info(f"  …还有 {len(files) - 15} 个")

    target = Path(args.file) if args.file else (files[0] if files else None)
    if target and target.exists():
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        tail = lines[-int(args.tail or 30):]
        log.step(f"最近 {len(tail)} 行（{target.name}）")
        for line in tail:
            log.info(line)
    return 0


def cmd_lib(args: argparse.Namespace, cfg: dict) -> int:
    from .library.index import Library, human_size

    lib = Library(Path(cfg["project"]["work_dir"]) / "library.db")
    if args.scan:
        log.step("扫描资源库")
        counts = lib.scan(cfg)
        for kind, count in counts.items():
            log.info(f"  {kind}: {count}")
        log.done("索引已更新")

    stats = lib.stats()
    log.step("资源库")
    for kind, item in sorted(stats["by_kind"].items()):
        log.info(f"  {kind:<8} {item['count']:>4} 个  {human_size(item['bytes'])}")
    log.info(f"  合计 {stats['items']} 个，{human_size(stats['total_bytes'])}")

    items = lib.list(args.kind, args.q)
    if items:
        print()
        for item in items[:40]:
            print(f"  [{item['kind']}] {item['name']}  {human_size(item['size_bytes'])}")
            print(f"        {item['path']}")
    return 0


def cmd_fix(args: argparse.Namespace, cfg: dict) -> int:
    from .recipes import loader as recipes_loader
    from .recipes import runner as recipes_runner

    song_dir = Path(cfg["project"]["work_dir"]) / args.song
    if not song_dir.exists():
        log.error(f"没有这个歌曲目录：{song_dir}")
        return 2

    ids = [x.strip() for x in args.recipes.split(",")] if args.recipes else None

    if args.adopt:
        symptom = recipes_loader.find_recipe(args.symptom) or {}
        candidates = [str(r.get("id")) for r in symptom.get("recipes") or []]
        recipes_loader.record_decision(cfg, args.symptom, args.adopt, candidates)
        log.done(f"已记录：{args.symptom} → {args.adopt}")
        return 0

    result = recipes_runner.compare(song_dir, cfg, args.symptom, ids, seconds=args.seconds)
    log.step("对比结果")
    for item in result["outputs"]:
        mark = "★" if item["id"] == result["recommended"] else " "
        log.info(f"{mark} {item['name']}：{item['path']}")
    log.info("听完觉得哪个好，用 --adopt <配方id> 记下来")
    return 0


def cmd_sing(args: argparse.Namespace, cfg: dict) -> int:
    from .pipelines import sing as sing_pipeline

    query = args.input or args.song
    if not query:
        log.error("要给 --song 或 --input")
        return 2
    name = args.name or Path(query).stem
    result = sing_pipeline.run(query, name, cfg, force=args.force, full=args.full, dry_run=args.dry_run)
    if result.get("dry_run"):
        return 0
    final = result.get("final")
    if final:
        log.done(f"完成：{final}")
    if result.get("parts"):
        log.done(f"完成：{len(result['parts'])} 段")
    return 0


def cmd_train(args: argparse.Namespace, cfg: dict) -> int:
    from .pipelines import train as train_pipeline

    data = Path(args.data).expanduser()
    if not data.exists():
        log.error(f"素材目录不存在：{data}")
        return 2
    train_pipeline.run(data, args.name or "default", cfg, dry_run=args.dry_run)
    return 0


def cmd_gui(args: argparse.Namespace, cfg: dict) -> int:
    try:
        from .webui.app import launch
    except Exception as exc:
        log.error(f"网页界面没装好（pip install 'cover-pipeline[gui]'）：{exc}")
        return 1
    launch(cfg)
    return 0


def _gpu_info() -> str:
    if not shutil.which("nvidia-smi"):
        return ""
    try:
        import subprocess

        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        return out.stdout.strip().splitlines()[0] if out.stdout.strip() else ""
    except Exception:
        return ""


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
