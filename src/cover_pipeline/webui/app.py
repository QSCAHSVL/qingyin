"""可选的本地网页界面（gradio）。

目标用户是不想敲命令的人：拖一个音频进去，点一下，出成品。
没有装 gradio 时这里会直接报错，命令行不受影响。
"""

from __future__ import annotations

from pathlib import Path


def launch(cfg: dict) -> None:  # pragma: no cover - 需要 gradio 与真实文件
    import gradio as gr

    from ..pipelines import sing as sing_pipeline
    from ..utils import log

    def run_sing(file_path: str, song: str, seconds: float, full: bool, force: bool):
        query = file_path or song
        if not query:
            return "请给一个音频文件，或者填歌名", None
        name = Path(query).stem
        local = {**cfg, "clip": {**cfg.get("clip", {}), "seconds": float(seconds)}}
        result = sing_pipeline.run(query, name, local, force=force, full=full)
        if full:
            return f"完成，切了 {len(result.get('parts', []))} 段", None
        return f"完成：{result.get('final')}", result.get("final")

    with gr.Blocks(title="cover-pipeline") as demo:
        gr.Markdown("## 翻唱流水线\n给一个音频，出成品。第一次跑会慢一些。")
        with gr.Row():
            file_in = gr.File(label="源音频", type="filepath")
            song_in = gr.Textbox(label="或者：歌名", placeholder="歌名")
        seconds = gr.Slider(15, 120, value=float(cfg.get("clip", {}).get("seconds", 45)), label="片段长度（秒）")
        full = gr.Checkbox(label="输出全曲并切段", value=False)
        force = gr.Checkbox(label="忽略缓存重跑", value=False)
        btn = gr.Button("开始", variant="primary")
        status = gr.Textbox(label="状态")
        audio_out = gr.Audio(label="成品")
        btn.click(run_sing, [file_in, song_in, seconds, full, force], [status, audio_out])

    log.info("界面地址会打印在下面，Ctrl+C 退出")
    demo.launch(inbrowser=True)
