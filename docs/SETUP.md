# 一键配置（cover setup）

新用户不用看文档、不用敲 pip：`cover setup` 会先探测，再推荐，等你确认后自己装好。

## 流程

```
探测 → 推荐 → 给你看清单 → 你确认 → 执行 → 自检
```

1. **探测**：显卡/显存、内存、磁盘、ffmpeg、已装依赖、本机有没有 RVC/UVR
2. **推荐**：选一套方案（和 `cover plan` 同一套引擎），再算出要下哪些文件
3. **清单**：每一步都写明「做什么、多大、装到哪、失败会怎样」
4. **确认**：命令行问 y/N；界面点「确认并自动配置」
5. **执行**：
   - pip 依赖用当前解释器装（`sys.executable -m pip`），不动系统环境
   - 权重下载走 hf-mirror，支持断点续传，失败自动换官方源
   - 写 `configs/local.yaml`（只改相关的几段，其它保留）
6. **自检**：装完再探一次，缺什么直接说

## 命令

```bash
cover setup --dry-run          # 只看会做什么，不动手
cover setup                    # 问一句 y/N 再执行
cover setup --yes              # 不问，直接执行（脚本/自动化用）
cover setup --train yes        # 我打算自己训练，多下预训练底模
cover setup --max-vram 6       # 显存预算 6G
```

## 会装什么、下什么

| 情况 | pip | 权重 |
|---|---|---|
| 本机已有 RVC + UVR | 不装 | 不下（只写配置 + 自检） |
| 有 RVC 没 UVR | `audio-separator[gpu]` | 分离模型（UVR 自带或首次运行下载） |
| 有 UVR 没 RVC | `rvc-python` + torch | hubert_base.pt、rmvpe.pt（已有就跳过） |
| 全新 + 有显卡 | torch CUDA + 两个运行时 | 同上；训练再加 pretrained_v2 |
| 全新 + 没显卡 | torch CPU + 两个运行时 | 同上 |

权重会先检查几个常见位置（RVC 的 `assets/hubert_base.pt`、`assets/hubert/`、`assets/rmvpe/`），
找到就跳过，不重复下。

## 下载源

默认 `https://hf-mirror.com`（国内可达），官方 HuggingFace 作为兜底。
换源：`configs/local.yaml` 里设 `download.mirror`。
权重想放别处：设 `download.assets_dir`。

## 失败了怎么办

- pip 失败：看报错里的包名，多半是网络或 Python 版本；重跑一次通常会续上
- 下载失败：会自动换源试一次；还不行就手动下，放到清单里写的目标路径
- 不想让它动系统：先 `--dry-run` 看清单，再手动执行