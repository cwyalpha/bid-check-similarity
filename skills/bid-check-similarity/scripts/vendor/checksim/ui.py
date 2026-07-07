from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, VERTICAL, filedialog, messagebox, simpledialog
import tkinter as tk
from tkinter import ttk

from .engine import load_config, run_check
from .models import CheckOptions, SUPPORTED_EXTENSIONS, normalize_path


SUPPORTED_FILETYPES = [
    ("支持的文件", "*.docx *.doc *.wps *.pdf *.md *.txt"),
    ("Word/WPS", "*.docx *.doc *.wps"),
    ("PDF", "*.pdf"),
    ("Markdown", "*.md"),
    ("Text", "*.txt"),
]


PARAM_HELP = {
    "keywords": (
        "重要关键词/正则",
        "每行一条规则。普通文本按字面量匹配；以 re: 开头时按正则匹配。"
        "关键词不受短文本过滤影响，只要同一规则出现在 2 个及以上公司/分组中，就会在报告中标为异常。"
        "建议填写公司名称、法人/负责人、项目人员姓名、手机号、统一社会信用代码、供应商专有产品名等。",
    ),
    "min_chars": (
        "中文/混合最短字符",
        "中文或中英混合片段参与相似度比对的最短可见字符数。默认 10。"
        "低于该长度的标题、编号、目录项等不参与文本相似度比对，但仍参与关键词/正则检测。",
    ),
    "min_words": (
        "英文最短词数",
        "纯英文片段参与相似度比对的最短英文词数。默认 8。"
        "低于该词数的短句不参与相似度比对，但仍参与关键词/正则检测。",
    ),
    "similarity_threshold": (
        "文本相似阈值",
        "跨公司/分组文本片段达到该相似度就会标为异常。默认 0.78。"
        "数值越高越严格，越低越容易发现轻微改写但也可能增加噪声。",
    ),
    "exclude_threshold": (
        "排除文件阈值",
        "相似片段两侧如果都能以该阈值匹配到招标文件、模板等排除文件，就会标为已排除。默认 0.86。"
        "通常建议高于文本相似阈值。",
    ),
    "image_ahash_distance": (
        "图片近似距离",
        "图片 aHash 感知哈希的汉明距离阈值。默认 6。"
        "距离越小越严格；精确 SHA256 重复始终会被检测。",
    ),
    "sentence_delimiters": (
        "强分段符号",
        "遇到这些符号会优先切分比较片段。默认包含句号、问号、叹号和中英文分号。"
        "如果标书常用冒号或换行承载完整条款，可按需要补充。",
    ),
    "soft_delimiters": (
        "长句辅助切分",
        "当单个片段过长时，用这些符号辅助切分。默认包含逗号、顿号和冒号。"
        "它只用于长句拆分，不会替代强分段符号。",
    ),
}


class _ScrollableFrame(ttk.Frame):
    def __init__(self, master: tk.Misc, **kwargs: object) -> None:
        super().__init__(master, **kwargs)
        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient=VERTICAL, command=self.canvas.yview)
        self.content = ttk.Frame(self.canvas)
        self.window_id = self.canvas.create_window((0, 0), window=self.content, anchor="nw")

        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side=LEFT, fill=BOTH, expand=True)
        self.scrollbar.pack(side=RIGHT, fill="y")

        self.content.bind("<Configure>", self._sync_scrollregion)
        self.content.bind("<Enter>", self._bind_mousewheel)
        self.content.bind("<Leave>", self._unbind_mousewheel)
        self.canvas.bind("<Configure>", self._sync_width)
        self.canvas.bind("<Enter>", self._bind_mousewheel)
        self.canvas.bind("<Leave>", self._unbind_mousewheel)

    def _sync_scrollregion(self, _event: tk.Event[tk.Misc] | None = None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _sync_width(self, event: tk.Event[tk.Misc]) -> None:
        self.canvas.itemconfigure(self.window_id, width=event.width)

    def _bind_mousewheel(self, _event: tk.Event[tk.Misc]) -> None:
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mousewheel(self, _event: tk.Event[tk.Misc]) -> None:
        self.canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event: tk.Event[tk.Misc]) -> None:
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


