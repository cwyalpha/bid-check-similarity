from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import tkinter as tk
from unittest.mock import patch

from checksim.ui import (
    CheckSimApp,
    _completion_message,
    _groups_from_company_folders,
    _groups_from_single_files,
    _open_path,
    _output_root,
)


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
            (company_b / "响应文件.txt").write_text("b", encoding="utf-8")

            groups, empty_folders = _groups_from_company_folders(root)

        self.assertEqual([group["name"] for group in groups], ["A公司", "B公司"])
        self.assertEqual([len(group["files"]) for group in groups], [1, 1])
        self.assertEqual(empty_folders, ["空目录"])

    def test_visible_options_are_collected_without_limit_fields(self) -> None:
        root = tk.Tk()
        root.withdraw()
        try:
            app = CheckSimApp(root)
            app.groups = [
                {"name": "A公司", "files": ["A.docx"]},
                {"name": "B公司", "files": ["B.docx"]},
            ]
            app.min_chars.set("10")

            config = app._collect_config()
            options = config["options"]

            self.assertEqual(options["min_chars"], 10)
            self.assertEqual(options["similarity_backend"], "local_ngrams")
            self.assertNotIn("max_matches_per_pair", options)
            self.assertNotIn("write_all_matches", options)
        finally:
            root.destroy()

    def test_completion_message_reports_full_counts(self) -> None:
        message = _completion_message(
            {
                "stats": {
                    "similar_match_count": 8,
                    "excluded_match_count": 3,
                },
                "output_files": {"output_dir": "outputs/run_test"},
            }
        )
        self.assertIn("异常片段：8", message)
        self.assertIn("已排除片段：3", message)
        self.assertNotIn("all_matches.jsonl", message)

    def test_open_path_uses_macos_open(self) -> None:
        with patch("checksim.ui.sys.platform", "darwin"), patch("checksim.ui.subprocess.Popen") as mocked:
            _open_path("/tmp/report.html")

        mocked.assert_called_once_with(["open", "/tmp/report.html"])

    def test_frozen_macos_output_root_uses_user_documents(self) -> None:
        with patch("checksim.ui._is_frozen_macos", return_value=True), patch.object(
            Path,
            "home",
            return_value=Path("/Users/demo"),
        ):
            self.assertEqual(_output_root(), Path("/Users/demo/Documents/标书文件查重工具输出"))


if __name__ == "__main__":
    unittest.main()
