from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from .engine import load_config, run_check


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="离线标书/文件查重工具")
    parser.add_argument("--config", required=True, help="检测配置 JSON 文件")
    parser.add_argument("--output", help="输出目录；默认 outputs/run_yyyyMMdd_HHmmss")
    parser.add_argument("--quiet", action="store_true", help="减少进度输出")
    args = parser.parse_args(argv)

    try:
        config_path = Path(args.config).expanduser().resolve()
        config = load_config(config_path)
        output = Path(args.output).expanduser().resolve() if args.output else _default_output_dir()
        progress = (lambda message: None) if args.quiet else (lambda message: print(message, flush=True))
        result = run_check(config, output, progress)
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2

    if not args.quiet:
        print(json.dumps(result.get("output_files", {}), ensure_ascii=False, indent=2))
    return 0


def _default_output_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path.cwd() / "outputs" / f"run_{stamp}"


if __name__ == "__main__":
    raise SystemExit(main())