class CheckSimApp(ttk.Frame):
    def __init__(self, master: tk.Tk) -> None:
        super().__init__(master, padding=12)
        self.master = master
        self.groups: list[dict[str, object]] = []
        self.exclude_files: list[str] = []
        self.last_report: str | None = None
        self.last_output_dir: str | None = None
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.is_running = False

        defaults = CheckOptions()
        self.min_chars = tk.StringVar(value=str(defaults.min_chars))
        self.min_words = tk.StringVar(value=str(defaults.min_words))
        self.similarity_threshold = tk.StringVar(value=str(defaults.similarity_threshold))
        self.exclude_threshold = tk.StringVar(value=str(defaults.exclude_threshold))
        self.image_ahash_distance = tk.StringVar(value=str(defaults.image_ahash_distance))
        self.sentence_delimiters = tk.StringVar(value=defaults.sentence_delimiters)
        self.soft_delimiters = tk.StringVar(value=defaults.soft_delimiters)
        self.similarity_backend = tk.StringVar(value=defaults.similarity_backend)
        self.status = tk.StringVar(value="就绪")

        self._build()
        self._refresh_history()

    def _build(self) -> None:
        self.master.title("标书/文件查重工具")
        self.master.geometry("1180x760")
        self.master.minsize(980, 640)
        self.pack(fill=BOTH, expand=True)

        header = ttk.Frame(self)
        header.pack(fill="x", pady=(0, 10))
        ttk.Label(header, text="标书/文件查重工具", font=("Microsoft YaHei UI", 16, "bold")).pack(side=LEFT)
        ttk.Label(header, textvariable=self.status, foreground="#0f766e").pack(side=RIGHT)

        body = ttk.PanedWindow(self, orient="horizontal")
        body.pack(fill=BOTH, expand=True)

        left_scroll = _ScrollableFrame(body)
        self.left_scroll = left_scroll
        left = left_scroll.content
        right = ttk.Frame(body, padding=(8, 0, 0, 0))
        body.add(left_scroll, weight=3)
        body.add(right, weight=2)

        self._build_groups(left)
        self._build_excludes(left)
        self._build_keywords_and_options(left)
        self._build_run_panel(right)
        self._build_log_panel(right)
        self._build_history(right)

    def _build_groups(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="1. 投标文件分组")
        frame.pack(fill="x", expand=False, pady=(0, 8))
        self.group_tree = ttk.Treeview(frame, columns=("name", "count", "files"), show="headings", height=7)
        self.group_tree.heading("name", text="公司/分组")
        self.group_tree.heading("count", text="文件数")
        self.group_tree.heading("files", text="文件")
        self.group_tree.column("name", width=120, stretch=False)
        self.group_tree.column("count", width=60, stretch=False, anchor="center")
        self.group_tree.column("files", width=420)
        self.group_tree.pack(fill=BOTH, expand=True, padx=8, pady=8)

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(buttons, text="添加文件组", command=self._add_file_group).pack(side=LEFT, padx=(0, 6))
        ttk.Button(buttons, text="按目录添加组", command=self._add_folder_group).pack(side=LEFT, padx=(0, 6))
        ttk.Button(buttons, text="重命名", command=self._rename_group).pack(side=LEFT, padx=(0, 6))
        ttk.Button(buttons, text="删除选中组", command=self._remove_group).pack(side=LEFT)

        batch_buttons = ttk.Frame(frame)
        batch_buttons.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(batch_buttons, text="批量单文件成组", command=self._add_single_file_groups).pack(side=LEFT, padx=(0, 6))
        ttk.Button(batch_buttons, text="批量文件夹成组", command=self._add_parent_folder_groups).pack(side=LEFT)

    def _build_excludes(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="2. 可选排除文件 B")
        frame.pack(fill="both", expand=False, pady=(0, 8))
        self.exclude_list = tk.Listbox(frame, height=4)
        self.exclude_list.pack(fill="x", padx=8, pady=8)
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(buttons, text="添加排除文件", command=self._add_exclude_files).pack(side=LEFT, padx=(0, 6))
        ttk.Button(buttons, text="按目录添加", command=self._add_exclude_folder).pack(side=LEFT, padx=(0, 6))
        ttk.Button(buttons, text="删除选中", command=self._remove_exclude).pack(side=LEFT)

    def _build_keywords_and_options(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="3. 关键词与检测参数")
        frame.pack(fill="x", expand=False)
        keyword_header = ttk.Frame(frame)
        keyword_header.pack(fill="x", padx=8, pady=(8, 2))
        ttk.Label(keyword_header, text="重要关键词/正则，每行一条；正则请用 re: 开头").pack(side=LEFT)
        ttk.Button(
            keyword_header,
            text="?",
            width=2,
            command=lambda: self._show_param_help("keywords"),
        ).pack(side=LEFT, padx=(6, 0))
        self.keyword_text = tk.Text(frame, height=4, wrap="word")
        self.keyword_text.pack(fill="x", padx=8, pady=(0, 8))

        options = ttk.Frame(frame)
        options.pack(fill="x", padx=8, pady=(0, 8))
        self._option_entry(options, "中文/混合最短字符", self.min_chars, 0, 0, "min_chars")
        self._option_entry(options, "英文最短词数", self.min_words, 0, 3, "min_words")
        self._option_entry(options, "文本相似阈值", self.similarity_threshold, 1, 0, "similarity_threshold")
        self._option_entry(options, "排除文件阈值", self.exclude_threshold, 1, 3, "exclude_threshold")
        self._option_entry(options, "图片近似距离", self.image_ahash_distance, 2, 0, "image_ahash_distance")
        self._option_entry(options, "强分段符号", self.sentence_delimiters, 2, 3, "sentence_delimiters")
        self._option_entry(options, "长句辅助切分", self.soft_delimiters, 3, 0, "soft_delimiters")
        options.columnconfigure(1, weight=1)
        options.columnconfigure(4, weight=1)

    def _build_run_panel(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="4. 检测与报告")
        frame.pack(fill="x", pady=(0, 8))
        self.run_button = ttk.Button(frame, text="开始检测", command=self._start_check)
        self.run_button.pack(side=LEFT, padx=8, pady=10)
        ttk.Button(frame, text="打开报告", command=self._open_report).pack(side=LEFT, padx=(0, 6))
        ttk.Button(frame, text="打开输出目录", command=self._open_output_dir).pack(side=LEFT, padx=(0, 6))
        ttk.Button(frame, text="帮助", command=self._show_help).pack(side=LEFT, padx=(0, 6))
        ttk.Button(frame, text="保存配置", command=self._save_config).pack(side=LEFT, padx=(0, 6))
        ttk.Button(frame, text="加载配置", command=self._load_config).pack(side=LEFT, padx=(0, 6))

    def _build_log_panel(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="进度日志")
        frame.pack(fill=BOTH, expand=True, pady=(0, 8))
        self.log_text = tk.Text(frame, height=14, wrap="word", state="disabled")
        scrollbar = ttk.Scrollbar(frame, orient=VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(side=LEFT, fill=BOTH, expand=True, padx=(8, 0), pady=8)
        scrollbar.pack(side=RIGHT, fill="y", padx=(0, 8), pady=8)

    def _build_history(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="历史报告")
        frame.pack(fill="both", expand=False)
        self.history_list = tk.Listbox(frame, height=7)
        self.history_list.pack(fill="x", padx=8, pady=8)
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(buttons, text="刷新", command=self._refresh_history).pack(side=LEFT, padx=(0, 6))
        ttk.Button(buttons, text="打开选中报告", command=self._open_selected_history).pack(side=LEFT, padx=(0, 6))
        ttk.Button(buttons, text="打开目录", command=self._open_selected_history_dir).pack(side=LEFT, padx=(0, 6))
        ttk.Button(buttons, text="复制路径", command=self._copy_selected_history_path).pack(side=LEFT, padx=(0, 6))
        ttk.Button(buttons, text="删除记录", command=self._delete_selected_history).pack(side=LEFT)

    def _option_entry(self, parent: ttk.Frame, label: str, variable: tk.StringVar, row: int, column: int, help_key: str) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=column, sticky="w", padx=(0, 6), pady=4)
        ttk.Entry(parent, textvariable=variable, width=12).grid(row=row, column=column + 1, sticky="ew", padx=(0, 4), pady=4)
        ttk.Button(parent, text="?", width=2, command=lambda: self._show_param_help(help_key)).grid(
            row=row,
            column=column + 2,
            sticky="w",
            padx=(0, 14),
            pady=4,
        )

    def _show_param_help(self, key: str) -> None:
        title, text = PARAM_HELP.get(key, ("参数说明", "暂无说明。"))
        messagebox.showinfo(title, text, parent=self.master)

    def _add_file_group(self) -> None:
        files = filedialog.askopenfilenames(
            title="选择一组投标文件",
            filetypes=SUPPORTED_FILETYPES,
        )
        if not files:
            return
        default_name = f"公司{len(self.groups) + 1}"
        name = simpledialog.askstring("分组名称", "请输入公司/分组名称", initialvalue=default_name, parent=self.master)
        if not name:
            return
        added, skipped = self._append_groups([{"name": name.strip(), "files": list(files)}])
        if skipped:
            messagebox.showinfo("未重复添加", "相同文件组成的分组已存在，本次没有重复添加。")
        elif added:
            self._refresh_groups()

    def _add_folder_group(self) -> None:
        folder = filedialog.askdirectory(title="选择一个公司的投标文件目录")
        if not folder:
            return
        folder_path = Path(folder)
        files = _find_supported_files(folder_path)
        if not files:
            messagebox.showwarning("未找到文件", "该目录下没有 .docx、.doc、.wps、.pdf、.md 或 .txt 文件。")
            return
        name = simpledialog.askstring("分组名称", "请输入公司/分组名称", initialvalue=folder_path.name, parent=self.master)
        if not name:
            return
        added, skipped = self._append_groups([{"name": name.strip(), "files": files}])
        if skipped:
            messagebox.showinfo("未重复添加", "相同文件组成的分组已存在，本次没有重复添加。")
        elif added:
            self._refresh_groups()

    def _add_single_file_groups(self) -> None:
        files = filedialog.askopenfilenames(
            title="批量选择投标文件，每个文件自动作为一个公司/分组",
            filetypes=SUPPORTED_FILETYPES,
        )
        if not files:
            return
        groups = _groups_from_single_files(files)
        added, skipped = self._append_groups(groups)
        if added:
            self._refresh_groups()
            message = f"已按单文件模式添加 {added} 个分组。"
            if skipped:
                message += f"\n跳过 {skipped} 个已存在的重复分组。"
            messagebox.showinfo("批量添加完成", message)
        else:
            messagebox.showwarning("未添加分组", "没有新增分组，所选文件可能已经添加过。")

    def _add_parent_folder_groups(self) -> None:
        proceed = messagebox.askokcancel(
            "批量文件夹成组",
            "请选择“包含多个公司文件夹的上级目录”。\n\n"
            "程序会把该目录下的每个直接子文件夹作为一个公司/分组，"
            "并递归导入子文件夹中的 .docx、.doc、.wps、.pdf、.md、.txt 文件。\n\n"
            "如果只想添加某一家公司的单个目录，请使用“按目录添加组”。",
            parent=self.master,
        )
        if not proceed:
            return
        folder = filedialog.askdirectory(title="选择包含多个公司文件夹的上级目录")
        if not folder:
            return
        groups, empty_folders = _groups_from_company_folders(Path(folder))
        if not groups:
            messagebox.showwarning("未找到文件", "该目录的直接子文件夹中没有 .docx、.doc、.wps、.pdf、.md 或 .txt 文件。")
            return
        added, skipped = self._append_groups(groups)
        if added:
            self._refresh_groups()
            message = f"已按文件夹模式添加 {added} 个分组。"
            if skipped:
                message += f"\n跳过 {skipped} 个已存在的重复分组。"
            if empty_folders:
                message += f"\n另有 {len(empty_folders)} 个子文件夹未找到支持文件，已跳过。"
            messagebox.showinfo("批量添加完成", message)
        else:
            messagebox.showwarning("未添加分组", "没有新增分组，所选子文件夹可能已经添加过。")

    def _append_groups(self, groups: list[dict[str, object]]) -> tuple[int, int]:
        existing_names = {str(group["name"]) for group in self.groups}
        existing_signatures = {_group_file_signature(group) for group in self.groups}
        added = 0
        skipped = 0
        for group in groups:
            files = [normalize_path(file) for file in group.get("files", [])]  # type: ignore[arg-type]
            if not files:
                continue
            signature = tuple(sorted(files))
            if signature in existing_signatures:
                skipped += 1
                continue
            name = _unique_group_name(str(group.get("name") or f"公司{len(self.groups) + 1}"), existing_names)
            self.groups.append({"name": name, "files": files})
            existing_names.add(name)
            existing_signatures.add(signature)
            added += 1
        return added, skipped

    def _rename_group(self) -> None:
        selected = self.group_tree.selection()
        if not selected:
            return
        index = int(selected[0])
        current = str(self.groups[index]["name"])
        name = simpledialog.askstring("重命名", "请输入新的公司/分组名称", initialvalue=current, parent=self.master)
        if not name:
            return
        self.groups[index]["name"] = name.strip()
        self._refresh_groups()

    def _remove_group(self) -> None:
        selected = self.group_tree.selection()
        for item in reversed(selected):
            del self.groups[int(item)]
        self._refresh_groups()

    def _add_exclude_files(self) -> None:
        files = filedialog.askopenfilenames(
            title="选择排除文件",
            filetypes=SUPPORTED_FILETYPES,
        )
        self._add_exclude_paths(files)

    def _add_exclude_folder(self) -> None:
        folder = filedialog.askdirectory(title="选择排除文件目录")
        if folder:
            self._add_exclude_paths(_find_supported_files(Path(folder)))

    def _add_exclude_paths(self, paths: list[str] | tuple[str, ...]) -> None:
        known = set(self.exclude_files)
        for path in paths:
            normalized = normalize_path(path)
            if normalized not in known:
                self.exclude_files.append(normalized)
                known.add(normalized)
        self._refresh_excludes()

    def _remove_exclude(self) -> None:
        selected = list(self.exclude_list.curselection())
        for index in reversed(selected):
            del self.exclude_files[index]
        self._refresh_excludes()

    def _refresh_groups(self) -> None:
        for item in self.group_tree.get_children():
            self.group_tree.delete(item)
        for index, group in enumerate(self.groups):
            files = [Path(str(file)).name for file in group["files"]]  # type: ignore[index]
            self.group_tree.insert("", END, iid=str(index), values=(group["name"], len(files), "；".join(files)))

    def _refresh_excludes(self) -> None:
        self.exclude_list.delete(0, END)
        for file in self.exclude_files:
            self.exclude_list.insert(END, Path(file).name)

    def _start_check(self) -> None:
        try:
            config = self._collect_config()
        except ValueError as exc:
            messagebox.showerror("参数错误", str(exc))
            return
        output_dir = _output_root() / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self._log("开始检测...")
        self._set_running(True, "检测中")
        thread = threading.Thread(target=self._worker, args=(config, output_dir), daemon=True)
        thread.start()
        self.after(120, self._poll_events)

    def _worker(self, config: dict[str, object], output_dir: Path) -> None:
        try:
            result = run_check(config, output_dir, lambda message: self.events.put(("log", message)))
            self.events.put(("done", result))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def _poll_events(self) -> None:
        try:
            while True:
                try:
                    kind, payload = self.events.get_nowait()
                except queue.Empty:
                    break
                if kind == "log":
                    self._log(str(payload))
                elif kind == "done":
                    result = payload  # type: ignore[assignment]
                    output_files = result.get("output_files", {})  # type: ignore[union-attr]
                    self.last_report = output_files.get("report_html")
                    self.last_output_dir = output_files.get("output_dir")
                    self._set_running(False, "完成")
                    self._log(f"报告已生成: {self.last_report}")
                    self._refresh_history()
                    self._auto_open_report()
                    messagebox.showinfo("完成", _completion_message(result))
                elif kind == "error":
                    self._set_running(False, "出错")
                    self._log(f"错误: {payload}")
                    messagebox.showerror("检测失败", str(payload))
        except Exception as exc:
            self._set_running(False, "出错")
            self._log(f"界面处理结果时出错: {exc}")
            messagebox.showerror("界面错误", f"检测可能已完成，但界面处理结果时出错：{exc}")
            return
        if self.is_running:
            self.after(120, self._poll_events)

    def _set_running(self, running: bool, status: str) -> None:
        self.is_running = running
        self.status.set(status)
        self.run_button.configure(state="disabled" if running else "normal")

    def _collect_config(self) -> dict[str, object]:
        return self._build_config(require_min_groups=True)

    def _build_config(self, require_min_groups: bool) -> dict[str, object]:
        if len(self.groups) < 2:
            if require_min_groups:
                raise ValueError("至少需要添加 2 个投标文件分组。")
        keywords = [line.strip() for line in self.keyword_text.get("1.0", END).splitlines() if line.strip()]
        options = {
            "min_chars": _parse_int(self.min_chars.get(), "中文/混合最短字符"),
            "min_words": _parse_int(self.min_words.get(), "英文最短词数"),
            "similarity_threshold": _parse_float(self.similarity_threshold.get(), "文本相似阈值"),
            "exclude_threshold": _parse_float(self.exclude_threshold.get(), "排除文件阈值"),
            "image_ahash_distance": _parse_int(self.image_ahash_distance.get(), "图片近似距离"),
            "sentence_delimiters": self.sentence_delimiters.get(),
            "soft_delimiters": self.soft_delimiters.get(),
            "similarity_backend": self.similarity_backend.get().strip() or "local_ngrams",
        }
        options = CheckOptions.from_dict(options).to_dict()
        return {
            "groups": [{"name": str(group.get("name", "")), "files": list(group.get("files", []))} for group in self.groups],
            "exclude_files": list(self.exclude_files),
            "keywords": keywords,
            "options": options,
        }

    def _save_config(self) -> None:
        try:
            config = self._build_config(require_min_groups=False)
        except ValueError as exc:
            messagebox.showerror("参数错误", str(exc))
            return
        path = filedialog.asksaveasfilename(
            title="保存检测配置",
            defaultextension=".json",
            initialfile="case.json",
            filetypes=[("JSON 配置", "*.json"), ("所有文件", "*.*")],
        )
        if not path:
            return
        Path(path).write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        self._log(f"配置已保存: {path}")
        messagebox.showinfo("保存完成", "当前分组、排除文件、关键词和参数已保存。")

    def _load_config(self) -> None:
        path = filedialog.askopenfilename(
            title="加载检测配置",
            filetypes=[("JSON 配置", "*.json"), ("所有文件", "*.*")],
        )
        if not path:
            return
        try:
            raw = load_config(path)
            options = CheckOptions.from_dict(raw.get("options") or {})
        except Exception as exc:
            messagebox.showerror("加载失败", f"无法读取配置：{exc}")
            return

        groups: list[dict[str, object]] = []
        for index, group in enumerate(raw.get("groups") or [], start=1):
            files = [normalize_path(file) for file in group.get("files", [])]
            if files:
                groups.append({"name": str(group.get("name") or f"公司{index}"), "files": files})
        self.groups = groups
        self.exclude_files = [normalize_path(file) for file in raw.get("exclude_files") or []]
        self.keyword_text.delete("1.0", END)
        self.keyword_text.insert("1.0", "\n".join(str(item) for item in raw.get("keywords") or []))
        self._apply_options_to_vars(options)
        self._refresh_groups()
        self._refresh_excludes()
        self._log(f"配置已加载: {path}")
        messagebox.showinfo("加载完成", "配置已加载到界面，可继续调整后检测。")

    def _apply_options_to_vars(self, options: CheckOptions) -> None:
        self.min_chars.set(str(options.min_chars))
        self.min_words.set(str(options.min_words))
        self.similarity_threshold.set(str(options.similarity_threshold))
        self.exclude_threshold.set(str(options.exclude_threshold))
        self.image_ahash_distance.set(str(options.image_ahash_distance))
        self.sentence_delimiters.set(options.sentence_delimiters)
        self.soft_delimiters.set(options.soft_delimiters)
        self.similarity_backend.set(options.similarity_backend)

    def _open_report(self) -> None:
        if not self.last_report:
            messagebox.showinfo("暂无报告", "请先完成一次检测，或在历史报告中打开。")
            return
        _open_path(self.last_report)

    def _auto_open_report(self) -> None:
        if not self.last_report:
            return
        try:
            _open_path(self.last_report)
            self._log("已自动打开报告。")
        except Exception as exc:
            self._log(f"自动打开报告失败，可手动点击“打开报告”: {exc}")

    def _open_output_dir(self) -> None:
        if not self.last_output_dir:
            messagebox.showinfo("暂无输出目录", "请先完成一次检测。")
            return
        _open_path(self.last_output_dir)

    def _show_help(self) -> None:
        win = tk.Toplevel(self.master)
        win.title("使用帮助")
        win.geometry("760x620")
        win.minsize(620, 460)
        win.transient(self.master)

        text = tk.Text(win, wrap="word", padx=14, pady=12)
        scrollbar = ttk.Scrollbar(win, orient=VERTICAL, command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        text.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill="y")
        text.insert("1.0", _help_text())
        text.configure(state="disabled")
        text.focus_set()

    def _refresh_history(self) -> None:
        if not hasattr(self, "history_list"):
            return
        self.history_list.delete(0, END)
        reports = sorted(_output_root().glob("run_*/report.html"), reverse=True)
        for report in reports[:30]:
            self.history_list.insert(END, str(report))

    def _open_selected_history(self) -> None:
        path = self._selected_history_path()
        if not path:
            return
        self.last_report = str(path)
        self.last_output_dir = str(path.parent)
        _open_path(str(path))

    def _open_selected_history_dir(self) -> None:
        path = self._selected_history_path()
        if not path:
            return
        _open_path(str(path.parent))

    def _copy_selected_history_path(self) -> None:
        path = self._selected_history_path()
        if not path:
            return
        self.master.clipboard_clear()
        self.master.clipboard_append(str(path))
        self.status.set("已复制报告路径")
        self._log(f"已复制报告路径: {path}")

    def _delete_selected_history(self) -> None:
        path = self._selected_history_path()
        if not path:
            return
        target = path.parent
        if not _is_history_run_dir(target):
            messagebox.showwarning("无法删除", "只能删除当前项目 outputs/run_* 下的历史报告。")
            return
        if not messagebox.askyesno("删除历史报告", f"确认删除该历史输出目录？\n{target}", parent=self.master):
            return
        try:
            shutil.rmtree(target)
        except Exception as exc:
            messagebox.showerror("删除失败", str(exc))
            return
        self._refresh_history()
        self._log(f"已删除历史输出目录: {target}")

    def _selected_history_path(self) -> Path | None:
        selected = self.history_list.curselection()
        if not selected:
            return None
        return Path(self.history_list.get(selected[0])).resolve()

    def _log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert(END, f"{datetime.now().strftime('%H:%M:%S')}  {message}\n")
        self.log_text.see(END)
        self.log_text.configure(state="disabled")


