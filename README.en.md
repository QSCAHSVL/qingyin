# 卿音 · QingYin

> A local song-cover pipeline: find a song → separate vocals → convert voice → mix → export. Runs entirely on your own machine.

[中文 README](README.md)

## Why another one

Most RVC cover projects stop at "a Gradio page with sliders". QingYin focuses on the **orchestration layer** new users actually trip over:

- **Hardware-aware plans** — detect GPU/VRAM/RAM/disk, recommend a parameter set, explain the trade-offs
- **Symptom recipes** — "seam clicks", "muffled vocal", "backing too loud": each has 2–3 candidate fixes with pros/cons, A/B rendered for comparison
- **Reuse what you already have** — if RVC and UVR5 are already on the machine, point to them; nothing gets reinstalled
- **Model versioning** — every training run becomes a new version; switch back in one click
- **Cancelable jobs** — long steps run as cancellable subprocesses with a hang watchdog
- **Agent API** — `POST /api/agent/sing` with a local key, so DSH / WorkBuddy / your own scripts can drive it

## Install

```bash
pip install -e .
cover doctor          # environment check
cover link --auto     # detect local RVC / UVR and write paths
cover plan            # hardware-based recommendation
cover serve           # web UI at http://127.0.0.1:7801
```

## Commands

| Command | What it does |
|---|---|
| `cover plan` | Detect hardware, recommend a parameter set, `--apply` to write it |
| `cover link` | Detect / point to local RVC and UVR |
| `cover search "song"` | Search Bilibili / iTunes / NetEase / QQ Music; `--download N --sing` |
| `cover sing --input file` / `--song name` | Render a cover |
| `cover train --data dir` | Prepare dataset and train; new model version registered automatically |
| `cover models list\|use\|import\|delete` | Manage voice model versions |
| `cover fix --song X --symptom seam_noise` | Render recipe candidates for comparison |
| `cover lib --scan` | Index models / projects / outputs / sources |
| `cover serve` / `cover desktop` | Web UI / desktop window |

## Notes

- This project only orchestrates. Separation and voice conversion rely on community models (UVR / RVC); you supply the source material and make sure you have the rights.
- No decryption of DRM audio is included or recommended. High-quality fetching from streaming platforms is a **plugin interface** (`providers.DecryptProvider`) you fill in yourself if you have a licensed path.
- Standard-quality (mp3/m4a) downloads from public endpoints are supported.

## License

MIT
