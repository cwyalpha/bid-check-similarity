from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import tkinter as tk

from checksim.ui import CheckSimApp, _completion_message, _groups_from_company_folders, _groups_from_single_files, _preset_for_limits


class CheckSimUiTest(unittest.TestCase):
    def test_polling_uses_explicit_running_state(self) -> None:
        root = tk.Tk()
        root.withdraw()
        try:
            app = CheckSimApp(root)
            calls: list[tuple[int, object]] = []

            def fake_after(delay: int, callback: object) -> None:
                calls.append((delay, callback))

            app.after = fake_after  # type: ignore[method-assign]
            app.is_running = True
            app.run_button.configure(state="disabled")

            self.assertFalse(app.run_button["state"] == "disabled")
            self.assertEqual(str(app.run_button["state"]), "disabled")

            app._poll_events()
            self.assertEqual(len(calls), 1)
        finally:
            root.destroy()

    def test_groups_from_single_files_creates_one_group_per_file(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "A公司投标文件.docx"
            second_dir = root / "B公司"
            second_dir.mkdir()
            second = second_dir / "A公司投标文件.md"
            first.write_text("a", encoding="utf-8")
            second.write_text("b", encoding="utf-8")

            groups = _groups_from_single_files((str(first), str(second)))

        self.assertEqual(len(groups), 2)
        self.assertEqual([len(group["files"]) for group in groups], [1, 1])
        self.assertEqual(
            set(group["name"] for group in groups),
            {"B公司_A公司投标文件", f"{root.name}_A公司投标文件"},
        )

    def test_groups_from_company_folders_uses_each_child_folder_as_group(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            company_a = root / "A公司"
            company_a_nested = company_a / "技术部分"
            company_a_nested.mkdir(parents=True)
            company_b = root / "B公司"
            company_b.mkdir()
            empty = root / "空目录"
            empty.mkdir()
            (company_a_nested / "投标文件.docx").write_text("a", encoding="utf-8")
            (company_b / "响应文件.wps").write_text("b", encoding="utf-8")

            groups, empty_folders = _groups_from_company_folders(root)

        self.assertEqual([group["name"] for group in groups], ["A公司", "B公司"])
        self.assertEqual([len(group["files"]) for group in groups], [1, 1])
        self.assertEqual(empty_folders, ["空目录"])

    def test_report_preset_and_advanced_options_are_collected(self) -> None:
        root = tk.Tk()
        root.withdraw()
        try:
            app = CheckSimApp(root)
            app.groups = [
                {"name": "A公司", "files": ["A.docx"]},
                {"name": "B公司", "files": ["B.docx"]},
            ]
            app.report_preset.set("快速")
            app._apply_report_preset()
            app.write_all_matches.set(True)
            app.candidate_shared_ratio.set("0")
            app.min_length_ratio.set("0.55")

            config = app._collect_config()
            options = config["options"]

            self.assertEqual(options["max_matches_per_pair"], 200)
            self.assertEqual(options["max_excluded_matches_per_pair"], 50)
            self.assertEqual(options["candidate_shared_ratio"], 0.0)
            self.assertEqual(options["min_length_ratio"], 0.55)
            self.assertTrue(options["write_all_matches"])
            self.assertEqual(options["similarity_backend"], "local_ngrams")
        finally:
            root.destroy()

    def test_preset_name_and_completion_message(self) -> None:
        self.assertEqual(_preset_for_limits(600, 200), "平衡")
        self.assertEqual(_preset_for_limits(601, 200), "自定义")
        message = _completion_message(
            {
                "stats": {
                    "displayed_similar_match_count": 2,
                    "total_similar_match_count": 8,
                    "displayed_excluded_match_count": 1,
                    "total_excluded_match_count": 3,
                    "match_truncated": True,
                },
                "output_files": {"output_dir": "outputs/run_test", "all_matches_jsonl": "outputs/run_test/all_matches.jsonl"},
            }
        )
        self.assertIn("2/8", message)
        self.assertIn("all_matches.jsonl", message)


if __name__ == "__main__":
    unittest.main()