def _find_supported_files(folder: Path) -> list[str]:
    files: list[str] = []
    for path in folder.rglob("*"):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS and not path.name.startswith("~$"):
            files.append(normalize_path(path))
    return sorted(files)


def _groups_from_single_files(paths: list[str] | tuple[str, ...]) -> list[dict[str, object]]:
    files = sorted({normalize_path(path) for path in paths})
    stems: dict[str, int] = {}
    for file in files:
        stems[Path(file).stem] = stems.get(Path(file).stem, 0) + 1

    groups: list[dict[str, object]] = []
    for file in files:
        path = Path(file)
        name = path.stem
        if stems.get(path.stem, 0) > 1:
            name = f"{path.parent.name}_{path.stem}"
        groups.append({"name": name, "files": [file]})
    return groups


def _groups_from_company_folders(parent: Path) -> tuple[list[dict[str, object]], list[str]]:
    groups: list[dict[str, object]] = []
    empty_folders: list[str] = []
    for folder in sorted((path for path in parent.iterdir() if path.is_dir()), key=lambda path: path.name.lower()):
        files = _find_supported_files(folder)
        if files:
            groups.append({"name": folder.name, "files": files})
        else:
            empty_folders.append(folder.name)
    return groups, empty_folders


def _unique_group_name(name: str, existing_names: set[str]) -> str:
    base = name.strip() or "未命名分组"
    if base not in existing_names:
        return base
    index = 2
    while f"{base}({index})" in existing_names:
        index += 1
    return f"{base}({index})"


