import ctypes
import json
import subprocess
import threading
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "git_auto_commit_gui_config.json"
LOG_PATH = APP_DIR / "git_auto_commit_gui.log"

BG = "#090C14"
PANEL = "#171D2B"
PANEL_ALT = "#121822"
FIELD = "#0B1119"
FIELD_ACTIVE = "#0E1521"
BORDER = "#283346"
BORDER_SOFT = "#1B2331"
TEXT = "#ECF1F8"
TEXT_MUTED = "#8C98AE"
TEXT_FAINT = "#5C6780"
ACCENT = "#5B9BFF"
ACCENT_HOVER = "#7DB2FF"
ACCENT_SOFT = "#3A6FB8"
SUCCESS = "#27C08A"
WARN = "#F6B04A"
DANGER = "#EC6A6A"
SWITCH_OFF = "#394354"
SWITCH_KNOB = "#F7FAFC"


def enable_high_dpi():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def apply_dpi_scaling(root: tk.Tk):
    try:
        dpi = root.winfo_fpixels("1i")
        root.tk.call("tk", "scaling", max(1.0, min(2.2, dpi / 72.0)))
    except Exception:
        pass


@dataclass
class CommitItem:
    sha: str
    message: str
    timestamp: str


@dataclass
class RepoSnapshot:
    branch: str
    branch_state: str
    ahead: int
    behind: int
    dirty: bool
    changed_count: int
    commits: list[CommitItem]


class AutoCommitWorker(threading.Thread):
    def __init__(self, app, repo_path: Path, interval_seconds: int, prefix: str):
        super().__init__(daemon=True)
        self.app = app
        self.repo_path = repo_path
        self.interval_seconds = max(2, int(interval_seconds))
        self.prefix = prefix.strip() or "auto"
        self.stop_event = threading.Event()

    def stop(self):
        self.stop_event.set()

    def run(self):
        self.app.write_log(f"开始监控：{self.repo_path}")
        while not self.stop_event.is_set():
            try:
                if self.app.repo_has_blocking_git_marker(self.repo_path):
                    self.app.write_log("检测到 Git 正在执行其他操作，本轮 auto commit 已跳过。")
                else:
                    committed = self.app.auto_commit_once(self.repo_path, self.prefix)
                    if committed:
                        self.app.request_status_refresh()
            except Exception as exc:
                self.app.write_log(f"auto commit 出错：{exc}")
            self.stop_event.wait(self.interval_seconds)
        self.app.write_log("监控已停止。")


class AutoCommitApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Git 自动提交工具")
        self.root.geometry("1160x740")
        self.root.minsize(1000, 640)
        self.root.configure(bg=BG)

        self.git_lock = threading.Lock()
        self.log_lock = threading.Lock()
        self.auto_worker: AutoCommitWorker | None = None
        self.refresh_running = False
        self.busy = False
        self.log_window: tk.Toplevel | None = None
        self.log_text: tk.Text | None = None
        self.commit_rows: list[tk.Widget] = []
        self.last_commit_signature: list[tuple[str, str, str]] = []

        self.identity_inputs_dirty = False
        self.enabled_var = tk.BooleanVar(value=False)
        self.folder_var = tk.StringVar()
        self.github_var = tk.StringVar()
        self.username_var = tk.StringVar()
        self.email_var = tk.StringVar()
        self.interval_var = tk.IntVar(value=5)
        self.prefix_var = tk.StringVar(value="auto")
        self.push_history: list[str] = []

        self.mode_var = tk.StringVar(value="空闲")
        self.switch_text_var = tk.StringVar(value="已关闭")
        self.branch_var = tk.StringVar(value="branch -")
        self.worktree_var = tk.StringVar(value="工作区未连接")
        self.push_state_var = tk.StringVar(value="待 push：0 条 commit")
        self.tip_var = tk.StringVar(value="等待选择项目文件夹")
        self.push_history_var = tk.StringVar(value="暂无 push 记录")

        self.configure_style()
        self.build_ui()
        self.load_config()
        self.ensure_log_file()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.request_status_refresh()
        self.root.after(250, self.restore_auto_commit_state)

    def configure_style(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            ".",
            background=BG,
            foreground=TEXT,
            fieldbackground=FIELD,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            troughcolor=PANEL_ALT,
        )
        style.configure("Panel.TFrame", background=PANEL, relief="flat", borderwidth=0)
        style.configure("PanelAlt.TFrame", background=PANEL_ALT, relief="flat", borderwidth=0)
        style.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("CardTitle.TLabel", background=PANEL, foreground=TEXT, font=("Segoe UI Semibold", 11))
        style.configure("SectionTitle.TLabel", background=PANEL_ALT, foreground=TEXT, font=("Segoe UI Semibold", 11))
        style.configure("Muted.TLabel", background=PANEL, foreground=TEXT_MUTED, font=("Segoe UI", 9))
        style.configure("MutedAlt.TLabel", background=PANEL_ALT, foreground=TEXT_MUTED, font=("Segoe UI", 9))
        style.configure("Header.TLabel", background=PANEL_ALT, foreground=TEXT, font=("Segoe UI Semibold", 18))
        style.configure("HeaderSub.TLabel", background=PANEL_ALT, foreground=TEXT_MUTED, font=("Segoe UI", 10))
        style.configure("TEntry", foreground=TEXT, fieldbackground=FIELD, bordercolor=BORDER, insertcolor=TEXT, lightcolor=BORDER, darkcolor=BORDER, padding=9)
        style.map("TEntry", bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)], fieldbackground=[("focus", FIELD_ACTIVE)])
        style.configure("TSpinbox", foreground=TEXT, fieldbackground=FIELD, bordercolor=BORDER, arrowsize=14, padding=7, arrowcolor=TEXT_MUTED)
        style.map("TSpinbox", bordercolor=[("focus", ACCENT)], fieldbackground=[("focus", FIELD_ACTIVE)])
        style.configure("Primary.TButton", background=ACCENT, foreground="#08101F", bordercolor=ACCENT, focusthickness=0, padding=(16, 10), font=("Segoe UI Semibold", 9))
        style.map("Primary.TButton", background=[("active", ACCENT_HOVER), ("disabled", "#2A3550")], foreground=[("disabled", TEXT_FAINT)], bordercolor=[("active", ACCENT_HOVER)])
        style.configure("Secondary.TButton", background=PANEL_ALT, foreground=TEXT, bordercolor=BORDER, focusthickness=0, padding=(14, 10), font=("Segoe UI", 9))
        style.map("Secondary.TButton", background=[("active", "#222C3E"), ("disabled", "#161C28")], foreground=[("disabled", TEXT_FAINT)], bordercolor=[("active", ACCENT_SOFT)])
        style.configure("Small.TButton", background=PANEL_ALT, foreground=TEXT, bordercolor=BORDER, focusthickness=0, padding=(10, 6), font=("Segoe UI", 8))
        style.map("Small.TButton", background=[("active", "#222C3E")], bordercolor=[("active", ACCENT_SOFT)])
        style.configure("Warn.TButton", background="#5A3F18", foreground="#FCEAD0", bordercolor="#8A6320", focusthickness=0, padding=(14, 10), font=("Segoe UI Semibold", 9))
        style.map("Warn.TButton", background=[("active", "#6E4D1D"), ("disabled", "#2A2113")])
        style.configure("Vertical.TScrollbar", background=PANEL, troughcolor=PANEL_ALT, bordercolor=PANEL, arrowcolor=TEXT_MUTED, gripcount=0)
        style.configure("Horizontal.TScrollbar", background=PANEL, troughcolor=PANEL_ALT, bordercolor=PANEL, arrowcolor=TEXT_MUTED, gripcount=0)
        style.configure("TSeparator", background=BORDER_SOFT)
        style.configure("Card.TSeparator", background=BORDER_SOFT)

    def build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        shell = ttk.Frame(self.root, padding=22, style="PanelAlt.TFrame")
        shell.grid(row=0, column=0, sticky="nsew", padx=14, pady=14)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(3, weight=1)

        header = ttk.Frame(shell, style="PanelAlt.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Git 自动提交工具", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="auto commit · push · 仓库设置", style="HeaderSub.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))

        ttk.Separator(shell, orient="horizontal", style="Card.TSeparator").grid(row=1, column=0, sticky="ew", pady=(14, 0))

        top = ttk.Frame(shell, style="PanelAlt.TFrame")
        top.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        top.columnconfigure(0, weight=3, uniform="top")
        top.columnconfigure(1, weight=2, uniform="top")
        top.rowconfigure(0, weight=1)

        repo_card = ttk.Frame(top, padding=18, style="Panel.TFrame")
        repo_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        repo_card.columnconfigure(0, weight=1)
        repo_card.columnconfigure(1, weight=0)
        ttk.Label(repo_card, text="仓库设置", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")

        ttk.Label(repo_card, text="项目文件夹", style="Muted.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", pady=(14, 5))
        self.folder_entry = ttk.Entry(repo_card, textvariable=self.folder_var)
        self.folder_entry.grid(row=2, column=0, sticky="ew")
        self.browse_button = ttk.Button(repo_card, text="选择文件夹", style="Secondary.TButton", command=self.choose_folder)
        self.browse_button.grid(row=2, column=1, padx=(10, 0))

        ttk.Label(repo_card, text="GitHub 链接", style="Muted.TLabel").grid(row=3, column=0, columnspan=2, sticky="w", pady=(12, 5))
        self.github_entry = ttk.Entry(repo_card, textvariable=self.github_var)
        self.github_entry.grid(row=4, column=0, columnspan=2, sticky="ew")

        id_row = ttk.Frame(repo_card, style="Panel.TFrame")
        id_row.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        id_row.columnconfigure(0, weight=1)
        id_row.columnconfigure(1, weight=1)
        ttk.Label(id_row, text="Git 用户名", style="Muted.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 5))
        ttk.Label(id_row, text="Git 邮箱", style="Muted.TLabel").grid(row=0, column=1, sticky="w", pady=(0, 5), padx=(10, 0))
        self.username_entry = ttk.Entry(id_row, textvariable=self.username_var)
        self.username_entry.grid(row=1, column=0, sticky="ew")
        self.email_entry = ttk.Entry(id_row, textvariable=self.email_var)
        self.email_entry.grid(row=1, column=1, sticky="ew", padx=(10, 0))
        self.username_entry.bind("<KeyRelease>", self.on_identity_input_changed)
        self.email_entry.bind("<KeyRelease>", self.on_identity_input_changed)
        self.username_entry.bind("<<Paste>>", self.on_identity_input_changed)
        self.email_entry.bind("<<Paste>>", self.on_identity_input_changed)

        control_card = ttk.Frame(top, padding=18, style="Panel.TFrame")
        control_card.grid(row=0, column=1, sticky="nsew")
        control_card.columnconfigure(1, weight=1)
        ttk.Label(control_card, text="控制", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        self.mode_badge = tk.Label(
            control_card,
            textvariable=self.mode_var,
            bg=FIELD,
            fg=TEXT,
            font=("Segoe UI Semibold", 9),
            padx=12,
            pady=5,
            relief="flat",
            borderwidth=0,
        )
        self.mode_badge.grid(row=0, column=1, sticky="e")

        ttk.Separator(control_card, orient="horizontal", style="Card.TSeparator").grid(row=1, column=0, columnspan=2, sticky="ew", pady=(12, 10))

        switch_row = ttk.Frame(control_card, style="Panel.TFrame")
        switch_row.grid(row=2, column=0, columnspan=2, sticky="ew")
        switch_row.columnconfigure(1, weight=1)
        ttk.Label(switch_row, text="Auto Commit", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(switch_row, textvariable=self.switch_text_var, style="Muted.TLabel").grid(row=0, column=1, sticky="e", padx=(0, 10))
        self.switch_canvas = tk.Canvas(switch_row, width=60, height=32, bg=PANEL, highlightthickness=0, bd=0, cursor="hand2")
        self.switch_canvas.grid(row=0, column=2, sticky="e")
        self.switch_canvas.bind("<Button-1>", self.on_switch_click)
        self.render_switch()

        ttk.Label(control_card, text="间隔", style="Muted.TLabel").grid(row=3, column=0, sticky="w", pady=(12, 5))
        ttk.Label(control_card, text="Commit 前缀", style="Muted.TLabel").grid(row=3, column=1, sticky="w", pady=(12, 5))
        interval_row = ttk.Frame(control_card, style="Panel.TFrame")
        interval_row.grid(row=4, column=0, sticky="w")
        self.interval_spin = ttk.Spinbox(interval_row, from_=2, to=3600, width=6, textvariable=self.interval_var)
        self.interval_spin.grid(row=0, column=0, sticky="w")
        ttk.Label(interval_row, text="秒", style="Muted.TLabel").grid(row=0, column=1, padx=(6, 0))
        self.prefix_entry = ttk.Entry(control_card, textvariable=self.prefix_var, width=14)
        self.prefix_entry.grid(row=4, column=1, sticky="ew", padx=(10, 0))

        actions = ttk.Frame(control_card, style="Panel.TFrame")
        actions.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        for i in range(4):
            actions.columnconfigure(i, weight=1, uniform="btn")
        self.refresh_button = ttk.Button(actions, text="刷新", style="Secondary.TButton", command=self.request_status_refresh)
        self.refresh_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.commit_button = ttk.Button(actions, text="Commit", style="Secondary.TButton", command=self.commit_now)
        self.commit_button.grid(row=0, column=1, sticky="ew", padx=6)
        self.logs_button = ttk.Button(actions, text="日志", style="Secondary.TButton", command=self.open_log_window)
        self.logs_button.grid(row=0, column=2, sticky="ew", padx=6)
        self.push_button = ttk.Button(actions, text="Push", style="Primary.TButton", command=self.push_to_github)
        self.push_button.grid(row=0, column=3, sticky="ew", padx=(6, 0))

        repo_tools = ttk.Frame(control_card, style="Panel.TFrame")
        repo_tools.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        for i in range(3):
            repo_tools.columnconfigure(i, weight=1, uniform="tool")
        self.init_button = ttk.Button(repo_tools, text="git init", style="Warn.TButton", command=self.git_init_repo)
        self.init_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.identity_button = ttk.Button(repo_tools, text="保存身份", style="Secondary.TButton", command=self.save_identity)
        self.identity_button.grid(row=0, column=1, sticky="ew", padx=6)
        self.gitignore_button = ttk.Button(repo_tools, text="编辑 .gitignore", style="Secondary.TButton", command=self.open_gitignore_with)
        self.gitignore_button.grid(row=0, column=2, sticky="ew", padx=(6, 0))

        body = ttk.Frame(shell, style="PanelAlt.TFrame")
        body.grid(row=3, column=0, sticky="nsew", pady=(14, 0))
        body.columnconfigure(0, weight=7, uniform="body")
        body.columnconfigure(1, weight=3, uniform="body")
        body.rowconfigure(0, weight=1, minsize=340)

        history_card = ttk.Frame(body, padding=18, style="Panel.TFrame", width=720)
        history_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        history_card.columnconfigure(0, weight=1)
        history_card.rowconfigure(1, weight=1)
        history_card.grid_propagate(False)
        ttk.Label(history_card, text="Commit 记录", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(history_card, textvariable=self.branch_var, style="Muted.TLabel").grid(row=0, column=1, sticky="e")

        self.commit_canvas = tk.Canvas(history_card, bg=PANEL, highlightthickness=0, bd=0)
        self.commit_canvas.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(12, 0))
        history_scroll = ttk.Scrollbar(history_card, orient="vertical", command=self.commit_canvas.yview)
        history_scroll.grid(row=1, column=2, sticky="ns", pady=(12, 0))
        self.commit_canvas.configure(yscrollcommand=history_scroll.set)
        self.commit_list_frame = ttk.Frame(self.commit_canvas, style="Panel.TFrame")
        self.commit_list_frame.columnconfigure(0, weight=1)
        self.commit_canvas_window = self.commit_canvas.create_window((0, 0), window=self.commit_list_frame, anchor="nw")
        self.commit_list_frame.bind("<Configure>", lambda _e: self.commit_canvas.configure(scrollregion=self.commit_canvas.bbox("all")))
        self.commit_canvas.bind("<Configure>", self.on_commit_canvas_resize)

        side_card = ttk.Frame(body, padding=18, style="Panel.TFrame", width=320)
        side_card.grid(row=0, column=1, sticky="nsew")
        side_card.columnconfigure(0, weight=1)
        side_card.rowconfigure(4, weight=1)
        side_card.grid_propagate(False)
        ttk.Label(side_card, text="状态", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Separator(side_card, orient="horizontal", style="Card.TSeparator").grid(row=1, column=0, sticky="ew", pady=(12, 0))
        tk.Label(side_card, textvariable=self.worktree_var, bg=PANEL, fg=TEXT, anchor="w", font=("Segoe UI Semibold", 11), pady=10).grid(row=2, column=0, sticky="ew")
        tk.Label(side_card, textvariable=self.push_state_var, bg=PANEL_ALT, fg=TEXT, anchor="w", justify="left", wraplength=280, font=("Segoe UI", 10), padx=12, pady=10).grid(row=3, column=0, sticky="ew", pady=(8, 0))
        tk.Label(side_card, textvariable=self.tip_var, bg=PANEL, fg=TEXT_MUTED, anchor="nw", justify="left", wraplength=280, font=("Segoe UI", 9), pady=10).grid(row=4, column=0, sticky="new")
        ttk.Label(side_card, text="Push 记录", style="Muted.TLabel").grid(row=5, column=0, sticky="sw", pady=(12, 5))
        tk.Label(
            side_card,
            textvariable=self.push_history_var,
            bg=PANEL_ALT,
            fg=TEXT_MUTED,
            anchor="nw",
            justify="left",
            wraplength=280,
            font=("Consolas", 9),
            padx=12,
            pady=10,
        ).grid(row=6, column=0, sticky="sew")

    def create_pill(self, parent, variable: tk.StringVar, column: int):
        label = tk.Label(parent, textvariable=variable, bg=PANEL, fg=TEXT, font=("Segoe UI", 9), padx=14, pady=8, relief="flat")
        label.grid(row=0, column=column, sticky="ew", padx=(0, 10) if column < 2 else (0, 0))
        return label

    def draw_round_rect(self, canvas: tk.Canvas, x1, y1, x2, y2, radius, fill):
        points = [
            x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
            x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
            x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
        ]
        canvas.create_polygon(points, smooth=True, fill=fill, outline=fill)

    def render_switch(self):
        enabled = self.enabled_var.get()
        self.switch_canvas.delete("all")
        track = SUCCESS if enabled else SWITCH_OFF
        self.draw_round_rect(self.switch_canvas, 2, 2, 58, 30, 14, track)
        knob_x = 44 if enabled else 16
        self.switch_canvas.create_oval(knob_x - 12, 4, knob_x + 12, 28, fill=SWITCH_KNOB, outline=SWITCH_KNOB)
        self.switch_text_var.set("已开启" if enabled else "已关闭")

    def on_switch_click(self, _event=None):
        if self.busy:
            return
        self.enabled_var.set(not self.enabled_var.get())
        self.render_switch()
        self.on_toggle()

    def on_commit_canvas_resize(self, event):
        self.commit_canvas.itemconfigure(self.commit_canvas_window, width=event.width)

    def ensure_log_file(self):
        if not LOG_PATH.exists():
            LOG_PATH.write_text("", encoding="utf-8")

    def normalize_github_url(self, github_url: str) -> str:
        github_url = github_url.strip()
        if github_url and github_url.startswith("http") and not github_url.endswith(".git"):
            return github_url + ".git"
        return github_url

    def ensure_gitignore_exists(self, folder_path: Path):
        gitignore_path = folder_path / ".gitignore"
        if gitignore_path.exists():
            return
        gitignore_path.write_text("", encoding="utf-8")
        self.write_log(f"已新建 .gitignore：{gitignore_path}")

    def load_config(self):
        data = {}
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        self.folder_var.set(data.get("folder", ""))
        self.github_var.set(self.normalize_github_url(data.get("github_url", "")))
        self.username_var.set(data.get("username", ""))
        self.email_var.set(data.get("email", ""))
        self.interval_var.set(int(data.get("interval_seconds", 5)))
        self.prefix_var.set(data.get("prefix", "auto"))
        self.enabled_var.set(bool(data.get("auto_commit_enabled", False)))
        self.push_history = list(data.get("push_history", []))[-5:]
        self.refresh_push_history()

    def save_config(self):
        github_url = self.normalize_github_url(self.github_var.get())
        self.github_var.set(github_url)
        data = {
            "folder": self.folder_var.get().strip(),
            "github_url": github_url,
            "username": self.username_var.get().strip(),
            "email": self.email_var.get().strip(),
            "interval_seconds": int(self.interval_var.get()),
            "prefix": self.prefix_var.get().strip() or "auto",
            "auto_commit_enabled": bool(self.enabled_var.get()),
            "push_history": self.push_history[-5:],
        }
        CONFIG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def choose_folder(self):
        selected = filedialog.askdirectory(initialdir=self.folder_var.get() or str(APP_DIR))
        if not selected:
            return
        self.folder_var.set(selected)
        self.identity_inputs_dirty = False
        self.ensure_gitignore_exists(Path(selected))
        self.save_config()
        self.request_status_refresh()

    def on_identity_input_changed(self, _event=None):
        self.identity_inputs_dirty = True

    def refresh_push_history(self):
        if not self.push_history:
            self.push_history_var.set("暂无 push 记录")
            return
        self.push_history_var.set("\n".join(self.push_history[-5:]))

    def append_push_history(self, message: str):
        timestamp = datetime.now().strftime("%m-%d %H:%M:%S")
        self.push_history.append(f"{timestamp}  {message}")
        self.push_history = self.push_history[-5:]
        self.refresh_push_history()
        self.save_config()

    def open_gitignore_with(self):
        folder = self.folder_var.get().strip()
        if not folder:
            messagebox.showerror("缺少项目文件夹", "请先选择一个项目文件夹。")
            return
        folder_path = Path(folder)
        if not folder_path.exists():
            messagebox.showerror("文件夹不存在", f"这个文件夹不存在：\n{folder_path}")
            return
        self.ensure_gitignore_exists(folder_path)
        gitignore_path = folder_path / ".gitignore"
        try:
            subprocess.Popen(["rundll32.exe", "shell32.dll,OpenAs_RunDLL", str(gitignore_path)])
            self.write_log(f"已打开 .gitignore 的打开方式窗口：{gitignore_path}")
        except OSError as exc:
            messagebox.showerror("打开失败", str(exc))

    def git_init_repo(self):
        folder = self.folder_var.get().strip()
        if not folder:
            messagebox.showerror("缺少项目文件夹", "请先选择一个项目文件夹。")
            return
        folder_path = Path(folder)
        if not folder_path.exists():
            messagebox.showerror("文件夹不存在", f"这个文件夹不存在：\n{folder_path}")
            return
        if (folder_path / ".git").exists():
            messagebox.showinfo("已经初始化", "这个项目文件夹已经有 .git 了。")
            return

        def work():
            self.set_busy(True)
            try:
                with self.git_lock:
                    result = subprocess.run(["git", "init"], cwd=folder_path, capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
                self.ensure_gitignore_exists(folder_path)
                self.write_log((result.stdout or result.stderr or "").strip() or f"已执行 git init：{folder_path}")
                messagebox.showinfo("初始化完成", "已执行 git init，现在这个文件夹已经是 Git 仓库。")
                self.request_status_refresh()
            except subprocess.CalledProcessError as exc:
                output = (exc.stdout or exc.stderr or str(exc)).strip()
                self.write_log(f"git init 失败：{output}")
                messagebox.showerror("初始化失败", output)
            finally:
                self.set_busy(False)

        threading.Thread(target=work, daemon=True).start()

    def save_identity(self):
        repo_path = self.get_repo_path(show_errors=True)
        if not repo_path:
            return
        username = self.username_var.get().strip()
        email = self.email_var.get().strip()
        if not username or not email:
            messagebox.showerror("缺少身份信息", "请先填写 Git 用户名和邮箱。")
            return

        def work():
            self.set_busy(True)
            try:
                self.run_git(repo_path, "config", "user.name", username)
                self.run_git(repo_path, "config", "user.email", email)
                self.identity_inputs_dirty = False
                self.write_log(f"已设置 Git 身份：{username} <{email}>")
                self.save_config()
                messagebox.showinfo("保存完成", "Git 用户名和邮箱已经保存到当前仓库。")
                self.request_status_refresh()
            except subprocess.CalledProcessError as exc:
                output = (exc.stdout or exc.stderr or str(exc)).strip()
                self.write_log(f"保存身份失败：{output}")
                messagebox.showerror("保存失败", output)
            finally:
                self.set_busy(False)

        threading.Thread(target=work, daemon=True).start()

    def restore_auto_commit_state(self):
        self.render_switch()
        if self.enabled_var.get():
            self.start_auto_commit()
        else:
            self.stop_auto_commit(log_change=False, persist=False)

    def on_toggle(self):
        if self.enabled_var.get():
            self.start_auto_commit()
        else:
            self.stop_auto_commit(log_change=True, persist=False)
        self.save_config()

    def start_auto_commit(self):
        repo_path = self.get_repo_path(show_errors=True)
        if not repo_path:
            self.enabled_var.set(False)
            self.save_config()
            self.render_switch()
            return
        self.ensure_gitignore_exists(repo_path)
        if self.auto_worker and self.auto_worker.is_alive():
            return
        self.auto_worker = AutoCommitWorker(self, repo_path, self.interval_var.get(), self.prefix_var.get())
        self.auto_worker.start()
        self.mode_var.set("监控中")
        self.mode_badge.configure(bg=SUCCESS, fg="#08101F")
        self.tip_var.set("Auto Commit 正在运行。")
        self.write_log("Auto Commit 已开启。")
        self.request_status_refresh()

    def stop_auto_commit(self, log_change=True, persist=False):
        if self.auto_worker:
            self.auto_worker.stop()
            self.auto_worker = None
        self.mode_var.set("空闲")
        self.mode_badge.configure(bg=FIELD, fg=TEXT)
        self.tip_var.set("Auto Commit 已关闭。")
        if log_change:
            self.write_log("Auto Commit 已关闭。")
        if persist:
            self.save_config()
        self.request_status_refresh()

    def on_close(self):
        enabled = bool(self.enabled_var.get())
        if self.auto_worker:
            self.auto_worker.stop()
            self.auto_worker = None
        self.enabled_var.set(enabled)
        self.save_config()
        self.root.destroy()

    def get_repo_path(self, show_errors=False) -> Path | None:
        raw = self.folder_var.get().strip()
        if not raw:
            if show_errors:
                messagebox.showerror("缺少项目文件夹", "请先选择一个项目文件夹。")
            return None
        repo_path = Path(raw)
        if not repo_path.exists():
            if show_errors:
                messagebox.showerror("文件夹不存在", f"这个文件夹不存在：\n{repo_path}")
            return None
        if not (repo_path / ".git").exists():
            if show_errors:
                messagebox.showerror("不是 Git 仓库", f"这个目录里没有 .git 文件夹：\n{repo_path}")
            return None
        return repo_path

    def run_git(self, repo_path: Path, *args: str, check=True) -> subprocess.CompletedProcess:
        with self.git_lock:
            return subprocess.run(["git", *args], cwd=repo_path, capture_output=True, text=True, encoding="utf-8", errors="replace", check=check)

    def repo_has_blocking_git_marker(self, repo_path: Path) -> bool:
        git_dir = repo_path / ".git"
        return any((git_dir / name).exists() for name in ("MERGE_HEAD", "REBASE_HEAD", "CHERRY_PICK_HEAD", "BISECT_LOG"))

    def auto_commit_once(self, repo_path: Path, prefix: str) -> bool:
        with self.git_lock:
            subprocess.run(["git", "add", "-A"], cwd=repo_path, capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
            diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo_path, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
            if diff.returncode == 0:
                return False
            if diff.returncode != 1:
                raise RuntimeError(diff.stderr.strip() or "git diff --cached 执行失败")
            message = f"{prefix}: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            result = subprocess.run(["git", "commit", "-m", message], cwd=repo_path, capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
        self.write_log((result.stdout or result.stderr or "").strip() or f"已 commit：{message}")
        return True

    def commit_now(self):
        repo_path = self.get_repo_path(show_errors=True)
        if not repo_path or self.busy:
            return
        self.ensure_gitignore_exists(repo_path)

        def work():
            self.set_busy(True)
            try:
                committed = self.auto_commit_once(repo_path, self.prefix_var.get().strip() or "manual")
                if not committed:
                    self.write_log("没有新的改动需要 commit。")
                self.request_status_refresh()
            except Exception as exc:
                self.write_log(f"立即 commit 失败：{exc}")
                messagebox.showerror("Commit 失败", str(exc))
            finally:
                self.set_busy(False)

        threading.Thread(target=work, daemon=True).start()

    def push_to_github(self):
        repo_path = self.get_repo_path(show_errors=True)
        if not repo_path or self.busy:
            return
        self.ensure_gitignore_exists(repo_path)

        def work():
            self.set_busy(True)
            try:
                self.ensure_remote_url(repo_path)
                branch = self.run_git(repo_path, "branch", "--show-current").stdout.strip()
                if not branch:
                    raise RuntimeError("当前不在正常分支上，不能直接 push。请先切回一个分支。")
                upstream = self.run_git(repo_path, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}", check=False)
                if upstream.returncode != 0 or not upstream.stdout.strip():
                    result = self.run_git(repo_path, "push", "--set-upstream", "origin", branch)
                else:
                    result = self.run_git(repo_path, "push")
                self.write_log((result.stdout or result.stderr or "").strip() or "Push 已完成。")
                self.push_state_var.set(f"待 push：0 条 commit | 最近 push 成功：{datetime.now().strftime('%H:%M:%S')}")
                self.append_push_history("push 成功")
                self.request_status_refresh()
            except (subprocess.CalledProcessError, RuntimeError) as exc:
                output = (exc.stdout or exc.stderr or str(exc)).strip()
                self.write_log(f"push 失败：{output}")
                self.push_state_var.set(f"待 push：未知 | 最近 push 失败：{datetime.now().strftime('%H:%M:%S')}")
                self.append_push_history("push 失败")
                messagebox.showerror("Push 失败", output)
            finally:
                self.set_busy(False)

        self.save_config()
        threading.Thread(target=work, daemon=True).start()

    def ensure_remote_url(self, repo_path: Path):
        github_url = self.normalize_github_url(self.github_var.get())
        if not github_url:
            return
        self.github_var.set(github_url)
        current = self.run_git(repo_path, "remote", "get-url", "origin", check=False)
        current_url = current.stdout.strip()
        if current.returncode != 0 or not current_url:
            self.run_git(repo_path, "remote", "add", "origin", github_url)
            self.write_log(f"已新增 origin：{github_url}")
        elif current_url != github_url:
            self.run_git(repo_path, "remote", "set-url", "origin", github_url)
            self.write_log(f"已更新 origin：{github_url}")

    def request_status_refresh(self):
        if self.refresh_running:
            return
        repo_path = self.get_repo_path()
        if not repo_path:
            self.branch_var.set("branch -")
            self.worktree_var.set("工作区未连接")
            self.tip_var.set("请选择一个 Git 项目文件夹。")
            self.push_state_var.set("待 push：0 条 commit")
            self.render_commit_list([])
            return
        self.refresh_running = True

        def work():
            try:
                snapshot = self.collect_status(repo_path)
                self.root.after(0, lambda: self.apply_snapshot(snapshot))
            finally:
                self.refresh_running = False
                self.root.after(3000, self.request_status_refresh)

        threading.Thread(target=work, daemon=True).start()

    def collect_status(self, repo_path: Path) -> RepoSnapshot:
        branch = self.run_git(repo_path, "branch", "--show-current").stdout.strip()
        if branch:
            branch_state = "正常分支"
        else:
            head_sha = self.run_git(repo_path, "rev-parse", "--short", "HEAD").stdout.strip() or "-"
            branch = f"detached@{head_sha}"
            branch_state = "detached HEAD"

        status_lines = self.run_git(repo_path, "status", "--porcelain", "--branch").stdout.splitlines()
        changed_paths: list[Path] = []
        ahead = behind = 0
        dirty = False
        if status_lines:
            header = status_lines[0]
            if "ahead " in header:
                ahead = int(header.split("ahead ", 1)[1].split("]", 1)[0].split(",", 1)[0].strip())
            if "behind " in header:
                behind = int(header.split("behind ", 1)[1].split("]", 1)[0].split(",", 1)[0].strip())
            for line in status_lines[1:]:
                if not line:
                    continue
                dirty = True
                path_text = line[3:]
                if " -> " in path_text:
                    path_text = path_text.split(" -> ", 1)[1]
                changed_paths.append(repo_path / path_text)

        history_lines = self.run_git(repo_path, "log", "-12", "--date=format:%Y-%m-%d %H:%M:%S", "--pretty=%h|%ad|%s").stdout.splitlines()
        commits: list[CommitItem] = []
        for line in history_lines:
            parts = line.split("|", 2)
            if len(parts) == 3:
                commits.append(CommitItem(sha=parts[0], timestamp=parts[1], message=parts[2]))

        config_name = self.run_git(repo_path, "config", "--get", "user.name", check=False).stdout.strip()
        config_email = self.run_git(repo_path, "config", "--get", "user.email", check=False).stdout.strip()
        if config_name and not self.identity_inputs_dirty:
            self.root.after(0, lambda: self.username_var.set(config_name))
        if config_email and not self.identity_inputs_dirty:
            self.root.after(0, lambda: self.email_var.set(config_email))

        return RepoSnapshot(
            branch=branch,
            branch_state=branch_state,
            ahead=ahead,
            behind=behind,
            dirty=dirty,
            changed_count=len(changed_paths),
            commits=commits,
        )

    def apply_snapshot(self, snapshot: RepoSnapshot):
        self.branch_var.set(f"branch {snapshot.branch}")
        if snapshot.branch_state == "detached HEAD":
            self.worktree_var.set("当前不在正常分支上")
            self.tip_var.set("当前是 detached HEAD，适合查看历史版本，但不适合长期开发。")
        elif snapshot.dirty:
            self.worktree_var.set(f"工作区有改动 {snapshot.changed_count}")
            self.tip_var.set("当前有未提交改动。等待 Auto Commit 或手动 Commit。")
        else:
            self.worktree_var.set("工作区干净")
            self.tip_var.set("当前工作区比较干净。")

        self.push_state_var.set(f"待 push：{snapshot.ahead} 条 commit")
        self.render_commit_list(snapshot.commits)

    def render_commit_list(self, commits: list[CommitItem]):
        signature = [(item.sha, item.message, item.timestamp) for item in commits]
        if signature == self.last_commit_signature:
            return
        self.last_commit_signature = signature

        for row in self.commit_rows:
            row.destroy()
        self.commit_rows.clear()
        if not commits:
            empty = tk.Frame(self.commit_list_frame, bg=PANEL)
            empty.grid(row=0, column=0, sticky="ew")
            empty.columnconfigure(0, weight=1)
            tk.Label(
                empty,
                text="还没有可显示的 commit 记录",
                bg=PANEL,
                fg=TEXT_MUTED,
                anchor="center",
                font=("Segoe UI", 10),
                padx=6,
                pady=24,
            ).grid(row=0, column=0, sticky="ew")
            self.commit_rows.append(empty)
            return
        for idx, item in enumerate(commits):
            row = tk.Frame(self.commit_list_frame, bg=PANEL_ALT)
            row.grid(row=idx, column=0, sticky="ew", pady=(0, 10))
            row.columnconfigure(1, weight=1)
            row.columnconfigure(2, weight=0)

            strip = tk.Frame(row, bg=ACCENT_SOFT, width=3)
            strip.grid(row=0, column=0, sticky="ns")
            strip.grid_propagate(False)

            content = tk.Frame(row, bg=PANEL_ALT)
            content.grid(row=0, column=1, sticky="ew", padx=(14, 10), pady=12)
            content.columnconfigure(0, weight=1)
            tk.Label(
                content,
                text=item.sha,
                bg=PANEL_ALT,
                fg=ACCENT,
                anchor="w",
                justify="left",
                font=("Consolas", 10),
            ).grid(row=0, column=0, sticky="w")
            tk.Label(
                content,
                text=item.message,
                bg=PANEL_ALT,
                fg=TEXT,
                anchor="w",
                justify="left",
                wraplength=460,
                font=("Segoe UI", 10),
            ).grid(row=1, column=0, sticky="ew", pady=(4, 0))

            right = tk.Frame(row, bg=PANEL_ALT)
            right.grid(row=0, column=2, sticky="e", padx=(8, 14), pady=12)
            tk.Label(right, text=item.timestamp, bg=PANEL_ALT, fg=TEXT_MUTED, font=("Segoe UI", 9)).grid(row=0, column=0, padx=(0, 12))
            ttk.Button(right, text="切换到此版本", style="Small.TButton", command=lambda sha=item.sha: self.checkout_commit(sha)).grid(row=0, column=1)
            self.commit_rows.append(row)

    def checkout_commit(self, sha: str):
        repo_path = self.get_repo_path(show_errors=True)
        if not repo_path or self.busy:
            return
        if not messagebox.askyesno("切换版本", f"将切换到 commit {sha}。\n这会进入该版本状态，是否继续？"):
            return

        def work():
            self.set_busy(True)
            try:
                self.run_git(repo_path, "checkout", sha)
                self.write_log(f"已切换到 commit：{sha}")
                self.request_status_refresh()
            except subprocess.CalledProcessError as exc:
                output = (exc.stdout or exc.stderr or str(exc)).strip()
                self.write_log(f"切换失败：{output}")
                messagebox.showerror("切换失败", output)
            finally:
                self.set_busy(False)

        threading.Thread(target=work, daemon=True).start()

    def open_log_window(self):
        if self.log_window and self.log_window.winfo_exists():
            self.log_window.lift()
            self.refresh_log_window()
            return
        self.log_window = tk.Toplevel(self.root)
        self.log_window.title("运行日志")
        self.log_window.geometry("880x540")
        self.log_window.minsize(720, 400)
        self.log_window.configure(bg=BG)
        self.log_window.columnconfigure(0, weight=1)
        self.log_window.rowconfigure(1, weight=1)

        top = ttk.Frame(self.log_window, padding=18, style="PanelAlt.TFrame")
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(0, weight=1)
        ttk.Label(top, text="运行日志", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(top, text=f"日志文件：{LOG_PATH}", style="HeaderSub.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Button(top, text="刷新日志", style="Secondary.TButton", command=self.refresh_log_window).grid(row=0, column=1, rowspan=2, padx=(12, 0))

        body = ttk.Frame(self.log_window, padding=(18, 0, 18, 18), style="PanelAlt.TFrame")
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        self.log_text = tk.Text(body, wrap="word", state="disabled", bg=PANEL, fg=TEXT, insertbackground=TEXT, relief="flat", borderwidth=0, font=("Consolas", 10), padx=16, pady=16, highlightthickness=0)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.refresh_log_window()

    def refresh_log_window(self):
        if not self.log_window or not self.log_window.winfo_exists() or not self.log_text:
            return
        content = LOG_PATH.read_text(encoding="utf-8", errors="replace") if LOG_PATH.exists() else ""
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.insert("1.0", content)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def write_log(self, text: str):
        line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {text}"
        with self.log_lock:
            with LOG_PATH.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")

    def set_busy(self, is_busy: bool):
        self.busy = is_busy
        state = "disabled" if self.busy else "normal"
        for widget in (
            self.browse_button,
            self.refresh_button,
            self.commit_button,
            self.logs_button,
            self.gitignore_button,
            self.push_button,
            self.init_button,
            self.identity_button,
            self.interval_spin,
            self.prefix_entry,
            self.github_entry,
            self.username_entry,
            self.email_entry,
        ):
            widget.configure(state=state)
        self.switch_canvas.configure(cursor="arrow" if self.busy else "hand2")
        if self.busy:
            self.mode_var.set("处理中")
            self.mode_badge.configure(bg=WARN, fg="#1A1206")
        elif self.auto_worker and self.auto_worker.is_alive():
            self.mode_var.set("监控中")
            self.mode_badge.configure(bg=SUCCESS, fg="#08101F")
        else:
            self.mode_var.set("空闲")
            self.mode_badge.configure(bg=FIELD, fg=TEXT)
        self.render_switch()


def main():
    enable_high_dpi()
    root = tk.Tk()
    apply_dpi_scaling(root)
    AutoCommitApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
