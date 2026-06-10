from __future__ import annotations

import os
import queue
import threading
from datetime import datetime
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, VERTICAL, filedialog, messagebox, simpledialog
import tkinter as tk
from tkinter import ttk

from .engine import run_check
from .models import CheckOptions, SUPPORTED_EXTENSIONS, normalize_path


SUPPORTED_FILETYPES = [
    ("支持的文件", "*.docx *.doc *.wps *.md"),
    ("Word/WPS", "*.docx *.doc *.wps"),
    ("Markdown", "*.md"),
]


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
        ttk.Label(frame, text="重要关键词/正则，每行一条；正则请用 re: 开头").pack(anchor="w", padx=8, pady=(8, 2))
        self.keyword_text = tk.Text(frame, height=4, wrap="word")
        self.keyword_text.pack(fill="x", padx=8, pady=(0, 8))

        options = ttk.Frame(frame)
        options.pack(fill="x", padx=8, pady=(0, 8))
        self._option_entry(options, "中文/混合最短字符", self.min_chars, 0, 0)
        self._option_entry(options, "英文最短词数", self.min_words, 0, 2)
        self._option_entry(options, "文本相似阈值", self.similarity_threshold, 1, 0)
        self._option_entry(options, "排除文件阈值", self.exclude_threshold, 1, 2)
        self._option_entry(options, "图片近似距离", self.image_ahash_distance, 2, 0)
        self._option_entry(options, "强分段符号", self.sentence_delimiters, 2, 2)
        self._option_entry(options, "长句辅助切分", self.soft_delimiters, 3, 0)
        options.columnconfigure(1, weight=1)
        options.columnconfigure(3, weight=1)

    def _build_run_panel(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="4. 检测与报告")
        frame.pack(fill="x", pady=(0, 8))
        self.run_button = ttk.Button(frame, text="开始检测", command=self._start_check)
        self.run_button.pack(side=LEFT, padx=8, pady=10)
        ttk.Button(frame, text="打开报告", command=self._open_report).pack(side=LEFT, padx=(0, 6))
        ttk.Button(frame, text="打开输出目录", command=self._open_output_dir).pack(side=LEFT, padx=(0, 6))
        ttk.Button(frame, text="帮助", command=self._show_help).pack(side=LEFT, padx=(0, 6))

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
        ttk.Button(buttons, text="打开选中报告", command=self._open_selected_history).pack(side=LEFT)

    def _option_entry(self, parent: ttk.Frame, label: str, variable: tk.StringVar, row: int, column: int) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=column, sticky="w", padx=(0, 6), pady=4)
        ttk.Entry(parent, textvariable=variable, width=12).grid(row=row, column=column + 1, sticky="ew", padx=(0, 14), pady=4)

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
        self.groups.append({"name": name.strip(), "files": [normalize_path(file) for file in files]})
        self._refresh_groups()

    def _add_folder_group(self) -> None:
        folder = filedialog.askdirectory(title="选择一个公司的投标文件目录")
        if not folder:
            return
        folder_path = Path(folder)
        files = _find_supported_files(folder_path)
        if not files:
            messagebox.showwarning("未找到文件", "该目录下没有 .docx、.doc、.wps 或 .md 文件。")
            return
        name = simpledialog.askstring("分组名称", "请输入公司/分组名称", initialvalue=folder_path.name, parent=self.master)
        if not name:
            return
        self.groups.append({"name": name.strip(), "files": [normalize_path(file) for file in files]})
        self._refresh_groups()

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
        output_dir = Path.cwd() / "outputs" / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
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
                    messagebox.showinfo("完成", "检测完成，报告已生成。")
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
        if len(self.groups) < 2:
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
        }
        return {
            "groups": self.groups,
            "exclude_files": self.exclude_files,
            "keywords": keywords,
            "options": options,
        }

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
        reports = sorted((Path.cwd() / "outputs").glob("run_*/report.html"), reverse=True)
        for report in reports[:30]:
            self.history_list.insert(END, str(report))

    def _open_selected_history(self) -> None:
        selected = self.history_list.curselection()
        if not selected:
            return
        path = self.history_list.get(selected[0])
        self.last_report = path
        self.last_output_dir = str(Path(path).parent)
        _open_path(path)

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


def _help_text() -> str:
    return "\n".join(
        [
            "标书/文件查重工具操作教程",
            "",
            "一、准备文件",
            "1. 每家公司的投标文件放到一个文件夹，或在添加文件组时一次选择同一公司的多个文件。",
            "2. 支持 .docx、.doc、.wps、.md；Markdown 附带的本地图片会参与图片重复检测。",
            "3. .doc/.wps 不会直接改原文件，程序会先转成临时 .docx 再解析。",
            "4. Windows 下按 WPS、Microsoft Office、LibreOffice 顺序尝试转换；Linux/macOS 下使用 LibreOffice。",
            "5. 如果旧格式转换失败，请先在 WPS/Word/LibreOffice 中另存为 .docx 再导入。",
            "",
            "二、添加投标文件分组",
            "1. 点击“添加文件组”，选择某一家公司的一批文件，然后输入公司/分组名称。",
            "2. 点击“按目录添加组”，可以直接选择一个公司目录，程序会递归查找支持的文件。",
            "3. 至少需要 2 个公司/分组才可以开始检测。",
            "4. 同一组内的文件不会互相比对，只会和其他公司/分组比对。",
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
            "1. 中文/混合最短字符：低于该长度的短句不参与相似度比对，默认 20。",
            "2. 英文最短词数：英文片段低于该词数不参与相似度比对，默认 8。",
            "3. 文本相似阈值：越高越严格；默认 0.78，适合发现轻微改写。",
            "4. 排除文件阈值：默认 0.86，建议比文本相似阈值更高。",
            "5. 强分段符号：遇到这些符号会优先切分句子，默认包含句号、问号、叹号、分号。",
            "6. 长句辅助切分：长句超过限制时用这些符号辅助切开，默认包含逗号、顿号、冒号。",
            "",
            "六、开始检测和查看报告",
            "1. 点击“开始检测”，右侧日志会显示解析、索引、相似计算和报告生成进度。",
            "2. 检测完成后会自动打开本次 report.html。",
            "3. 也可以点击“打开报告”“打开输出目录”，或在“历史报告”里打开旧报告。",
            "4. report.html 是总览；compare_*.html 是两组文件左右对照页。",
            "5. 左右对照页支持点击高亮片段跳到对侧对应片段；角标数字表示对侧有多处相似文本。",
            "6. 高亮颜色越深表示相似度越高；已排除片段颜色更淡。",
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
    else:
        import subprocess

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