def _group_file_signature(group: dict[str, object]) -> tuple[str, ...]:
    files = group.get("files", [])
    if not isinstance(files, list):
        return tuple()
    return tuple(sorted(normalize_path(str(file)) for file in files))


def _is_history_run_dir(path: Path) -> bool:
    try:
        outputs = _output_root().resolve()
        resolved = path.resolve()
    except OSError:
        return False
    return resolved.name.startswith("run_") and outputs in resolved.parents


def _is_frozen_macos() -> bool:
    return sys.platform == "darwin" and bool(getattr(sys, "frozen", False))


def _output_root() -> Path:
    if _is_frozen_macos():
        return Path.home() / "Documents" / "标书文件查重工具输出"
    return Path.cwd() / "outputs"


def _completion_message(result: object) -> str:
    if not isinstance(result, dict):
        return "检测完成，报告已生成。"
    stats = result.get("stats", {})
    output_files = result.get("output_files", {})
    if not isinstance(stats, dict) or not isinstance(output_files, dict):
        return "检测完成，报告已生成。"
    lines = [
        "检测完成，报告已生成并已尝试自动打开。",
        f"输出目录：{output_files.get('output_dir', '')}",
        f"异常片段：{stats.get('similar_match_count', 0)}",
        f"已排除片段：{stats.get('excluded_match_count', 0)}",
    ]
    return "\n".join(lines)


