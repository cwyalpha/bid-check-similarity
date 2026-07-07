from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class SkillBundleTest(unittest.TestCase):
    def test_skill_vendor_matches_core_source(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        source_dir = repo_root / "checksim"
        vendor_dir = repo_root / "skills" / "bid-check-similarity" / "scripts" / "vendor" / "checksim"

        source_files = sorted(path.relative_to(source_dir) for path in source_dir.glob("*.py"))
        vendor_files = sorted(path.relative_to(vendor_dir) for path in vendor_dir.glob("*.py"))

        self.assertEqual(vendor_files, source_files)
        for relative_path in source_files:
            self.assertEqual(
                (vendor_dir / relative_path).read_text(encoding="utf-8"),
                (source_dir / relative_path).read_text(encoding="utf-8"),
                f"Skill vendor is stale: {relative_path}",
            )

    def test_skill_requirements_stay_lightweight(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        skill_dir = repo_root / "skills" / "bid-check-similarity"
        requirements = (skill_dir / "scripts" / "requirements.txt").read_text(encoding="utf-8").lower()

        self.assertNotIn("pypdf", requirements)
        self.assertNotIn("paddleocr", requirements)
        self.assertNotIn("onnxruntime", requirements)
        self.assertNotIn("pypdfium2", requirements)
        self.assertFalse((skill_dir / "scripts" / "requirements-ocr.txt").exists())

    def test_skill_directory_runs_without_repo_root_imports(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        source_skill = repo_root / "skills" / "bid-check-similarity"

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundled_skill = root / "bid-check-similarity"
            shutil.copytree(source_skill, bundled_skill, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

            case_dir = root / "case"
            case_dir.mkdir()
            left = case_dir / "A公司.txt"
            right = case_dir / "B公司.txt"
            left.write_text(
                "本项目采用统一身份认证、安全审计和日志留存方案，确保业务系统稳定运行并形成可追溯记录。",
                encoding="utf-8",
            )
            right.write_text(
                "本项目采用统一身份认证、安全审计及日志留存方案，保障业务系统稳定运行并形成可追溯记录。",
                encoding="utf-8",
            )
            config = {
                "groups": [
                    {"name": "A公司", "files": [str(left)]},
                    {"name": "B公司", "files": [str(right)]},
                ],
                "options": {"min_chars": 10, "similarity_threshold": 0.72},
            }
            config_path = case_dir / "case.json"
            config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
            output_dir = root / "outputs"

            completed = subprocess.run(
                [
                    sys.executable,
                    str(bundled_skill / "scripts" / "run_check.py"),
                    "--config",
                    str(config_path),
                    "--output",
                    str(output_dir),
                    "--quiet",
                ],
                cwd=root,
                text=True,
                capture_output=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue((output_dir / "report.html").exists())
            self.assertTrue((output_dir / "ai_summary.json").exists())
            summary = json.loads((output_dir / "ai_summary.json").read_text(encoding="utf-8"))
            self.assertGreaterEqual(summary["stats"]["similar_match_count"], 1)

    def test_skill_rejects_pdf_without_loading_ocr_stack(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        source_skill = repo_root / "skills" / "bid-check-similarity"

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundled_skill = root / "bid-check-similarity"
            shutil.copytree(source_skill, bundled_skill, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

            case_dir = root / "case"
            case_dir.mkdir()
            left = case_dir / "A公司.pdf"
            right = case_dir / "B公司.txt"
            left.write_bytes(b"%PDF-1.4\n%%EOF\n")
            right.write_text("本项目采用统一身份认证、安全审计和日志留存方案。", encoding="utf-8")
            config = {
                "groups": [
                    {"name": "A公司", "files": [str(left)]},
                    {"name": "B公司", "files": [str(right)]},
                ],
                "options": {"min_chars": 10, "similarity_threshold": 0.72},
            }
            config_path = case_dir / "case.json"
            config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(bundled_skill / "scripts" / "run_check.py"),
                    "--config",
                    str(config_path),
                    "--output",
                    str(root / "outputs"),
                    "--quiet",
                ],
                cwd=root,
                text=True,
                capture_output=True,
            )

            self.assertEqual(completed.returncode, 2)
            self.assertIn("暂不支持的文件格式", completed.stderr)


if __name__ == "__main__":
    unittest.main()
