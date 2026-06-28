import json
import queue
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
DEFAULT_REPO = APP_DIR / "GlobalPEQ"

BG = "#101217"
CARD = "#171A21"
CARD_2 = "#1D212B"
TEXT = "#F3F5F7"
TEXT_MUTED = "#9CA3AF"
ACCENT = "#4F8CFF"
ACCENT_HOVER = "#6A9CFF"
SUCCESS = "#1FA971"
WARN = "#F4A23A"
DANGER = "#E45D5D"
BORDER = "#2A3040"
FIELD = "#11151D"
SWITCH_OFF = "#343B4B"
SWITCH_KNOB = "#F8FAFC"


@dataclass
class RepoSnapshot:
    branch: str = "-"
    ahead: int = 0
    behind: int = 0
    dirty: bool = False
    changed_count: int = 0
    last_commit: str = "-"
    modified_display: str = "修改时间：-"
    summary: str = "未就绪"


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
        self.root.geometry("920x520")
        self.root.minsize(860, 480)
        self.root.configure(bg=BG)

        self.event_queue: queue.Queue = queue.Queue()
        self.log_lock = threading.Lock()
        self.git_lock = threading.Lock()
        self.auto_worker: AutoCommitWorker | None = None
        self.refresh_running = False
        self.busy = False
        self.log_window: tk.Toplevel | None = None
        self.log_text: tk.Text | None = None

        self.enabled_var = tk.BooleanVar(value=False)
        self.folder_var = tk.StringVar()
        self.github_var = tk.StringVar()
        self.interval_var = tk.IntVar(value=5)
        self.prefix_var = tk.StringVar(value="auto")

        self.summary_var = tk.StringVar(value="等待选择项目文件夹")
        self.commit_var = tk.StringVar(value="最近一次 commit：-")
        self.modified_var = tk.StringVar(value="修改时间：-")
        self.branch_var = tk.StringVar(value="branch -")
        self.sync_var = tk.StringVar(value="ahead 0")
        self.worktree_var = tk.StringVar(value="工作区未连接")
        self.tip_var = tk.StringVar(value="开启 Auto Commit 后会自动 add + commit，push 仍需手动执行。")
        self.mode_var = tk.StringVar(value="空闲")
        self.switch_text_var = tk.StringVar(value="已关闭")

        self.configure_style()
        self.build_ui()
        self.load_config()
        self.ensure_log_file()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(180, self.process_events)
        self.request_status_refresh()

    def configure_style(self):
        style = ttk.Style()
        style.theme_use("clam")

        style.configure(".", background=BG, foreground=TEXT, fieldbackground=FIELD)
        style.configure("Card.TFrame", background=CARD, relief="flat")
        style.configure("CardAlt.TFrame", background=CARD_2, relief="flat")
        style.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=CARD, foreground=TEXT_MUTED, font=("Segoe UI", 9))
        style.configure("TinyMuted.TLabel", background=CARD, foreground=TEXT_MUTED, font=("Segoe UI", 8))
        style.configure("Title.TLabel", background=BG, foreground=TEXT, font=("Segoe UI Semibold", 21))
        style.configure("SubTitle.TLabel", background=BG, foreground=TEXT_MUTED, font=("Segoe UI", 10))
        style.configure("CardTitle.TLabel", background=CARD, foreground=TEXT, font=("Segoe UI Semibold", 10))
        style.configure("Value.TLabel", background=CARD, foreground=TEXT, font=("Segoe UI Semibold", 11))
        style.configure("StatusHero.TLabel", background=CARD_2, foreground=TEXT, font=("Segoe UI Semibold", 16))
        style.configure(
            "TEntry",
            foreground=TEXT,
            fieldbackground=FIELD,
            bordercolor=BORDER,
            insertcolor=TEXT,
            padding=8,
        )
        style.configure(
            "TSpinbox",
            foreground=TEXT,
            fieldbackground=FIELD,
            bordercolor=BORDER,
            arrowsize=12,
            padding=6,
        )
        style.configure(
            "Accent.TButton",
            background=ACCENT,
            foreground=TEXT,
            bordercolor=ACCENT,
            focusthickness=0,
            padding=(14, 9),
            font=("Segoe UI Semibold", 10),
        )
        style.map("Accent.TButton", background=[("active", ACCENT_HOVER), ("disabled", "#31405C")])
        style.configure(
            "Secondary.TButton",
            background=CARD_2,
            foreground=TEXT,
            bordercolor=BORDER,
            focusthickness=0,
            padding=(12, 9),
            font=("Segoe UI", 10),
        )
        style.map("Secondary.TButton", background=[("active", "#242A36"), ("disabled", "#1A1D25")])

    def build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        shell = ttk.Frame(self.root, padding=18, style="CardAlt.TFrame")
        shell.grid(row=0, column=0, sticky="nsew", padx=18, pady=18)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(3, weight=1)

        header = ttk.Frame(shell, style="CardAlt.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Git 自动提交工具", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="更轻、更紧凑的本地 auto commit / 手动 push 工作台",
            style="SubTitle.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        grid = ttk.Frame(shell, style="CardAlt.TFrame")
        grid.grid(row=1, column=0, sticky="nsew", pady=(16, 0))
        grid.columnconfigure(0, weight=3)
        grid.columnconfigure(1, weight=2)
        grid.rowconfigure(1, weight=1)

        repo_card = ttk.Frame(grid, padding=16, style="Card.TFrame")
        repo_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=(0, 10))
        repo_card.columnconfigure(1, weight=1)
        ttk.Label(repo_card, text="仓库设置", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(repo_card, text="连接本地项目与 GitHub 远端", style="TinyMuted.TLabel").grid(
            row=0, column=3, sticky="e"
        )

        ttk.Label(repo_card, text="项目文件夹", style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(14, 6))
        self.folder_entry = ttk.Entry(repo_card, textvariable=self.folder_var)
        self.folder_entry.grid(row=2, column=0, columnspan=3, sticky="ew")
        self.browse_button = ttk.Button(repo_card, text="选择", style="Secondary.TButton", command=self.choose_folder)
        self.browse_button.grid(row=2, column=3, padx=(10, 0))

        ttk.Label(repo_card, text="GitHub 链接", style="Muted.TLabel").grid(row=3, column=0, sticky="w", pady=(14, 6))
        self.github_entry = ttk.Entry(repo_card, textvariable=self.github_var)
        self.github_entry.grid(row=4, column=0, columnspan=4, sticky="ew")

        control_card = ttk.Frame(grid, padding=16, style="Card.TFrame")
        control_card.grid(row=0, column=1, sticky="nsew", pady=(0, 10))
        control_card.columnconfigure(1, weight=1)
        ttk.Label(control_card, text="控制", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(control_card, text="总开关", style="TinyMuted.TLabel").grid(row=0, column=1, sticky="e")

        switch_row = ttk.Frame(control_card, style="Card.TFrame")
        switch_row.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(14, 10))
        switch_row.columnconfigure(1, weight=1)

        ttk.Label(switch_row, text="Auto Commit", style="Value.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(switch_row, textvariable=self.switch_text_var, style="Muted.TLabel").grid(row=0, column=1, sticky="e", padx=(0, 10))
        self.switch_canvas = tk.Canvas(
            switch_row,
            width=54,
            height=30,
            bg=CARD,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.switch_canvas.grid(row=0, column=2, sticky="e")
        self.switch_canvas.bind("<Button-1>", self.on_switch_click)
        self.render_switch()

        self.mode_badge = tk.Label(
            control_card,
            textvariable=self.mode_var,
            bg=FIELD,
            fg=TEXT,
            font=("Segoe UI Semibold", 9),
            padx=10,
            pady=5,
        )
        self.mode_badge.grid(row=2, column=1, sticky="e", pady=(0, 10))

        ttk.Label(control_card, text="间隔", style="Muted.TLabel").grid(row=3, column=0, sticky="w", pady=(4, 6))
        interval_row = ttk.Frame(control_card, style="Card.TFrame")
        interval_row.grid(row=4, column=0, sticky="w")
        self.interval_spin = ttk.Spinbox(interval_row, from_=2, to=3600, width=6, textvariable=self.interval_var)
        self.interval_spin.grid(row=0, column=0, sticky="w")
        ttk.Label(interval_row, text="秒", style="Muted.TLabel").grid(row=0, column=1, padx=(8, 0))

        ttk.Label(control_card, text="Commit 前缀", style="Muted.TLabel").grid(row=3, column=1, sticky="w", pady=(4, 6))
        self.prefix_entry = ttk.Entry(control_card, textvariable=self.prefix_var, width=14)
        self.prefix_entry.grid(row=4, column=1, sticky="ew")

        action_card = ttk.Frame(grid, padding=16, style="Card.TFrame")
        action_card.grid(row=1, column=0, columnspan=2, sticky="nsew")
        action_card.columnconfigure(0, weight=1)
        action_card.columnconfigure(1, weight=1)
        action_card.columnconfigure(2, weight=1)
        action_card.columnconfigure(3, weight=1)

        self.refresh_button = ttk.Button(action_card, text="刷新状态", style="Secondary.TButton", command=self.request_status_refresh)
        self.refresh_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.commit_button = ttk.Button(action_card, text="立即 Commit", style="Secondary.TButton", command=self.commit_now)
        self.commit_button.grid(row=0, column=1, sticky="ew", padx=8)
        self.logs_button = ttk.Button(action_card, text="查看日志", style="Secondary.TButton", command=self.open_log_window)
        self.logs_button.grid(row=0, column=2, sticky="ew", padx=8)
        self.push_button = ttk.Button(action_card, text="Push 到 GitHub", style="Accent.TButton", command=self.push_to_github)
        self.push_button.grid(row=0, column=3, sticky="ew", padx=(8, 0))
        ttk.Label(
            action_card,
            text="日志已独立到单独窗口，主界面只保留核心控制。",
            style="TinyMuted.TLabel",
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(10, 0))

        status_card = ttk.Frame(shell, padding=18, style="CardAlt.TFrame")
        status_card.grid(row=2, column=0, sticky="nsew", pady=(14, 0))
        status_card.columnconfigure(0, weight=1)
        status_card.columnconfigure(1, weight=0)

        ttk.Label(status_card, text="状态", style="SubTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(status_card, textvariable=self.modified_var, style="SubTitle.TLabel").grid(row=0, column=1, sticky="e")
        ttk.Label(status_card, textvariable=self.summary_var, style="StatusHero.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", pady=(10, 2))
        ttk.Label(status_card, textvariable=self.commit_var, style="SubTitle.TLabel").grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 14))

        metrics = ttk.Frame(status_card, style="CardAlt.TFrame")
        metrics.grid(row=3, column=0, columnspan=2, sticky="ew")
        metrics.columnconfigure(0, weight=1)
        metrics.columnconfigure(1, weight=1)
        metrics.columnconfigure(2, weight=1)

        self.branch_pill = self.create_pill(metrics, self.branch_var, 0)
        self.sync_pill = self.create_pill(metrics, self.sync_var, 1)
        self.worktree_pill = self.create_pill(metrics, self.worktree_var, 2)

        footer = ttk.Frame(shell, style="CardAlt.TFrame")
        footer.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.tip_var, style="SubTitle.TLabel").grid(row=0, column=0, sticky="w")

    def create_pill(self, parent, variable: tk.StringVar, column: int):
        label = tk.Label(
            parent,
            textvariable=variable,
            bg=CARD,
            fg=TEXT,
            font=("Segoe UI", 9),
            padx=14,
            pady=8,
            relief="flat",
        )
        padx = (0, 10) if column < 2 else (0, 0)
        label.grid(row=0, column=column, sticky="ew", padx=padx)
        return label

    def draw_round_rect(self, canvas: tk.Canvas, x1, y1, x2, y2, radius, fill, outline=None):
        points = [
            x1 + radius, y1,
            x2 - radius, y1,
            x2, y1,
            x2, y1 + radius,
            x2, y2 - radius,
            x2, y2,
            x2 - radius, y2,
            x1 + radius, y2,
            x1, y2,
            x1, y2 - radius,
            x1, y1 + radius,
            x1, y1,
        ]
        return canvas.create_polygon(points, smooth=True, fill=fill, outline=outline or fill)

    def render_switch(self):
        if not hasattr(self, "switch_canvas"):
            return
        enabled = self.enabled_var.get()
        bg_color = SUCCESS if enabled else SWITCH_OFF
        knob_x = 39 if enabled else 15
        self.switch_canvas.delete("all")
        self.draw_round_rect(self.switch_canvas, 2, 2, 52, 28, 14, bg_color)
        self.switch_canvas.create_oval(knob_x - 11, 4, knob_x + 11, 26, fill=SWITCH_KNOB, outline=SWITCH_KNOB)
        self.switch_text_var.set("已开启" if enabled else "已关闭")

    def on_switch_click(self, _event=None):
        if self.busy:
            return
        self.enabled_var.set(not self.enabled_var.get())
        self.render_switch()
        self.on_toggle()

    def ensure_log_file(self):
        if not LOG_PATH.exists():
            LOG_PATH.write_text("", encoding="utf-8")

    def load_config(self):
        data = {}
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        self.folder_var.set(data.get("folder", str(DEFAULT_REPO) if DEFAULT_REPO.exists() else ""))
        self.github_var.set(data.get("github_url", ""))
        self.interval_var.set(int(data.get("interval_seconds", 5)))
        self.prefix_var.set(data.get("prefix", "auto"))

    def save_config(self):
        data = {
            "folder": self.folder_var.get().strip(),
            "github_url": self.github_var.get().strip(),
            "interval_seconds": int(self.interval_var.get()),
            "prefix": self.prefix_var.get().strip() or "auto",
        }
        CONFIG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def choose_folder(self):
        selected = filedialog.askdirectory(initialdir=self.folder_var.get() or str(APP_DIR))
        if not selected:
            return
        self.folder_var.set(selected)
        self.save_config()
        self.request_status_refresh()

    def on_toggle(self):
        if self.enabled_var.get():
            self.start_auto_commit()
        else:
            self.stop_auto_commit()
        self.save_config()

    def start_auto_commit(self):
        repo_path = self.get_repo_path(show_errors=True)
        if not repo_path:
            self.enabled_var.set(False)
            self.render_switch()
            return
        if self.auto_worker and self.auto_worker.is_alive():
            return
        self.auto_worker = AutoCommitWorker(self, repo_path, self.interval_var.get(), self.prefix_var.get())
        self.auto_worker.start()
        self.mode_var.set("监控中")
        self.mode_badge.configure(bg=SUCCESS)
        self.tip_var.set("Auto Commit 正在运行。新的改动会按设定间隔自动 commit。")
        self.write_log("Auto Commit 已开启。")
        self.request_status_refresh()

    def stop_auto_commit(self):
        if self.auto_worker:
            self.auto_worker.stop()
            self.auto_worker = None
        self.mode_var.set("空闲")
        self.mode_badge.configure(bg=FIELD)
        self.tip_var.set("Auto Commit 已关闭。现在仍可手动 Commit 或 Push。")
        self.write_log("Auto Commit 已关闭。")
        self.request_status_refresh()

    def on_close(self):
        self.stop_auto_commit()
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
            return subprocess.run(
                ["git", *args],
                cwd=repo_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=check,
            )

    def repo_has_blocking_git_marker(self, repo_path: Path) -> bool:
        git_dir = repo_path / ".git"
        return any((git_dir / name).exists() for name in ("MERGE_HEAD", "REBASE_HEAD", "CHERRY_PICK_HEAD", "BISECT_LOG"))

    def auto_commit_once(self, repo_path: Path, prefix: str) -> bool:
        with self.git_lock:
            subprocess.run(
                ["git", "add", "-A"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
            )
            diff = subprocess.run(
                ["git", "diff", "--cached", "--quiet"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if diff.returncode == 0:
                return False
            if diff.returncode != 1:
                raise RuntimeError(diff.stderr.strip() or "git diff --cached 执行失败")
            message = f"{prefix}: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            result = subprocess.run(
                ["git", "commit", "-m", message],
                cwd=repo_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
            )
        output = (result.stdout or result.stderr or "").strip()
        self.write_log(output or f"已 commit：{message}")
        return True

    def commit_now(self):
        repo_path = self.get_repo_path(show_errors=True)
        if not repo_path or self.busy:
            return

        def work():
            self.event_queue.put(("busy", True))
            try:
                committed = self.auto_commit_once(repo_path, self.prefix_var.get().strip() or "manual")
                if not committed:
                    self.write_log("没有新的改动需要 commit。")
                self.event_queue.put(("snapshot_request", None))
            except Exception as exc:
                self.write_log(f"立即 commit 失败：{exc}")
                self.event_queue.put(("message", ("Commit 失败", str(exc), True)))
            finally:
                self.event_queue.put(("busy", False))

        threading.Thread(target=work, daemon=True).start()

    def push_to_github(self):
        repo_path = self.get_repo_path(show_errors=True)
        if not repo_path or self.busy:
            return

        def work():
            self.event_queue.put(("busy", True))
            try:
                self.ensure_remote_url(repo_path)
                result = self.run_git(repo_path, "push")
                output = (result.stdout or result.stderr or "").strip()
                self.write_log(output or "Push 已完成。")
                self.event_queue.put(("message", ("Push 完成", "改动已经 push 到 GitHub。", False)))
                self.event_queue.put(("snapshot_request", None))
            except subprocess.CalledProcessError as exc:
                output = (exc.stdout or exc.stderr or str(exc)).strip()
                self.write_log(f"push 失败：{output}")
                self.event_queue.put(("message", ("Push 失败", output, True)))
            finally:
                self.event_queue.put(("busy", False))

        self.save_config()
        threading.Thread(target=work, daemon=True).start()

    def ensure_remote_url(self, repo_path: Path):
        github_url = self.github_var.get().strip()
        if not github_url:
            return
        with self.git_lock:
            current = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
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
            self.summary_var.set("请先连接一个 Git 项目")
            self.commit_var.set("最近一次 commit：-")
            self.modified_var.set("修改时间：-")
            self.branch_var.set("branch -")
            self.sync_var.set("ahead 0")
            self.worktree_var.set("未连接")
            self.tip_var.set("选择一个带 .git 的项目文件夹，然后再开启 Auto Commit。")
            return

        self.refresh_running = True

        def work():
            try:
                snapshot = self.collect_status(repo_path)
                self.event_queue.put(("snapshot", snapshot))
            except Exception as exc:
                self.event_queue.put(("refresh_error", str(exc)))
            finally:
                self.event_queue.put(("refresh_done", None))

        threading.Thread(target=work, daemon=True).start()

    def collect_status(self, repo_path: Path) -> RepoSnapshot:
        branch = self.run_git(repo_path, "branch", "--show-current").stdout.strip() or "detached"
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

        log_output = self.run_git(repo_path, "log", "-1", "--date=format:%Y-%m-%d %H:%M:%S", "--pretty=%ad|%h %s").stdout.strip()
        if log_output:
            last_commit_time, last_commit = log_output.split("|", 1)
        else:
            last_commit_time, last_commit = "-", "-"

        modified_display = self.build_modified_display(changed_paths, last_commit_time)
        if dirty:
            summary = f"检测到 {len(changed_paths)} 项改动"
        elif ahead:
            summary = f"有 {ahead} 个本地 commit 等待 push"
        else:
            summary = "状态稳定，正在等待新的改动"

        return RepoSnapshot(
            branch=branch,
            ahead=ahead,
            behind=behind,
            dirty=dirty,
            changed_count=len(changed_paths),
            last_commit=last_commit,
            modified_display=modified_display,
            summary=summary,
        )

    def build_modified_display(self, changed_paths: list[Path], fallback_time: str) -> str:
        latest = 0.0
        for path in changed_paths:
            try:
                latest = max(latest, path.stat().st_mtime)
            except OSError:
                continue
        if latest > 0:
            return "修改时间：" + datetime.fromtimestamp(latest).strftime("%Y-%m-%d %H:%M:%S")
        if fallback_time and fallback_time != "-":
            return "修改时间：" + fallback_time
        return "修改时间：-"

    def apply_snapshot(self, snapshot: RepoSnapshot):
        self.summary_var.set(snapshot.summary)
        self.commit_var.set(f"最近一次 commit：{snapshot.last_commit}")
        self.modified_var.set(snapshot.modified_display)
        self.branch_var.set(f"branch {snapshot.branch}")

        sync_chunks = []
        if snapshot.ahead:
            sync_chunks.append(f"ahead {snapshot.ahead}")
        if snapshot.behind:
            sync_chunks.append(f"behind {snapshot.behind}")
        if not sync_chunks:
            sync_chunks.append("ahead 0")
        self.sync_var.set(" | ".join(sync_chunks))

        if snapshot.dirty:
            self.worktree_var.set(f"工作区有改动 {snapshot.changed_count}")
            self.worktree_pill.configure(bg=WARN, fg="#111111")
            self.tip_var.set("当前有未提交改动。等待 Auto Commit 自动处理，或点击“立即 Commit”。")
        else:
            self.worktree_var.set("工作区干净")
            self.worktree_pill.configure(bg=SUCCESS, fg=TEXT)
            if snapshot.ahead:
                self.tip_var.set("当前已有本地 commit 尚未 push，准备好后点击“Push 到 GitHub”。")
            else:
                self.tip_var.set("当前工作区比较干净，工具只会在检测到新改动时再 commit。")

        self.branch_pill.configure(bg=CARD, fg=TEXT)
        self.sync_pill.configure(bg=CARD, fg=TEXT)
        if snapshot.ahead:
            self.sync_pill.configure(bg=ACCENT, fg=TEXT)

    def open_log_window(self):
        if self.log_window and self.log_window.winfo_exists():
            self.log_window.lift()
            self.refresh_log_window()
            return

        self.log_window = tk.Toplevel(self.root)
        self.log_window.title("运行日志")
        self.log_window.geometry("840x520")
        self.log_window.minsize(680, 360)
        self.log_window.configure(bg=BG)
        self.log_window.columnconfigure(0, weight=1)
        self.log_window.rowconfigure(1, weight=1)

        top = ttk.Frame(self.log_window, padding=14, style="CardAlt.TFrame")
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(0, weight=1)
        ttk.Label(top, text="运行日志", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(top, text=f"日志文件：{LOG_PATH}", style="SubTitle.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Button(top, text="刷新日志", style="Secondary.TButton", command=self.refresh_log_window).grid(row=0, column=1, rowspan=2, padx=(14, 0))

        body = ttk.Frame(self.log_window, padding=(14, 0, 14, 14), style="CardAlt.TFrame")
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        self.log_text = tk.Text(
            body,
            wrap="word",
            state="disabled",
            bg=CARD,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            borderwidth=0,
            font=("Consolas", 10),
            padx=14,
            pady=14,
        )
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
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {text}".strip()
        with self.log_lock:
            with LOG_PATH.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        self.event_queue.put(("log_written", line))

    def process_events(self):
        while True:
            try:
                kind, payload = self.event_queue.get_nowait()
            except queue.Empty:
                break

            if kind == "snapshot":
                self.apply_snapshot(payload)
            elif kind == "refresh_error":
                self.summary_var.set(f"状态读取失败：{payload}")
                self.tip_var.set("请检查项目目录和 Git 是否可用。")
                self.write_log(f"状态刷新失败：{payload}")
            elif kind == "refresh_done":
                self.refresh_running = False
                self.root.after(3000, self.request_status_refresh)
            elif kind == "busy":
                self.busy = payload
                self.apply_busy_state()
            elif kind == "message":
                title, text, is_error = payload
                if is_error:
                    messagebox.showerror(title, text)
                else:
                    messagebox.showinfo(title, text)
            elif kind == "log_written":
                self.refresh_log_window()
            elif kind == "snapshot_request":
                self.request_status_refresh()

        self.root.after(180, self.process_events)

    def apply_busy_state(self):
        state = "disabled" if self.busy else "normal"
        for widget in (
            self.browse_button,
            self.refresh_button,
            self.commit_button,
            self.logs_button,
            self.push_button,
            self.interval_spin,
            self.prefix_entry,
            self.github_entry,
        ):
            widget.configure(state=state)
        self.switch_canvas.configure(cursor="arrow" if self.busy else "hand2")
        if self.busy:
            self.mode_var.set("处理中")
            self.mode_badge.configure(bg=WARN, fg="#111111")
            self.tip_var.set("正在执行 Git 操作，请稍等。")
        elif self.auto_worker and self.auto_worker.is_alive():
            self.mode_var.set("监控中")
            self.mode_badge.configure(bg=SUCCESS, fg=TEXT)
        else:
            self.mode_var.set("空闲")
            self.mode_badge.configure(bg=FIELD, fg=TEXT)
        self.render_switch()


def main():
    root = tk.Tk()
    AutoCommitApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
