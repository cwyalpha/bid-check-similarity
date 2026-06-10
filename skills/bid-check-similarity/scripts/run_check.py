#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


def _add_core_paths() -> None:
    script_dir = Path(__file__).resolve().parent
    vendor_dir = script_dir / "vendor"
    repo_root = script_dir.parents[2] if len(script_dir.parents) >= 3 else None

    for candidate in (vendor_dir, repo_root):
        if candidate and (candidate / "checksim").exists():
            sys.path.insert(0, str(candidate))
            return


def main() -> int:
    _add_core_paths()
    try:
        from checksim.cli import main as cli_main
    except ImportError as exc:
        print(
            "无法导入 checksim 核心包。请确认 Skill 安装完整，或在当前项目根目录运行；"
            "如缺少依赖，请执行: python -m pip install -r scripts/requirements.txt",
            file=sys.stderr,
        )
        print(f"详细错误: {exc}", file=sys.stderr)
        return 2
    return cli_main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
