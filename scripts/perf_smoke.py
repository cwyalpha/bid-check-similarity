#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成临时大样本并运行查重性能 smoke。")
    parser.add_argument("--mode", choices=["cli", "skill"], default="cli", help="通过 CLI 或 Skill 包装脚本运行")
    parser.add_argument("--groups", type=int, default=4, help="投标分组数量")
    parser.add_argument("--chars-per-file", type=int, default=100000, help="每组 Markdown 样本文本目标字符数")
    parser.add_argument("--keep", action="store_true", help="保留临时样本和输出目录")
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    work_dir = Path(tempfile.mkdtemp(prefix="checksim_perf_"))
    try:
        config_path = _generate_case(work_dir, args.groups, args.chars_per_file)
        output_dir = work_dir / "outputs" / f"run_{args.mode}"
        command = _command_for_mode(repo_root, args.mode, config_path, output_dir)
        started = time.perf_counter()
        completed = subprocess.run(command, cwd=repo_root, text=True, capture_output=True)
        elapsed = time.perf_counter() - started
        if completed.returncode != 0:
            sys.stderr.write(completed.stdout)
            sys.stderr.write(completed.stderr)
            return completed.returncode

        result_path = output_dir / "result.json"
        result = json.loads(result_path.read_text(encoding="utf-8"))
        report_path = output_dir / "report.html"
        ai_summary_path = output_dir / "ai_summary.json"
        metrics = {
            "mode": args.mode,
            "elapsed_seconds": round(elapsed, 3),
            "groups": args.groups,
            "chars_per_file": args.chars_per_file,
            "stats": result.get("stats", {}),
            "ai_summary_json_bytes": _file_size(ai_summary_path),
            "report_html_bytes": _file_size(report_path),
            "result_json_bytes": _file_size(result_path),
            "output_dir": str(output_dir),
            "kept": bool(args.keep),
        }
        print(json.dumps(metrics, ensure_ascii=False, indent=2))
        return 0
    finally:
        if not args.keep:
            shutil.rmtree(work_dir, ignore_errors=True)


def _command_for_mode(repo_root: Path, mode: str, config_path: Path, output_dir: Path) -> list[str]:
    if mode == "cli":
        return [
            sys.executable,
            "-m",
            "checksim.cli",
            "--config",
            str(config_path),
            "--output",
            str(output_dir),
            "--quiet",
        ]
    skill_script = repo_root / "skills" / "bid-check-similarity" / "scripts" / "run_check.py"
    return [
        sys.executable,
        str(skill_script),
        "--config",
        str(config_path),
        "--output",
        str(output_dir),
        "--quiet",
    ]


def _generate_case(work_dir: Path, group_count: int, chars_per_file: int) -> Path:
    samples_dir = work_dir / "samples"
    samples_dir.mkdir(parents=True)
    exclude_path = samples_dir / "招标文件.md"
    exclude_path.write_text(_exclude_text(chars_per_file // 5), encoding="utf-8")

    groups: list[dict[str, Any]] = []
    for index in range(1, group_count + 1):
        group_dir = samples_dir / f"{index:02d}_测试公司{index}"
        group_dir.mkdir()
        file_path = group_dir / "投标文件.md"
        file_path.write_text(_bid_text(index, chars_per_file), encoding="utf-8")
        groups.append({"name": f"测试公司{index}", "files": [str(file_path)]})

    config = {
        "groups": groups,
        "exclude_files": [str(exclude_path)],
        "keywords": ["华远智联科技有限公司"],
        "regex_keywords": ["每日巡检|月度运行分析"],
        "regex_presets": {
            "china_mobile": True,
            "china_id_card": True,
            "email": True,
            "china_address": True,
        },
        "options": {
            "min_chars": 10,
            "min_words": 8,
            "similarity_threshold": 0.78,
            "exclude_threshold": 0.86,
            "sentence_delimiters": "。！？!?；;",
            "soft_delimiters": "，,、：:",
            "similarity_backend": "local_ngrams",
            "image_ahash_distance": 6,
        },
    }
    config_path = work_dir / "case.json"
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return config_path


def _exclude_text(target_chars: int) -> str:
    paragraphs: list[str] = []
    index = 1
    while len("\n".join(paragraphs)) < target_chars:
        paragraphs.append(
            f"第{index}条 招标文件要求投标人建立统一项目治理机制，"
            "按照周例会、月度评审和季度总结的方式提交服务报告，并接受采购人监督。"
        )
        paragraphs.append(
            f"第{index}条 招标文件要求服务团队在故障发生后及时响应，"
            "记录处理过程、影响范围、恢复时间和后续预防措施。"
        )
        index += 1
    return "\n\n".join(paragraphs)


def _bid_text(group_index: int, target_chars: int) -> str:
    paragraphs: list[str] = [f"# 测试公司{group_index}投标文件"]
    index = 1
    while len("\n".join(paragraphs)) < target_chars:
        paragraphs.append(
            f"第{index}项 响应招标文件要求，投标人建立统一项目治理机制，"
            "按照周例会、月度评审和季度总结的方式提交服务报告，并接受采购人监督。"
        )
        paragraphs.append(
            f"第{index}项 本公司针对平台运行维护设置三级响应流程，"
            f"由驻场工程师、远程专家和项目经理共同闭环处理，预计第{(group_index + index) % 7 + 1}个工作日完成阶段复盘。"
        )
        paragraphs.append(
            f"第{index}项 运维方案采用每日巡检、自动告警、月度运行分析和风险闭环四类措施，"
            f"重点保障核心业务系统连续稳定运行，并结合测试公司{group_index}经验优化沟通路径。"
        )
        paragraphs.append(
            f"第{index}项 华远智联科技有限公司提供的历史接口规范将作为兼容性核查依据，"
            "项目组会逐项确认字段映射、权限边界和数据留痕要求。"
        )
        paragraphs.append(
            f"第{index}项 本章节为测试公司{group_index}独有说明，"
            f"包含设备台账编号 GC-{group_index:02d}-{index:04d}、现场联系人安排和差异化交付计划。"
        )
        index += 1
    return "\n\n".join(paragraphs)


def _file_size(path: Path) -> int:
    return path.stat().st_size if path.exists() else 0


if __name__ == "__main__":
    raise SystemExit(main())