def _help_text() -> str:
    return "\n".join(
        [
            "标书/文件查重工具操作教程",
            "",
            "一、准备文件",
            "1. 每家公司的投标文件可以单独成一个文件，也可以放到一个文件夹。",
            "2. 支持 .docx、.doc、.wps、.pdf、.md、.txt；PDF 会优先读取可复制文本，Markdown 附带的本地图片会参与图片重复检测，txt 按纯文本解析。",
            "3. .doc/.wps 不会直接改原文件，程序会先转成临时 .docx 再解析。",
            "4. Windows 下按 WPS、Microsoft Office、LibreOffice 顺序尝试转换；Linux/macOS 下使用 LibreOffice。",
            "5. 桌面打包版内置 PaddleOCR/PP-OCRv6，可处理扫描版 PDF；源码运行时需安装 OCR 依赖。",
            "6. 如果旧格式转换失败，请先在 WPS/Word/LibreOffice 中另存为 .docx 再导入。",
            "",
            "二、添加投标文件分组",
            "1. 点击“添加文件组”，选择某一家公司的一批文件，然后输入公司/分组名称。",
            "2. 点击“按目录添加组”，可以直接选择一个公司目录，程序会递归查找支持的文件。",
            "3. 点击“批量单文件成组”，可以一次选择多个文件；每个文件会自动成为一个公司/分组。",
            "4. 点击“批量文件夹成组”，选择包含多个公司文件夹的上级目录；每个直接子文件夹及其子目录会自动成为一个公司/分组。",
            "5. 批量导入时，分组名会优先使用文件名或文件夹名；如重名会自动追加序号，导入后仍可重命名。",
            "6. 至少需要 2 个公司/分组才可以开始检测。",
            "7. 同一组内的文件不会互相比对，只会和其他公司/分组比对。",
            "",
            "三、添加可选排除文件 B",
            "1. 排除文件适合放招标文件、模板、统一格式要求等允许各家共同引用的材料。",
            "2. 如果两家公司相似的片段两侧都能高相似匹配到排除文件，该片段会标为“已排除”。",
            "3. 已排除片段仍会进入报告，颜色更淡，便于复核。",
            "",
            "四、填写重要关键词/正则",
            "1. 每行一条规则，例如公司名称、项目经理姓名、手机号或统一社会信用代码。",
            "2. 普通文本直接写；正则表达式以 re: 开头，例如 re:1[3-9]\\d{9}。",
            "3. 关键词检测不受短文本过滤影响；同一规则命中 2 个及以上公司/分组会判为异常。",
            "",
            "五、设置参数",
            "1. 中文/混合最短字符：低于该长度的短句不参与相似度比对，默认 10。",
            "2. 英文最短词数：英文片段低于该词数不参与相似度比对，默认 8。",
            "3. 文本相似阈值：越高越严格；默认 0.78，适合发现轻微改写。",
            "4. 排除文件阈值：默认 0.86，建议比文本相似阈值更高。",
            "5. 强分段符号：遇到这些符号会优先切分句子，默认包含句号、问号、叹号、分号。",
            "6. 长句辅助切分：长句超过限制时用这些符号辅助切开，默认包含逗号、顿号、冒号。",
            "7. 每个参数右侧的 ? 可查看具体说明。",
            "",
            "六、开始检测和查看报告",
            "1. 点击“开始检测”，右侧日志会显示解析、索引、相似计算和报告生成进度。",
            "2. 检测完成后会自动打开本次 report.html。",
            "3. 也可以点击“打开报告”“打开输出目录”，或在“历史报告”里打开旧报告。",
            "4. report.html 是总览；compare_*.html 是两组文件左右对照页。",
            "5. 左右对照页支持点击高亮片段跳到对侧对应片段；角标数字表示对侧有多处相似文本。",
            "6. 高亮颜色越深表示相似度越高；已排除片段颜色更淡。",
            "7. “保存配置/加载配置”可以复用当前分组、排除文件、关键词和参数。",
            "8. 历史报告支持打开目录、复制路径和删除当前项目 outputs/run_* 下的旧记录。",
            "",
            "七、命令行与 Skill",
            "1. 命令行入口：python -m checksim.cli --config case.json --output outputs/run_demo。",
            "2. 配置 JSON 字段包括 groups、exclude_files、keywords、options。",
            "3. Skill 会调用同一套 CLI 和核心算法，适合在 Win/Linux Agent 环境中自动生成配置并运行查重。",
            "4. 所有 HTML 报告的 CSS/JS 均内嵌，适合内网离线打开。",
        ]
    )


def _parse_int(value: str, label: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{label} 必须是整数。") from exc


def _parse_float(value: str, label: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise ValueError(f"{label} 必须是数字。") from exc
    if not 0 < number <= 1:
        raise ValueError(f"{label} 必须在 0 到 1 之间。")
    return number


def _open_path(path: str) -> None:
    if os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def main() -> None:
    root = tk.Tk()
    try:
        ttk.Style().theme_use("clam")
    except tk.TclError:
        pass
    CheckSimApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
