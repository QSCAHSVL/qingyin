# 卿音 · QingYin (cover-pipeline)

[![CI](https://github.com/QSCAHSVL/qingyin/actions/workflows/ci.yml/badge.svg)](https://github.com/QSCAHSVL/qingyin/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10+-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)

[中文 README](README.md)

> A local song-cover pipeline: find a song → separate vocals → convert voice → mix → export, all on your own machine.

One command from "a song name" to "a finished cover": **train a voice model → separate vocals → convert timbre → mix → pick the chorus → export/send**.

Built for people new to AI voice work: you don't need to understand RVC knobs, and you don't need to write scripts.

> This project only does **orchestration**. Vocal separation and voice conversion rely on community open-source models (UVR / RVC, etc.);
> audio sources and training material are your responsibility to obtain and license legally.
> It ships **no** tooling that bypasses copyright protection. See [docs/DISCLAIMER.md](docs/DISCLAIMER.md) (Chinese).

## What it solves

Most of the RVC ecosystem stops at "click buttons in a web UI": separate by hand, guess parameters, assemble the mix yourself,
find the chorus by ear. QingYin turns that chain into one reproducible command and handles the traps beginners hit:

- **Environment check**: GPU / VRAM / dependencies / models — tells you what's missing in one pass
- **Training wizard**: drop in material; it slices, cleans, extracts features, trains, exports, and judges whether you have enough audio
- **One-shot cover**: local file or link in, finished audio out
- **Automatic chorus pick**: energy-based, 45 seconds by default
- **Automatic key shift**: measures the source vocal pitch and drops the whole song 1–3 semitones when it sits too high
- **Cache reuse**: if the finished mix is newer than the model it's reused; retraining invalidates it automatically

## Quick start

```bash
pip install -e .
cover plan                          # probe the machine + 3 questions → 2–3 plans
cover plan --apply vram8_balanced   # pick one, write it into the config
cover train --data ./materials      # train a voice (optional — an existing model works too)
cover sing --song "song name"       # render the cover
```

Step-by-step walkthrough: [docs/QUICKSTART.md](docs/QUICKSTART.md) (Chinese).

## Already have RVC / UVR installed? Reuse them

Plenty of machines already have RVC and UVR5. QingYin does **not** ask you to install another copy — it looks for yours:

```bash
cover link --auto          # detect local RVC / UVR and write the paths into the config
cover doctor               # confirm it found them
```

Search order: paths from the config → common locations → walk up from `uvr_sep.py` to the GPT-SoVITS venv.
If it's somewhere unusual, point at it explicitly:

```bash
cover link --rvc-dir D:/RVC --rvc-python D:/RVC/.venv/Scripts/python.exe
cover link --uvr-script D:/tools/uvr_sep.py --uvr-python D:/tools/GPT-SoVITS/.venv/Scripts/python.exe
```

## Plan engine (let it choose if you don't know)

`cover plan` probes your machine (GPU, VRAM, RAM, disk, ffmpeg, installed deps), asks three questions
(what you care about, whether you'll train, disk & waiting budget), then prints 2–3 plans.

Each plan spells out the separation model, conversion backend, training epochs, minutes per song, VRAM peak, disk per song,
plus **pros and cons**. The recommended one gets a ★, but the choice is yours.

The plan library lives in `plans/` as plain YAML — add your own by dropping a file in:

```yaml
id: my_plan
name: "My 8G plan"
for: { min_vram_gb: 7.5, max_vram_gb: 9.9, min_disk_gb: 25, needs_train: optional }
scores: { quality: 4, speed: 4, space: 3, stability: 5 }
params: { separate: {...}, convert: {...}, train: {...} }
estimate: { per_song_minutes: 4, vram_peak_gb: 6.8, disk_per_song_mb: 240, train_minutes: 50 }
pros: ["..."]
cons: ["..."]
explain: "One-line explanation"
```

Built-ins: `cpu_only`, `vram4_infer`, `vram6_balanced`, `vram8_balanced`, `vram8_quality`, `vram12_quality`,
plus the advanced `svc_advanced` (deliberately not recommended for first-timers).

## Commands

| Command | What it does |
|---|---|
| `cover plan` | Probe + recommend plans; `--apply` writes one into the config |
| `cover link` | Detect or point at an existing RVC / UVR install |
| `cover serve` | Start the local web UI (default http://127.0.0.1:7801) |
| `cover desktop` | Desktop window mode (needs pywebview) |
| `cover doctor` | Diagnose only, change nothing |
| `cover train --data <dir>` | Train a voice model from your material |
| `cover sing --song <name>` / `--input <file>` | Render a cover |
| `cover lib --scan` | Rescan the library (models / material / outputs / sources) |
| `cover fix --song <name> --symptom seam_noise` | Symptom diagnosis: render several recipes for A/B listening |
| `cover search "song name"` | Search online sources; `--download N`, `--sing` to cover it right away |
| `cover sources` | List available source adapters |
| `cover gui` | Legacy Gradio UI (kept for history; prefer `serve`) |

## Web UI

`cover serve` starts a local page (http://127.0.0.1:7801) with ten sections:

- **Start** — one-click cover (name → find source → download → cover) plus a five-step onboarding
- **Search** — Bilibili / iTunes / NetEase / QQ Music at once; downloadable results offer "download & cover", metadata-only ones are labelled
- **Sing** — file, folder or song name; a folder lists its tracks for you to select first
- **Jobs** — progress, elapsed time, logs; running jobs can be cancelled
- **Library** — models / projects / outputs / sources / favorites, with detail view, preview, favorite, delete (moves to `work/_trash`, never hard-deletes)
- **Fix** — six symptom types (seam noise, muffled vocal, clipping, dry vocal, backing too loud, wrong timbre), 2–3 recipes each, multi-select for comparison
- **Plan** — 11 built-in plans, filterable by VRAM budget, one-click undo back to defaults
- **Train** — material folder + pre-check (duration / clips / ETA / warnings), parameters, start; auto-registers the new version and supports rollback
- **Logs** — server and job logs, tail by line count
- **Settings** — data directories (with write test), publish config, backup
- **API** — endpoint index (`/docs`) where GETs can be tried in place

The UI uses only the standard library (`http.server`) plus vanilla JS — no FastAPI/uvicorn, no bundler.

## For external agents

The "API" page shows a local key. External agents can call:

```bash
curl http://127.0.0.1:7801/api/agent/info                       # connection info incl. local key

curl -X POST http://127.0.0.1:7801/api/agent/sing \
  -H "X-Api-Key: cp_xxx" -H "Content-Type: application/json" \
  -d '{"query":"<song name>","full":false}'

curl "http://127.0.0.1:7801/api/agent/status?id=<job_id>"      # job status
```

Public endpoints `/api/sing`, `/api/search`, `/api/jobs` work without a key.

## Packaging

```powershell
scripts\build-installer.ps1                  # portable zip + Inno Setup installer (needs Inno Setup 6)
scripts\build-installer.ps1 -SkipInstaller   # portable zip only
```

| Target | How | How users run it |
|---|---|---|
| Portable | `scripts\build-installer.ps1` → `dist/卿音-<version>-portable.zip` | unzip, double-click `启动.bat` |
| Installer | same script → `dist/卿音-<version>-setup.exe` | run the wizard, pick a dependency tier |
| Desktop window | `启动-桌面版.bat` or `cover desktop` | standalone window, no browser |

Details and dependency tiers: [docs/PACKAGING.md](docs/PACKAGING.md) (Chinese).

## Training material requirements

- 10–30 minutes of clean vocals; no backing track, no reverb, no background music
- One speaker, one device, one room is best
- wav / flac / mp3, subdirectories allowed
- If it's short, `cover train` warns ("recommend at least X minutes") but lets you continue

## Directory layout

```
configs/            config and presets (fast / balanced / hq)
plans/              plan library (plain YAML, tiered by VRAM and preference)
src/cover_pipeline/
  cli.py            command entry point
  probe.py          hardware / environment probing
  plan/             plan engine: scoring, rendering plan cards, writing config
  core/             separate, convert, mix, chorus picking, pitch shift
  pipelines/        train / sing orchestration
  server/           local web UI + agent API (app.py = routes, services/* = logic)
  sources/          source adapters (local files + your own plugins)
  utils/            ffmpeg, logging
plugins/            your own source plugins (not tracked)
docs/               documentation
scripts/            build and packaging scripts
```

## Audio sources (important)

The main repo only ships `local_file` (local audio files).
Other sources — streaming platforms, your own downloader, your own decryption tool — belong in `plugins/`;
they are neither bundled, nor provided, nor explained here. See [docs/SOURCES.md](docs/SOURCES.md) (Chinese).

## Hardware requirements

| VRAM | What you can do |
|---|---|
| 8 GB+ | Train + infer (recommended) |
| 6 GB | Infer fine, training with a smaller batch |
| 4 GB | Infer only |

CPU works too, but much slower — not recommended for training.

## Documentation

Everything lives in `docs/` (Chinese). Highlights:

| Topic | File |
|---|---|
| 15-minute first cover | [QUICKSTART.md](docs/QUICKSTART.md) |
| One-command environment setup | [SETUP.md](docs/SETUP.md), [ASSETS.md](docs/ASSETS.md) |
| How plans are chosen | [PLANS.md](docs/PLANS.md) |
| Training + model versioning | [TRAIN.md](docs/TRAIN.md), [MODELS.md](docs/MODELS.md) |
| Adding your own sources | [SOURCES.md](docs/SOURCES.md), [PROVIDERS.md](docs/PROVIDERS.md) |
| Packaging and release | [PACKAGING.md](docs/PACKAGING.md) |
| Copyright and risk | [DISCLAIMER.md](docs/DISCLAIMER.md), [RISK.md](docs/RISK.md) |
| How the project grew | [JOURNAL.md](docs/JOURNAL.md), [REVIEW.md](docs/REVIEW.md) |
| Picking up development | [NEXT-SESSION.md](docs/NEXT-SESSION.md), [PLAN.md](docs/PLAN.md) |

## License

Code is MIT. Bundled open-source dependencies keep their own licenses (UVR, RVC, ffmpeg, …) — see [ATTRIBUTION.md](ATTRIBUTION.md).
**Licensing of voice models and training material is on you**: don't train on someone else's voice or redistribute a model without permission.
No decryption implementation is bundled, and no voice model is packaged.

## Status

0.4.2, usable today: `cover setup` configures the environment, `cover sing` produces a cover, and the local web UI
(`cover serve`) ships 10 sections and 59 endpoints. The backend is split into `server/services/*`, the frontend into native
ES modules under `static/pages/*`. 71 unit tests plus frontend static checks run in CI; ruff is clean and now blocking.

Still open: the Demucs separation backend is implemented but not verified on real hardware; installer shortcuts and
uninstall leftovers are verified by hand only.

Per-version changes live in [CHANGELOG.md](CHANGELOG.md).
