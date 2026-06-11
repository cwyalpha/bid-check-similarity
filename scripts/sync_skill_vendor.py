#!/usr/bin/env python3
from __future__ import annotations

import shutil
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    source = repo_root / "checksim"
    target = repo_root / "skills" / "bid-check-similarity" / "scripts" / "vendor" / "checksim"
    if not source.is_dir():
        raise SystemExit(f"checksim source not found: {source}")

    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
    print(f"Synced {source} -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
