#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


def _add_core_paths() -> None:
    script_dir = Path(__file__).resolve().parent
    vendor_dir = script_dir / "vendor"

    if (vendor_dir / "checksim").exists():
        sys.path.insert(0, str(vendor_dir))
        return


def main() -> int:
    _add_core_paths()
    try:
        from checksim.cli import main as cli_main
    except ImportError as exc:
        print(
            "无法导入 Skill 内置的 checksim 核心包。请确认 scripts/vendor/checksim 存在；"
            "如缺少依赖，请执行: python -m pip install -r scripts/requirements.txt",
            file=sys.stderr,
        )
        print(f"详细错误: {exc}", file=sys.stderr)
        return 2
    return cli_main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
