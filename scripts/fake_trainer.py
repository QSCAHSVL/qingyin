"""假训练器：只为验证「训练 → 导出 .pth → 自动登记版本」这条链路。

它不训练任何模型，只按约定在输出目录写一个占位 .pth 和日志。
真实训练请配置 configs/local.yaml 的 train.command 指向 RVC 或自己的脚本。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--name", default="demo")
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    out_dir = Path(args.out or Path(args.data) / ".." / "fake_out").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{args.name}.pth"
    target.write_bytes(b"FAKE_MODEL" * 1024)  # 7KB 占位

    print(f"[fake-trainer] data={args.data} name={args.name} epochs={args.epochs}")
    print(f"[fake-trainer] wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())