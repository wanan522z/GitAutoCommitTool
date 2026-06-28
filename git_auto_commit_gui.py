import ctypes
import ctypes.wintypes
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
CONFIG_FILENAME = "git_auto_commit_gui_config.json"
LOG_FILENAME = "git_auto_commit_gui.log"
APP_STORAGE_DIRNAME = "GitAutoCommitTool"

# --- 鐧借壊鐜颁唬涓婚閰嶈壊 ---
WINDOW = "#E9EEF6"        # 绐楀彛搴曡壊锛堜細琚涓洪€忔槑鑹诧紝闇插嚭浜氬厠鍔涙ā绯婏級
CARD_BG = "#FFFFFF"
CARD_BORDER = "#E6E9F0"
ROW_BG = "#F4F6FB"
ROW_HOVER = "#EDF1F8"
INPUT_BG = "#FFFFFF"
INPUT_BORDER = "#E1E5EE"
TEXT = "#1E2630"
TEXT_MUTED = "#6B7689"
TEXT_FAINT = "#A8B0C0"
ACCENT = "#4C7DFF"
ACCENT_HOVER = "#3A66E8"
ACCENT_SOFT = "#EAF1FF"
SUCCESS = "#1FA971"
SUCCESS_SOFT = "#E6F7F0"
WARN = "#D9922A"
WARN_SOFT = "#FBF1E0"
DANGER = "#E05D5D"
SWITCH_OFF = "#D3D9E4"
SWITCH_KNOB = "#FFFFFF"

# --- 瀛椾綋瀛楀彿甯搁噺锛堢櫧鑹茬幇浠ｄ富棰橈紝鍋忓ぇ浠ラ€傞厤楂?DPI锛?---
F_TITLE = ("Segoe UI Semibold", 16)
F_CARD_TITLE = ("Segoe UI Semibold", 14)
F_LABEL = ("Segoe UI", 11)
F_MUTED = ("Segoe UI", 10)
F_BUTTON = ("Segoe UI Semibold", 11)
F_BUTTON_SM = ("Segoe UI", 10)
F_BODY = ("Segoe UI", 11)
F_MONO = ("Consolas", 11)
F_MONO_SM = ("Consolas", 10)


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


def configure_tk_runtime():
    candidates: list[tuple[Path, Path]] = []
    if getattr(sys, "frozen", False):
        base_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
        candidates.append((base_dir / "_tcl_data", base_dir / "_tk_data"))
        candidates.append((base_dir / "tcl" / "tcl8.6", base_dir / "tcl" / "tk8.6"))
    else:
        base_prefix = Path(sys.base_prefix)
        candidates.append((base_prefix / "tcl" / "_tcl_data", base_prefix / "tcl" / "_tk_data"))
        candidates.append((base_prefix / "tcl" / "tcl8.6", base_prefix / "tcl" / "tk8.6"))
        candidates.append((APP_DIR / "_tcl_data", APP_DIR / "_tk_data"))
        candidates.append((APP_DIR / "tcl" / "tcl8.6", APP_DIR / "tcl" / "tk8.6"))

    for tcl_dir, tk_dir in candidates:
        if tcl_dir.exists() and tk_dir.exists():
            os.environ["TCL_LIBRARY"] = str(tcl_dir)
            os.environ["TK_LIBRARY"] = str(tk_dir)
            return


def reset_external_dll_search_path():
    if os.name != "nt":
        return
    try:
        ctypes.windll.kernel32.SetDllDirectoryW(None)
    except Exception:
        pass


def _root_hwnd(win):
    try:
        parent = ctypes.windll.user32.GetParent(win.winfo_id())
        return parent or win.winfo_id()
    except Exception:
        return win.winfo_id()


def apply_acrylic(win, gradient=0xCCFFFFFF):
    """Apply a Windows 10/11 acrylic effect when supported."""
    try:

        class AccentPolicy(ctypes.Structure):
            _fields_ = [
                ("AccentState", ctypes.c_int),
                ("AccentFlags", ctypes.c_int),
                ("GradientColor", ctypes.c_uint),
                ("AnimationId", ctypes.c_int),
            ]

        class WCA(ctypes.Structure):
            _fields_ = [
                ("Attribute", ctypes.c_int),
                ("Data", ctypes.POINTER(AccentPolicy)),
                ("SizeOfData", ctypes.c_int),
            ]

        accent = AccentPolicy()
        accent.AccentState = 4  # ACCENT_ENABLE_ACRYLICBLURBEHIND
        accent.GradientColor = gradient
        data = WCA()
        data.Attribute = 19  # WCA_ACCENT_POLICY
        data.Data = ctypes.pointer(accent)
        data.SizeOfData = ctypes.sizeof(accent)
        ok = ctypes.windll.user32.SetWindowCompositionAttribute(
            ctypes.wintypes.HWND(_root_hwnd(win)), ctypes.byref(data)
        )
        return bool(ok)
    except Exception:
        return False


def style_transparent(win):
    """Make the window background transparent so the acrylic effect can show through."""
    try:
        win.configure(bg=WINDOW)
        win.wm_attributes("-transparentcolor", WINDOW)
    except Exception:
        pass


# ---------- 閫氱敤鍦嗚鎺т欢 ----------

def ensure_appwindow(win):
    try:
        hwnd = ctypes.wintypes.HWND(_root_hwnd(win))
        get_window_long_ptr = getattr(ctypes.windll.user32, "GetWindowLongPtrW", None)
        set_window_long_ptr = getattr(ctypes.windll.user32, "SetWindowLongPtrW", None)
        if not get_window_long_ptr or not set_window_long_ptr:
            return
        GWL_EXSTYLE = -20
        WS_EX_APPWINDOW = 0x00040000
        WS_EX_TOOLWINDOW = 0x00000080
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_NOZORDER = 0x0004
        SWP_FRAMECHANGED = 0x0020
        ex_style = get_window_long_ptr(hwnd, GWL_EXSTYLE)
        ex_style = (ex_style | WS_EX_APPWINDOW) & ~WS_EX_TOOLWINDOW
        set_window_long_ptr(hwnd, GWL_EXSTYLE, ex_style)
        ctypes.windll.user32.SetWindowPos(
            hwnd,
            0,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED,
        )
    except Exception:
        pass


def _round_polygon(canvas, x1, y1, x2, y2, r, **kw):
    pts = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(pts, smooth=True, **kw)


class RoundedCard(tk.Frame):
    """Rounded white card drawn with a canvas-backed background."""

    def __init__(self, parent, radius=16, fill=CARD_BG, outline=CARD_BORDER,
                 outline_width=1, bg=WINDOW, padding=18, **kw):
        super().__init__(parent, bg=bg, **kw)
        self._r = radius
        self._fill = fill
        self._outline = outline
        self._ow = outline_width
        self._pad = padding
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.canvas.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.inner = tk.Frame(self, bg=fill)
        self.inner.grid(row=0, column=0, sticky="nsew", padx=padding, pady=padding)
        self.inner.columnconfigure(0, weight=1)
        self.bind("<Configure>", self._redraw)
        self.bind("<Map>", lambda _e: self._redraw())
        self.after(60, self._redraw)

    def _redraw(self, _=None):
        self.canvas.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 4 or h < 4:
            self.after(30, self._redraw)
            return
        _round_polygon(
            self.canvas, self._ow, self._ow, w - self._ow - 1, h - self._ow - 1, self._r,
            fill=self._fill, outline=self._outline, width=self._ow,
        )


def _lerp_color(c1, c2, t):
    """Linearly interpolate between two #RRGGBB colors with t in [0, 1]."""
    if not c1 or not c2 or not c1.startswith("#") or not c2.startswith("#"):
        return c1 or c2
    r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
    r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)
    return f"#{r:02X}{g:02X}{b:02X}"



class ModernButton(tk.Canvas):
    """Draw a vertical gradient with optional rounded clipping."""

    _VARIANTS = {
        "primary": dict(bg="#E8EEFF", fg=ACCENT, hover="#DDE7FF", press="#D3DEFF", border="#DCE5FF"),
        "secondary": dict(bg="#F1F4F9", fg=TEXT, hover="#E7ECF4", press="#DDE4EF", border="#E6EBF3"),
        "ghost": dict(bg="#F6F8FC", fg=TEXT_MUTED, hover="#EDF2F8", press="#E4EAF3", border="#ECF0F6"),
        "warning": dict(bg="#FFF1F0", fg=DANGER, hover="#FFE5E2", press="#FFD7D2", border="#FFE5E2"),
        "danger_outline": dict(bg="#FFFFFF", fg=DANGER, hover="#FFF4F3", press="#FFE7E4", border="#F2B8B2"),
        "titlebar": dict(bg=WINDOW, fg="#5E6778", hover="#EEF2F8", press="#E3E9F3", border=WINDOW),
        "titlebar_close": dict(bg=WINDOW, fg="#5E6778", hover="#E05D5D", press="#CC4D4D", border=WINDOW),
        "success": dict(bg="#ECFAF3", fg=SUCCESS, hover="#DFF5EA", press="#D0EEDC", border="#DDF4E9"),
    }

    def __init__(self, parent, text="", command=None, variant="secondary",
                 radius=14, height=40, font=F_BUTTON, **kw):
        try:
            parent_bg = parent.cget("bg")
        except Exception:
            parent_bg = WINDOW
        try:
            measured = tkfont.Font(parent, font=font).measure(text) + 34
        except Exception:
            measured = 96
        width = kw.pop("width", None) or max(84, measured)
        super().__init__(
            parent,
            highlightthickness=0,
            bd=0,
            relief="flat",
            bg=parent_bg,
            height=height,
            width=width,
            cursor="hand2",
            **kw,
        )
        self._text = text
        self._command = command
        self._variant = variant
        self._radius = radius
        self._font = font
        self._enabled = True
        self._hover = False
        self._pressed = False
        self._hover_mix = 0.0
        self._anim_id = None
        self._colors = self._VARIANTS.get(variant, self._VARIANTS["secondary"])
        self.bind("<Configure>", self._redraw)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.after(30, self._redraw)

    def _state_colors(self):
        colors = self._colors
        if not self._enabled:
            return "#F3F5F8", TEXT_FAINT, "#E8ECF2"
        if self._pressed:
            return colors["press"], colors["fg"], colors["press"]
        fill = _lerp_color(colors["bg"], colors["hover"], self._hover_mix)
        border = _lerp_color(colors["border"], colors["hover"], self._hover_mix)
        return fill, colors["fg"], border

    def _redraw(self, _event=None):
        self.delete("all")
        width = self.winfo_width()
        height = self.winfo_height()
        if width < 8 or height < 8:
            return
        fill, fg, border = self._state_colors()
        inset = 1 if self._pressed else 0
        _round_polygon(
            self,
            1 + inset,
            1 + inset,
            width - 2 - inset,
            height - 2 - inset,
            self._radius,
            fill=fill,
            outline=border,
            width=1,
        )
        self.create_text(
            width / 2,
            height / 2 + (1 if self._pressed else 0),
            text=self._text,
            fill=fg,
            font=self._font,
        )

    def _animate(self):
        target = 1.0 if self._hover else 0.0
        if self._hover_mix < target:
            self._hover_mix = min(target, self._hover_mix + 0.18)
        elif self._hover_mix > target:
            self._hover_mix = max(target, self._hover_mix - 0.18)
        self._redraw()
        if self._hover_mix != target:
            self._anim_id = self.after(16, self._animate)
        else:
            self._anim_id = None

    def _ensure_animation(self):
        if self._anim_id is None:
            self._anim_id = self.after(16, self._animate)

    def _on_enter(self, _event):
        if not self._enabled:
            return
        self._hover = True
        self._ensure_animation()

    def _on_leave(self, _event):
        self._hover = False
        self._pressed = False
        self._ensure_animation()

    def _on_press(self, _event):
        if not self._enabled:
            return
        self._pressed = True
        self._redraw()

    def _on_release(self, event):
        if not self._enabled:
            return
        was_pressed = self._pressed
        self._pressed = False
        self._redraw()
        if not was_pressed:
            return
        x, y = event.x, event.y
        if 0 <= x <= self.winfo_width() and 0 <= y <= self.winfo_height():
            if callable(self._command):
                self._command()

    def configure(self, cnf=None, **kw):
        if cnf:
            kw.update(cnf)
        state = kw.pop("state", None)
        text = kw.pop("text", None)
        command = kw.pop("command", None)
        variant = kw.pop("variant", None)
        if state is not None:
            self._enabled = state != "disabled"
            super().configure(cursor="hand2" if self._enabled else "arrow")
        if text is not None:
            self._text = text
        if command is not None:
            self._command = command
        if variant is not None:
            self._variant = variant
            self._colors = self._VARIANTS.get(variant, self._VARIANTS["secondary"])
        super().configure(**kw)
        self._redraw()

    config = configure

    def cget(self, key):
        if key == "state":
            return "normal" if self._enabled else "disabled"
        if key == "text":
            return self._text
        return super().cget(key)


class WindowControlButton(ModernButton):
    def __init__(self, parent, kind: str, text="", command=None, variant="titlebar",
                 radius=8, height=32, width=46, **kw):
        self._kind = kind
        kw.pop("text", None)
        kw.pop("radius", None)
        kw.pop("height", None)
        kw.pop("width", None)
        super().__init__(
            parent,
            text="",
            command=command,
            variant=variant,
            radius=radius,
            height=height,
            width=width,
            **kw,
        )

    def configure(self, cnf=None, **kw):
        if cnf:
            kw.update(cnf)
        kind = kw.pop("kind", None)
        if kind is not None:
            self._kind = kind
        kw.pop("text", None)
        super().configure(**kw)

    config = configure

    def _draw_icon(self, width: int, height: int, fg: str, offset: int):
        cx = width / 2
        cy = height / 2 + offset
        if self._kind == "minimize":
            self.create_line(cx - 7, cy + 1, cx + 7, cy + 1, fill=fg, width=1.6, capstyle="round")
        elif self._kind == "maximize":
            self.create_rectangle(cx - 6, cy - 5, cx + 6, cy + 5, outline=fg, width=1.4)
        elif self._kind == "restore":
            self.create_rectangle(cx - 4, cy - 3, cx + 6, cy + 5, outline=fg, width=1.2)
            self.create_line(cx - 2, cy - 5, cx + 4, cy - 5, fill=fg, width=1.2)
            self.create_line(cx + 4, cy - 5, cx + 4, cy + 1, fill=fg, width=1.2)
            self.create_rectangle(cx - 7, cy - 6, cx + 3, cy + 2, outline=fg, width=1.2)
        elif self._kind == "close":
            self.create_line(cx - 6, cy - 6, cx + 6, cy + 6, fill=fg, width=1.7, capstyle="round")
            self.create_line(cx - 6, cy + 6, cx + 6, cy - 6, fill=fg, width=1.7, capstyle="round")

    def _redraw(self, _event=None):
        self.delete("all")
        width = self.winfo_width()
        height = self.winfo_height()
        if width < 8 or height < 8:
            return
        fill, fg, border = self._state_colors()
        inset = 1 if self._pressed else 0
        _round_polygon(
            self,
            1 + inset,
            1 + inset,
            width - 2 - inset,
            height - 2 - inset,
            self._radius,
            fill=fill,
            outline=border,
            width=1,
        )
        self._draw_icon(width, height, fg, 1 if self._pressed else 0)


# ?????
RoundedButton = ModernButton


# ---------- ???? ----------

@dataclass
class CommitItem:
    full_sha: str
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
    commits_has_more: bool


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
        self.app.write_log(f"寮€濮嬬洃鎺э細{self.repo_path}")
        while not self.stop_event.is_set():
            try:
                if self.app.repo_has_blocking_git_marker(self.repo_path):
                    self.app.write_log("检测到 Git 正在执行其他操作，本轮 auto commit 已跳过。")
                else:
                    commit_message = self.app.auto_commit_once(self.repo_path, self.prefix)
                    if commit_message:
                        self.app.request_status_refresh(force=True)
            except Exception as exc:
                self.app.write_log("auto commit 出错：" + str(exc))
            self.stop_event.wait(self.interval_seconds)
        self.app.write_log("监控已停止。")


# ---------- 涓诲簲鐢?----------

class AutoCommitApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Git 自动提交工具")
        self.root.configure(bg=WINDOW)
        self._size_window(1700, 1200)
        self.root.minsize(1400, 860)

        self.git_lock = threading.Lock()
        self.log_lock = threading.Lock()
        self.auto_worker: AutoCommitWorker | None = None
        self.refresh_running = False
        self.refresh_pending = False
        self.refresh_generation = 0
        self.busy = False
        self.log_window: tk.Toplevel | None = None
        self.log_text: tk.Text | None = None
        self.commit_rows: list[tk.Widget] = []
        self.commit_row_meta: dict[str, dict[str, object]] = {}
        self.empty_commit_row: tk.Widget | None = None
        self.commit_loading_row: tk.Widget | None = None
        self.displayed_commits: list[CommitItem] = []
        self.last_commit_signature: list[tuple[str, str, str]] = []
        self.last_rendered_checkout_sha: str | None = None
        self.last_rendered_commit_empty = False
        self.commit_refresh_limit = 30
        self.commit_history_limit = 30
        self.commit_history_step = 30
        self.commit_history_has_more = True
        self.commit_history_loading_more = False
        self.commit_history_check_job: str | None = None
        self.active_checkout_sha: str | None = None
        self.checkout_restore_ref: str | None = None
        self.checkout_restore_label: str | None = None
        self.window_drag_offset_x = 0
        self.window_drag_offset_y = 0
        self.window_is_maximized = False
        self.git_executable = self.resolve_git_executable()
        self.identity_cache_repo = ""
        self.identity_cache_name = ""
        self.identity_cache_email = ""
        self.identity_cache_loaded_at = 0.0

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
        self.rebuild_titlebar_buttons()
        for child in self.title_bar.winfo_children():
            if child not in (self.minimize_button, self.maximize_button, self.close_button):
                self.bind_window_drag(child)
        self.load_config()
        self.ensure_log_file()
        self.root.after(120, self.verify_git_ready)
        self.root.overrideredirect(True)
        self.root.after(80, lambda: ensure_appwindow(self.root))
        self.root.after(140, self.refresh_taskbar_presence)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.bind("<Map>", self.on_root_map)
        self.request_status_refresh()
        self.root.after(250, self.restore_auto_commit_state)

    def reset_repo_view_state(self):
        self.refresh_generation += 1
        self.commit_history_limit = 30
        self.commit_history_has_more = True
        self.commit_history_loading_more = False
        self.identity_cache_repo = ""
        self.identity_cache_loaded_at = 0.0
        self.active_checkout_sha = None
        self.checkout_restore_ref = None
        self.checkout_restore_label = None
        if self.commit_history_check_job is not None:
            try:
                self.root.after_cancel(self.commit_history_check_job)
            except Exception:
                pass
            self.commit_history_check_job = None
        self.displayed_commits = []
        self.last_commit_signature = []
        self.last_rendered_checkout_sha = None
        self.last_rendered_commit_empty = False
        self.clear_commit_rows()
        self.show_empty_commit_row()
        self.branch_var.set("branch -")
        self.worktree_var.set("工作区未连接")
        self.tip_var.set("正在读取当前项目状态...")
        self.push_state_var.set("待 push：0 条 commit")

    def rebuild_titlebar_buttons(self):
        for button in (
            getattr(self, "minimize_button", None),
            getattr(self, "maximize_button", None),
            getattr(self, "close_button", None),
        ):
            if button and button.winfo_exists():
                button.destroy()

        self.minimize_button = WindowControlButton(
            self.title_actions, kind="minimize", command=self.minimize_window, variant="titlebar"
        )
        self.minimize_button.grid(row=0, column=0, padx=(0, 2))
        self.maximize_button = WindowControlButton(
            self.title_actions, kind="maximize", command=self.toggle_maximize, variant="titlebar"
        )
        self.maximize_button.grid(row=0, column=1, padx=(0, 2))
        self.close_button = WindowControlButton(
            self.title_actions, kind="close", command=self.on_close, variant="titlebar_close"
        )
        self.close_button.grid(row=0, column=2)

    def _size_window(self, w, h):
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w = min(w, sw - 40)
        h = min(h, sh - 60)
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 3)
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def configure_style(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background=WINDOW, foreground=TEXT, fieldbackground=INPUT_BG,
                        bordercolor=INPUT_BORDER, lightcolor=INPUT_BORDER, darkcolor=INPUT_BORDER,
                        font=F_BODY)
        style.configure("TEntry", foreground=TEXT, fieldbackground=INPUT_BG, bordercolor=INPUT_BORDER,
                        insertcolor=TEXT, lightcolor=INPUT_BORDER, darkcolor=INPUT_BORDER, padding=12,
                        font=F_LABEL)
        style.map("TEntry", bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)],
                  darkcolor=[("focus", ACCENT)], fieldbackground=[("focus", INPUT_BG)])
        style.configure("TSpinbox", foreground=TEXT, fieldbackground=INPUT_BG, bordercolor=INPUT_BORDER,
                        arrowsize=16, padding=11, arrowcolor=TEXT_MUTED, font=F_LABEL)
        style.map("TSpinbox", bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)],
                  darkcolor=[("focus", ACCENT)])
        style.configure("Vertical.TScrollbar", background=CARD_BORDER, troughcolor=CARD_BG,
                        bordercolor=CARD_BG, arrowcolor=TEXT_MUTED, gripcount=0, arrowsize=16)
        style.configure("Horizontal.TScrollbar", background=CARD_BORDER, troughcolor=CARD_BG,
                        bordercolor=CARD_BG, arrowcolor=TEXT_MUTED, gripcount=0)
        style.configure("TSeparator", background=CARD_BORDER)

    # ---------- UI 鏋勫缓 ----------

    def build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        shell = tk.Frame(self.root, bg=WINDOW)
        shell.grid(row=0, column=0, sticky="nsew", padx=24, pady=20)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(2, weight=1)

        # 鏍囬鍖?
        self.title_bar = tk.Frame(shell, bg=WINDOW)
        self.title_bar.grid(row=0, column=0, sticky="ew")
        self.title_bar.columnconfigure(0, weight=1)
        self.title_bar.columnconfigure(1, weight=0)
        header = self.title_bar
        title_actions = tk.Frame(self.title_bar, bg=WINDOW)
        title_actions.grid(row=0, column=1, sticky="e")
        self.title_actions = title_actions
        self.minimize_button = WindowControlButton(
            title_actions, kind="minimize", text="-", command=self.minimize_window, variant="ghost",
        )
        self.minimize_button.grid(row=0, column=0, padx=(0, 2))
        self.maximize_button = WindowControlButton(
            title_actions, kind="maximize", text="□", command=self.toggle_maximize, variant="ghost",
            radius=12, font=("Segoe UI Semibold", 11), height=34, width=42,
        )
        self.maximize_button.grid(row=0, column=1, padx=(0, 2))
        self.close_button = WindowControlButton(
            title_actions, kind="close", text="×", command=self.on_close, variant="danger_outline",
            radius=12, font=("Segoe UI Semibold", 12), height=34, width=42,
        )
        self.close_button.grid(row=0, column=2)
        self.bind_window_drag(self.title_bar)
        tk.Label(header, text="Git 自动提交工具", bg=WINDOW, fg=TEXT,
                 font=F_TITLE).grid(row=0, column=0, sticky="w")

        # 椤堕儴鍙屽崱鐗?
        top = tk.Frame(shell, bg=WINDOW)
        top.grid(row=1, column=0, sticky="ew", pady=(16, 0))
        top.columnconfigure(0, weight=1, uniform="top")
        top.columnconfigure(1, weight=1, uniform="top")
        top.rowconfigure(0, weight=1)

        self._build_repo_card(top)
        self._build_control_card(top)

        # 涓讳綋鍙屽崱鐗?
        body = tk.Frame(shell, bg=WINDOW)
        body.grid(row=2, column=0, sticky="nsew", pady=(16, 0))
        body.columnconfigure(0, weight=7, uniform="body")
        body.columnconfigure(1, weight=3, uniform="body")
        body.rowconfigure(0, weight=1, minsize=380)

        self._build_history_card(body)
        self._build_side_card(body)




    def _build_repo_card(self, parent):
        card = RoundedCard(parent, radius=16, padding=18)
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        inner = card.inner
        inner.columnconfigure(0, weight=1)
        inner.columnconfigure(1, weight=0)

        tk.Label(inner, text="\u4ed3\u5e93\u8bbe\u7f6e", bg=CARD_BG, fg=TEXT,
                 font=F_CARD_TITLE).grid(row=0, column=0, sticky="w")

        tk.Label(inner, text="\u9879\u76ee\u6587\u4ef6\u5939", bg=CARD_BG, fg=TEXT_MUTED,
                 font=F_MUTED).grid(row=1, column=0, columnspan=2, sticky="w", pady=(12, 6))
        self.folder_entry = ttk.Entry(inner, textvariable=self.folder_var)
        self.folder_entry.grid(row=2, column=0, sticky="ew")
        self.browse_button = ModernButton(
            inner, text="\u9009\u62e9\u6587\u4ef6\u5939", command=self.choose_folder, variant="ghost",
            radius=14, font=F_BUTTON_SM, height=36, width=118,
        )
        self.browse_button.grid(row=2, column=1, sticky="e", padx=(10, 0))

        tk.Label(inner, text="GitHub \u94fe\u63a5", bg=CARD_BG, fg=TEXT_MUTED,
                 font=F_MUTED).grid(row=3, column=0, columnspan=2, sticky="w", pady=(12, 6))
        self.github_entry = ttk.Entry(inner, textvariable=self.github_var)
        self.github_entry.grid(row=4, column=0, columnspan=2, sticky="ew")

        id_row = tk.Frame(inner, bg=CARD_BG)
        id_row.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        id_row.columnconfigure(0, weight=3)
        id_row.columnconfigure(1, weight=4)
        tk.Label(id_row, text="Git \u7528\u6237\u540d", bg=CARD_BG, fg=TEXT_MUTED,
                 font=F_MUTED).grid(row=0, column=0, sticky="w", pady=(0, 6))
        tk.Label(id_row, text="Git \u90ae\u7bb1", bg=CARD_BG, fg=TEXT_MUTED,
                 font=F_MUTED).grid(row=0, column=1, sticky="w", pady=(0, 6), padx=(10, 0))
        self.username_entry = ttk.Entry(id_row, textvariable=self.username_var)
        self.username_entry.grid(row=1, column=0, sticky="ew")
        self.email_entry = ttk.Entry(id_row, textvariable=self.email_var)
        self.email_entry.grid(row=1, column=1, sticky="ew", padx=(10, 0))
        self.username_entry.bind("<KeyRelease>", self.on_identity_input_changed)
        self.email_entry.bind("<KeyRelease>", self.on_identity_input_changed)
        self.username_entry.bind("<<Paste>>", self.on_identity_input_changed)
        self.email_entry.bind("<<Paste>>", self.on_identity_input_changed)

    def _build_control_card(self, parent):
        card = RoundedCard(parent, radius=16, padding=18)
        card.grid(row=0, column=1, sticky="nsew")
        inner = card.inner
        inner.columnconfigure(0, weight=1)

        head = tk.Frame(inner, bg=CARD_BG)
        head.grid(row=0, column=0, sticky="ew")
        head.columnconfigure(0, weight=1)
        tk.Label(head, text="\u63a7\u5236\u680f", bg=CARD_BG, fg=TEXT,
                 font=F_CARD_TITLE).grid(row=0, column=0, sticky="w")
        self.mode_badge = tk.Label(head, textvariable=self.mode_var, bg=ROW_BG, fg=TEXT_MUTED,
                                   font=("Segoe UI Semibold", 9), padx=10, pady=4, relief="flat", borderwidth=0)
        self.mode_badge.grid(row=0, column=1, sticky="e")

        tk.Frame(inner, bg=CARD_BORDER, height=1).grid(row=1, column=0, sticky="ew", pady=(12, 12))

        switch_row = tk.Frame(inner, bg=CARD_BG)
        switch_row.grid(row=2, column=0, sticky="ew")
        switch_row.columnconfigure(0, weight=1)
        tk.Label(switch_row, text="Auto Commit", bg=CARD_BG, fg=TEXT,
                 font=("Segoe UI Semibold", 12)).grid(row=0, column=0, sticky="w")
        self.switch_canvas = tk.Canvas(switch_row, width=62, height=32, bg=CARD_BG,
                                       highlightthickness=0, bd=0, cursor="hand2")
        self.switch_canvas.grid(row=0, column=1, sticky="e")
        self.switch_canvas.bind("<Button-1>", self.on_switch_click)
        self.render_switch()

        field_row = tk.Frame(inner, bg=CARD_BG)
        field_row.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        field_row.columnconfigure(0, weight=0)
        field_row.columnconfigure(1, weight=1)
        tk.Label(field_row, text="\u95f4\u9694", bg=CARD_BG, fg=TEXT_MUTED,
                 font=F_MUTED).grid(row=0, column=0, sticky="w")
        tk.Label(field_row, text="Commit \u524d\u7f00", bg=CARD_BG, fg=TEXT_MUTED,
                 font=F_MUTED).grid(row=0, column=1, sticky="w", padx=(14, 0))
        interval_row = tk.Frame(field_row, bg=CARD_BG)
        interval_row.grid(row=1, column=0, sticky="w")
        self.interval_spin = ttk.Spinbox(interval_row, from_=2, to=3600, width=6, textvariable=self.interval_var)
        self.interval_spin.grid(row=0, column=0, sticky="w")
        tk.Label(interval_row, text="\u79d2", bg=CARD_BG, fg=TEXT_MUTED,
                 font=F_MUTED).grid(row=0, column=1, padx=(6, 0))
        self.prefix_entry = ttk.Entry(field_row, textvariable=self.prefix_var)
        self.prefix_entry.grid(row=1, column=1, sticky="ew", padx=(14, 0))

        primary_row = tk.Frame(inner, bg=CARD_BG)
        primary_row.grid(row=4, column=0, sticky="ew", pady=(14, 0))
        primary_row.columnconfigure(0, weight=1)
        primary_row.columnconfigure(1, weight=1)
        self.commit_button = ModernButton(
            primary_row, text="Commit", command=self.commit_now, variant="secondary",
            radius=14, font=F_BUTTON, height=38,
        )
        self.commit_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.push_button = ModernButton(
            primary_row, text="Push", command=self.push_to_github_safe, variant="primary",
            radius=14, font=F_BUTTON, height=38,
        )
        self.push_button.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        utility_row = tk.Frame(inner, bg=CARD_BG)
        utility_row.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        for idx in range(3):
            utility_row.columnconfigure(idx, weight=1)
        self.refresh_button = ModernButton(
            utility_row, text="\u5237\u65b0", command=self.request_status_refresh, variant="ghost",
            radius=14, font=F_BUTTON_SM, height=34,
        )
        self.refresh_button.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.logs_button = ModernButton(
            utility_row, text="\u65e5\u5fd7", command=self.open_log_window, variant="ghost",
            radius=14, font=F_BUTTON_SM, height=34,
        )
        self.logs_button.grid(row=0, column=1, sticky="ew", padx=5)
        self.init_button = ModernButton(
            utility_row, text="git init", command=self.git_init_repo, variant="warning",
            radius=14, font=F_BUTTON_SM, height=34,
        )
        self.init_button.grid(row=0, column=2, sticky="ew", padx=(5, 0))

        manage_row = tk.Frame(inner, bg=CARD_BG)
        manage_row.grid(row=6, column=0, sticky="ew", pady=(10, 0))
        manage_row.columnconfigure(0, weight=1)
        manage_row.columnconfigure(1, weight=1)
        self.identity_button = ModernButton(
            manage_row, text="\u4fdd\u5b58\u8eab\u4efd", command=self.save_identity, variant="secondary",
            radius=14, font=F_BUTTON_SM, height=34,
        )
        self.identity_button.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.gitignore_button = ModernButton(
            manage_row, text="\u7f16\u8f91 .gitignore", command=self.open_gitignore_with, variant="secondary",
            radius=14, font=F_BUTTON_SM, height=34,
        )
        self.gitignore_button.grid(row=0, column=1, sticky="ew", padx=(5, 0))

    def _build_history_card(self, parent):
        card = RoundedCard(parent, radius=16, padding=20)
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        inner = card.inner
        inner.columnconfigure(0, weight=1)
        inner.rowconfigure(1, weight=1)
        head = tk.Frame(inner, bg=CARD_BG)
        head.grid(row=0, column=0, columnspan=2, sticky="ew")
        head.columnconfigure(0, weight=1)
        tk.Label(head, text="Commit 记录", bg=CARD_BG, fg=TEXT,
                font=F_CARD_TITLE).grid(row=0, column=0, sticky="w")
        tk.Label(head, textvariable=self.branch_var, bg=CARD_BG, fg=TEXT_MUTED,
                font=F_MUTED).grid(row=0, column=1, sticky="e")

        self.commit_canvas = tk.Canvas(inner, bg=CARD_BG, highlightthickness=0, bd=0)
        self.commit_canvas.grid(row=1, column=0, sticky="nsew", pady=(14, 0))
        scroll = ttk.Scrollbar(inner, orient="vertical", command=self.commit_canvas.yview)
        scroll.grid(row=1, column=1, sticky="ns", pady=(14, 0))
        self.commit_canvas.configure(yscrollcommand=scroll.set)
        self.commit_list_frame = tk.Frame(self.commit_canvas, bg=CARD_BG)
        self.commit_list_frame.columnconfigure(0, weight=1)
        self.commit_canvas_window = self.commit_canvas.create_window((0, 0), window=self.commit_list_frame, anchor="nw")
        self.commit_list_frame.bind("<Configure>", lambda _e: self.commit_canvas.configure(scrollregion=self.commit_canvas.bbox("all")))
        self.commit_canvas.bind("<Configure>", self.on_commit_canvas_resize)
        self.commit_canvas.bind("<Enter>", self.bind_commit_mousewheel)
        self.commit_canvas.bind("<Leave>", self.unbind_commit_mousewheel)
        self.commit_list_frame.bind("<Enter>", self.bind_commit_mousewheel)
        self.commit_list_frame.bind("<Leave>", self.unbind_commit_mousewheel)

    def _build_side_card(self, parent):
        card = RoundedCard(parent, radius=16, padding=20)
        card.grid(row=0, column=1, sticky="nsew")
        inner = card.inner
        inner.rowconfigure(4, weight=1)
        tk.Label(inner, text="状态", bg=CARD_BG, fg=TEXT,
                 font=F_CARD_TITLE).grid(row=0, column=0, sticky="w")
        tk.Frame(inner, bg=CARD_BORDER, height=1).grid(row=1, column=0, sticky="ew", pady=(14, 0))
        tk.Label(inner, textvariable=self.worktree_var, bg=CARD_BG, fg=TEXT, anchor="w",
                 font=("Segoe UI Semibold", 13), pady=10).grid(row=2, column=0, sticky="ew")
        tk.Label(inner, textvariable=self.push_state_var, bg=ROW_BG, fg=TEXT, anchor="w", justify="left",
                 wraplength=320, font=F_BODY, padx=14, pady=12).grid(row=3, column=0, sticky="ew", pady=(8, 0))
        tk.Label(inner, textvariable=self.tip_var, bg=CARD_BG, fg=TEXT_MUTED, anchor="nw", justify="left",
                 wraplength=320, font=F_MUTED, pady=10).grid(row=4, column=0, sticky="new")
        tk.Label(inner, text="Push 记录", bg=CARD_BG, fg=TEXT_MUTED,
                 font=F_MUTED).grid(row=5, column=0, sticky="sw", pady=(12, 6))
        tk.Label(inner, textvariable=self.push_history_var, bg=ROW_BG, fg=TEXT_MUTED, anchor="nw", justify="left",
                 wraplength=320, font=F_MONO_SM, padx=14, pady=12).grid(row=6, column=0, sticky="sew")

    # ---------- 寮€鍏?/ 缁樺埗 ----------




    def draw_round_rect(self, canvas, x1, y1, x2, y2, radius, fill):
        _round_polygon(canvas, x1, y1, x2, y2, radius, fill=fill, outline=fill)

    def render_switch(self):
        enabled = self.enabled_var.get()
        self.switch_canvas.delete("all")
        width = int(float(self.switch_canvas.cget("width")))
        height = int(float(self.switch_canvas.cget("height")))
        track_color = ACCENT if enabled else SWITCH_OFF
        knob_size = height - 8
        knob_y1 = 4
        knob_y2 = knob_y1 + knob_size
        knob_x1 = width - knob_size - 4 if enabled else 4
        knob_x2 = knob_x1 + knob_size
        _round_polygon(
            self.switch_canvas,
            2,
            2,
            width - 2,
            height - 2,
            max(12, (height - 4) // 2),
            fill=track_color,
            outline=track_color,
        )
        self.switch_canvas.create_oval(
            knob_x1,
            knob_y1,
            knob_x2,
            knob_y2,
            fill=SWITCH_KNOB,
            outline="#DCE2EC",
        )
        self.switch_text_var.set("\u5df2\u5f00\u542f" if enabled else "\u5df2\u5173\u95ed")

    def on_switch_click(self, _event=None):
        if self.busy:
            return
        self.enabled_var.set(not self.enabled_var.get())
        self.render_switch()
        self.on_toggle()

    def bind_window_drag(self, widget):
        widget.bind("<ButtonPress-1>", self.start_window_drag)
        widget.bind("<B1-Motion>", self.perform_window_drag)
        widget.bind("<Double-Button-1>", self.on_titlebar_double_click)

    def start_window_drag(self, event):
        if self.window_is_maximized:
            return
        self.window_drag_offset_x = event.x_root - self.root.winfo_x()
        self.window_drag_offset_y = event.y_root - self.root.winfo_y()

    def perform_window_drag(self, event):
        if self.window_is_maximized:
            return
        x = event.x_root - self.window_drag_offset_x
        y = event.y_root - self.window_drag_offset_y
        self.root.geometry(f"+{x}+{y}")

    def on_titlebar_double_click(self, _event=None):
        self.toggle_maximize()

    def minimize_window(self):
        self.root.overrideredirect(False)
        self.root.iconify()

    def toggle_maximize(self):
        if self.window_is_maximized:
            self.root.state("normal")
            self.window_is_maximized = False
            self.maximize_button.configure(text="□")
        else:
            self.root.state("zoomed")
            self.window_is_maximized = True
            self.maximize_button.configure(text="❐")

    def toggle_maximize(self):
        if self.window_is_maximized:
            self.root.state("normal")
            self.window_is_maximized = False
            self.maximize_button.configure(kind="maximize", variant="titlebar")
        else:
            self.root.state("zoomed")
            self.window_is_maximized = True
            self.maximize_button.configure(kind="restore", variant="titlebar")

    def on_root_map(self, _event=None):
        if self.root.state() != "iconic":
            self.root.overrideredirect(True)
            self.root.after(0, lambda: ensure_appwindow(self.root))

    def refresh_taskbar_presence(self):
        try:
            self.root.withdraw()
            self.root.after(10, self.root.deiconify)
            self.root.after(30, lambda: ensure_appwindow(self.root))
        except Exception:
            pass

    def toggle_maximize(self):
        if self.window_is_maximized:
            self.root.state("normal")
            self.window_is_maximized = False
            self.maximize_button.configure(text="□", variant="titlebar")
        else:
            self.root.state("zoomed")
            self.window_is_maximized = True
            self.maximize_button.configure(text="❐", variant="titlebar")

    def toggle_maximize(self):
        if self.window_is_maximized:
            self.root.state("normal")
            self.window_is_maximized = False
            self.maximize_button.configure(kind="maximize", variant="titlebar")
        else:
            self.root.state("zoomed")
            self.window_is_maximized = True
            self.maximize_button.configure(kind="restore", variant="titlebar")

    def on_commit_canvas_resize(self, event):
        self.commit_canvas.itemconfigure(self.commit_canvas_window, width=event.width)

    def bind_commit_mousewheel(self, event=None):
        if event is not None:
            self.attach_commit_mousewheel(event.widget)

    def unbind_commit_mousewheel(self, _event=None):
        return

    def attach_commit_mousewheel(self, widget):
        if getattr(widget, "_commit_mousewheel_bound", False):
            return
        widget._commit_mousewheel_bound = True
        widget.bind("<MouseWheel>", self.on_commit_mousewheel)
        widget.bind("<Button-4>", self.on_commit_mousewheel)
        widget.bind("<Button-5>", self.on_commit_mousewheel)
        for child in widget.winfo_children():
            self.attach_commit_mousewheel(child)

    def on_commit_mousewheel(self, event):
        if event.delta:
            step = -1 * int(event.delta / 120) if event.delta else 0
        elif getattr(event, "num", None) == 4:
            step = -1
        else:
            step = 1
        if step:
            self.commit_canvas.yview_scroll(step, "units")
            self.schedule_commit_history_check()
        return "break"

    def schedule_commit_history_check(self):
        if self.commit_history_check_job is not None:
            try:
                self.root.after_cancel(self.commit_history_check_job)
            except Exception:
                pass
        self.commit_history_check_job = self.root.after(120, self.maybe_load_more_commit_history)

    def maybe_load_more_commit_history(self):
        self.commit_history_check_job = None
        if not self.commit_history_has_more or self.commit_history_loading_more:
            return
        start, end = self.commit_canvas.yview()
        if end < 0.98:
            return
        self.commit_history_loading_more = True
        self.show_commit_loading_row()
        repo_path = self.get_repo_path()
        if not repo_path:
            self.commit_history_loading_more = False
            self.hide_commit_loading_row()
            return

        skip_count = len(self.displayed_commits)
        limit = self.commit_history_step

        def work():
            try:
                more_commits = self.fetch_more_commits(repo_path, skip_count, limit)
                self.root.after(0, lambda: self.apply_more_commits(more_commits))
            except Exception as exc:
                self.write_log("加载更多 commit 失败：" + str(exc))
                self.root.after(0, self.finish_commit_history_load)

        threading.Thread(target=work, daemon=True).start()

    def ensure_log_file(self):
        log_path = self.get_log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        if not log_path.exists():
            log_path.write_text("", encoding="utf-8")

    def get_storage_dir(self) -> Path:
        return APP_DIR

    def get_legacy_storage_dirs(self) -> list[Path]:
        candidates: list[Path] = []
        if os.name == "nt":
            base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
            if base:
                candidates.append(Path(base) / APP_STORAGE_DIRNAME)
        return candidates

    def get_config_path(self) -> Path:
        return self.get_storage_dir() / CONFIG_FILENAME

    def get_legacy_config_candidates(self) -> list[Path]:
        candidates = [legacy_dir / CONFIG_FILENAME for legacy_dir in self.get_legacy_storage_dirs()]
        current_folder = self.folder_var.get().strip()
        if current_folder:
            candidates.append(Path(current_folder) / CONFIG_FILENAME)
        unique: list[Path] = []
        for candidate in candidates:
            if candidate not in unique:
                unique.append(candidate)
        return unique

    def get_log_path(self) -> Path:
        return self.get_storage_dir() / LOG_FILENAME

    def normalize_github_url(self, raw: str) -> str:
        value = (raw or "").strip()
        if not value:
            return ""
        value = value.replace("git@github.com:", "https://github.com/")
        if value.endswith(".git"):
            value = value[:-4]
        return value.rstrip("/")

    def ensure_gitignore_exists(self, folder_path: Path):
        gitignore_path = folder_path / ".gitignore"
        if gitignore_path.exists():
            return
        gitignore_path.write_text("", encoding="utf-8")
        self.write_log(f"\u5df2\u65b0\u5efa .gitignore\uff1a{gitignore_path}")

    def load_config(self):
        data = {}
        config_path = self.get_config_path()
        if config_path.exists():
            try:
                data = json.loads(config_path.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        else:
            for legacy_path in self.get_legacy_config_candidates():
                if not legacy_path.exists():
                    continue
                try:
                    data = json.loads(legacy_path.read_text(encoding="utf-8"))
                    break
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
        config_path = self.get_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)
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
        config_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def verify_git_ready(self):
        try:
            result = subprocess.run(
                self.git_command("--version"),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
                **self.get_subprocess_kwargs(),
            )
            version_text = (result.stdout or result.stderr or "").strip()
            if version_text:
                self.write_log("检测到 Git 环境：" + version_text)
        except Exception:
            self.tip_var.set("未检测到 Git，请先安装 Git for Windows。")
            self.show_error_async(
                "缺少 Git",
                "没有检测到可用的 Git。\n\n请先安装 Git for Windows，并确认命令行可以执行 git --version。",
            )

    def choose_folder(self):
        selected = filedialog.askdirectory(initialdir=self.folder_var.get() or str(APP_DIR))
        if not selected:
            return
        self.folder_var.set(selected)
        self.identity_inputs_dirty = False
        self.reset_repo_view_state()
        self.ensure_gitignore_exists(Path(selected))
        self.save_config()
        self.request_status_refresh(force=True)

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

    def run_on_ui_thread(self, callback, *args, **kwargs):
        if threading.current_thread() is threading.main_thread():
            return callback(*args, **kwargs)
        self.root.after(0, lambda: callback(*args, **kwargs))
        return None

    def get_subprocess_kwargs(self) -> dict[str, object]:
        kwargs: dict[str, object] = {}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            kwargs["startupinfo"] = startupinfo
            kwargs["env"] = self.get_external_process_env()
        return kwargs

    def get_external_process_env(self) -> dict[str, str]:
        env = os.environ.copy()
        if os.name != "nt":
            return env

        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            filtered_paths = []
            for entry in env.get("PATH", "").split(os.pathsep):
                normalized = entry.strip()
                if not normalized:
                    continue
                try:
                    if Path(normalized).resolve().is_relative_to(Path(meipass).resolve()):
                        continue
                except Exception:
                    if normalized.startswith(meipass):
                        continue
                filtered_paths.append(normalized)
            env["PATH"] = os.pathsep.join(filtered_paths)

        for key in ("_MEIPASS2", "PYTHONHOME", "PYTHONPATH"):
            env.pop(key, None)
        return env

    def resolve_git_executable(self) -> str:
        candidates = [
            shutil.which("git.exe"),
            shutil.which("git"),
            r"C:\Program Files\Git\cmd\git.exe",
            r"C:\Program Files\Git\bin\git.exe",
        ]
        for candidate in candidates:
            if candidate and Path(candidate).exists():
                return str(Path(candidate))
        return "git"

    def git_command(self, *args: str) -> list[str]:
        return [self.git_executable, *args]

    def show_error_async(self, title: str, message: str):
        self.run_on_ui_thread(messagebox.showerror, title, message)

    def show_info_async(self, title: str, message: str):
        self.run_on_ui_thread(messagebox.showinfo, title, message)

    def format_push_error_message(self, output: str) -> str:
        detail = (output or "").strip()
        if not detail:
            return "Push 失败，请稍后重试。"

        lowered = detail.lower()
        if "fetch first" in lowered or "non-fast-forward" in lowered or "[rejected]" in lowered:
            return (
                "Push 被远端拒绝了，因为远端分支比你本地更新。\n\n"
                "常见原因：这个仓库在别的地方已经推送过新提交。\n\n"
                "建议先执行：\n"
                "1. 先 pull / 同步远端改动\n"
                "2. 处理可能的冲突\n"
                "3. 再重新 push\n\n"
                "Git 原始信息：\n" + detail
            )
        if "not a git repository" in lowered:
            return "Push 失败：当前目录还不是可用的 Git 仓库。\n\n如果你刚执行过 git init，请先点一次刷新，或重新选择一次项目文件夹后再试。\n\nGit 原始信息：\n" + detail
        if "src refspec" in lowered and "does not match any" in lowered:
            return "Push 失败：当前仓库还没有任何提交。\n\n请先至少执行一次 Commit，再进行 Push。\n\nGit 原始信息：\n" + detail
        if "does not appear to be a git repository" in lowered or "no such remote" in lowered:
            return "Push 失败：还没有可用的远程仓库 origin。\n\n请先填写 GitHub 链接，再重新 Push。\n\nGit 原始信息：\n" + detail
        if "authentication failed" in lowered or "permission denied" in lowered:
            return "Push 失败，GitHub 认证或权限有问题。\n\n请检查账号权限、Token 或 Git 凭据设置。\n\nGit 原始信息：\n" + detail
        if "could not resolve host" in lowered or "failed to connect" in lowered:
            return "Push 失败，网络连接 GitHub 时出问题了。\n\n请检查网络、代理或 VPN 设置。\n\nGit 原始信息：\n" + detail
        return "Push 失败。\n\nGit 原始信息：\n" + detail

    def format_git_action_error(self, action_name: str, output: str) -> str:
        detail = (output or "").strip()
        if not detail:
            return f"{action_name}失败，请稍后重试。"

        lowered = detail.lower()
        if "not a git repository" in lowered:
            return f"{action_name}失败：当前目录不是 Git 仓库。\n\n请先确认项目目录里有 .git 文件夹。\n\nGit 原始信息：\n{detail}"
        if "index.lock" in lowered or "another git process" in lowered:
            return f"{action_name}失败：仓库里有另一个 Git 进程正在运行，或遗留了锁文件。\n\n请先关闭其他 Git 操作后再试。\n\nGit 原始信息：\n{detail}"
        if "dubious ownership" in lowered or "unsafe repository" in lowered:
            return f"{action_name}失败：Git 认为这个仓库目录不安全。\n\n请先在命令行里把它加入 safe.directory 后再试。\n\nGit 原始信息：\n{detail}"
        if "author identity unknown" in lowered or "please tell me who you are" in lowered:
            return f"{action_name}失败：当前仓库还没有配置 Git 用户名和邮箱。\n\n请先填写并保存身份信息。\n\nGit 原始信息：\n{detail}"
        if "nothing to commit" in lowered:
            return "没有新的改动需要提交。"
        return f"{action_name}失败。\n\nGit 原始信息：\n{detail}"

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
            subprocess.Popen(
                ["rundll32.exe", "shell32.dll,OpenAs_RunDLL", str(gitignore_path)],
                **self.get_subprocess_kwargs(),
            )
            self.write_log("已打开 .gitignore 的打开方式窗口：" + str(gitignore_path))
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
        if self.is_git_repository(folder_path):
            messagebox.showinfo("已经初始化", "这个项目文件夹已经有 .git 了。")
            return

        def work():
            self.set_busy(True)
            try:
                with self.git_lock:
                    result = subprocess.run(
                        self.git_command("init"),
                        cwd=folder_path,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        check=True,
                        **self.get_subprocess_kwargs(),
                    )
                if not self.is_git_repository(folder_path):
                    raise RuntimeError("git init 执行后，当前目录仍未被识别为可用的 Git 仓库。")
                self.ensure_gitignore_exists(folder_path)
                self.write_log((result.stdout or result.stderr or "").strip() or ("已执行 git init：" + str(folder_path)))
                messagebox.showinfo("初始化完成", "已执行 git init，现在这个文件夹已经是 Git 仓库。")
                self.run_on_ui_thread(self.reset_repo_view_state)
                self.run_on_ui_thread(self.request_status_refresh, True)
            except (subprocess.CalledProcessError, RuntimeError) as exc:
                output = (getattr(exc, "stdout", "") or getattr(exc, "stderr", "") or str(exc)).strip()
                self.write_log("git init 失败：" + output)
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
                self.identity_cache_repo = str(repo_path)
                self.identity_cache_name = username
                self.identity_cache_email = email
                self.identity_cache_loaded_at = time.monotonic()
                self.write_log(f"已设置 Git 身份：{username} <{email}>")
                self.save_config()
                messagebox.showinfo("保存完成", "Git 用户名和邮箱已经保存到当前仓库。")
                self.request_status_refresh()
            except subprocess.CalledProcessError as exc:
                output = (exc.stdout or exc.stderr or str(exc)).strip()
                self.write_log("保存身份失败：" + output)
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
        self.mode_badge.configure(bg=SUCCESS_SOFT, fg=SUCCESS)
        self.tip_var.set("Auto Commit 正在运行。")
        self.write_log("Auto Commit 已开启。")
        self.request_status_refresh()

    def stop_auto_commit(self, log_change=True, persist=False):
        if self.auto_worker:
            self.auto_worker.stop()
            self.auto_worker = None
        self.mode_var.set("空闲")
        self.mode_badge.configure(bg=ROW_BG, fg=TEXT_MUTED)
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

    def is_git_repository(self, folder_path: Path) -> bool:
        try:
            result = self.run_git(folder_path, "rev-parse", "--is-inside-work-tree", check=False)
        except Exception:
            return False
        return result.returncode == 0 and result.stdout.strip().lower() == "true"

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
        if not self.is_git_repository(repo_path):
            if show_errors:
                messagebox.showerror("不是 Git 仓库", f"这个目录当前还不是可用的 Git 仓库：\n{repo_path}")
            return None
        return repo_path

    def run_git(self, repo_path: Path, *args: str, check=True) -> subprocess.CompletedProcess:
        with self.git_lock:
            return subprocess.run(
                self.git_command(*args),
                cwd=repo_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=check,
                **self.get_subprocess_kwargs(),
            )

    def repo_has_blocking_git_marker(self, repo_path: Path) -> bool:
        git_dir = repo_path / ".git"
        return any((git_dir / name).exists() for name in ("MERGE_HEAD", "REBASE_HEAD", "CHERRY_PICK_HEAD", "BISECT_LOG"))

    def auto_commit_once(self, repo_path: Path, prefix: str) -> str | None:
        with self.git_lock:
            subprocess.run(
                self.git_command("add", "-A"),
                cwd=repo_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
                **self.get_subprocess_kwargs(),
            )
            diff = subprocess.run(
                self.git_command("diff", "--cached", "--quiet"),
                cwd=repo_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                **self.get_subprocess_kwargs(),
            )
            if diff.returncode == 0:
                return None
            if diff.returncode != 1:
                raise RuntimeError(diff.stderr.strip() or "git diff --cached 鎵ц澶辫触")
            message = f"{prefix}: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            result = subprocess.run(
                self.git_command("commit", "-m", message),
                cwd=repo_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
                **self.get_subprocess_kwargs(),
            )
        self.write_log((result.stdout or result.stderr or "").strip() or ("已 commit：" + message))
        return message

    def commit_now(self):
        repo_path = self.get_repo_path(show_errors=True)
        if not repo_path or self.busy:
            return
        self.ensure_gitignore_exists(repo_path)

        def work():
            self.set_busy(True)
            try:
                self.write_log("准备手动 commit，目标仓库：" + str(repo_path))
                commit_message = self.auto_commit_once(repo_path, self.prefix_var.get().strip() or "manual")
                if not commit_message:
                    self.write_log("没有新的改动需要 commit。")
                    self.run_on_ui_thread(self.tip_var.set, "没有新的改动需要提交。")
                    self.show_info_async("没有新的改动", "这次没有检测到新的改动，所以没有生成 commit。")
                else:
                    self.run_on_ui_thread(self.tip_var.set, "手动 Commit 已完成。")
                    self.show_info_async("Commit 已完成", "已成功生成提交：\n" + commit_message)
                self.request_status_refresh(force=True)
            except subprocess.CalledProcessError as exc:
                output = (exc.stdout or exc.stderr or str(exc)).strip()
                self.write_log("立即 commit 失败：" + output)
                messagebox.showerror("Commit 失败", self.format_git_action_error("Commit ", output))
            except Exception as exc:
                self.write_log("立即 commit 失败：" + str(exc))
                messagebox.showerror("Commit 失败", self.format_git_action_error("Commit ", str(exc)))
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
                    raise RuntimeError("当前处于 detached HEAD，无法直接确定要 push 的分支。")
                upstream = self.run_git(repo_path, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}", check=False)
                if upstream.returncode != 0 or not upstream.stdout.strip():
                    result = self.run_git(repo_path, "push", "--set-upstream", "origin", branch)
                else:
                    result = self.run_git(repo_path, "push")
                self.write_log((result.stdout or result.stderr or "").strip() or "Push 已完成。")
                self.push_state_var.set("待 push：0 条 commit | 最近 push 成功：" + datetime.now().strftime("%H:%M:%S"))
                self.append_push_history("push 成功")
                self.request_status_refresh()
            except (subprocess.CalledProcessError, RuntimeError) as exc:
                output = (exc.stdout or exc.stderr or str(exc)).strip()
                self.write_log("push 失败：" + output)
                self.push_state_var.set("待 push：未知 | 最近 push 失败：" + datetime.now().strftime("%H:%M:%S"))
                self.append_push_history("push 失败")
                messagebox.showerror("Push 失败", self.format_push_error_message(output))
            finally:
                self.set_busy(False)

        self.save_config()
        threading.Thread(target=work, daemon=True).start()

    def push_to_github_safe(self):
        repo_path = self.get_repo_path(show_errors=True)
        if not repo_path or self.busy:
            return
        self.ensure_gitignore_exists(repo_path)

        def work():
            self.set_busy(True)
            try:
                self.ensure_remote_url(repo_path)
                branch, created_recovery_branch = self.resolve_push_branch(repo_path)
                upstream = self.run_git(repo_path, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}", check=False)
                if created_recovery_branch or upstream.returncode != 0 or not upstream.stdout.strip():
                    result = self.run_git(repo_path, "push", "--set-upstream", "origin", branch)
                else:
                    result = self.run_git(repo_path, "push")
                output = (result.stdout or result.stderr or "").strip() or "Push 已完成。"
                self.write_log(output)
                if created_recovery_branch:
                    self.write_log("当前是 detached HEAD，已自动创建恢复分支：" + branch)
                success_time = datetime.now().strftime("%H:%M:%S")
                self.run_on_ui_thread(self.push_state_var.set, "待 push：0 条 commit | 最近 push 成功：" + success_time)
                history_message = f"push 成功 -> {branch}" if created_recovery_branch else "push 成功"
                self.run_on_ui_thread(self.append_push_history, history_message)
                if created_recovery_branch:
                    self.show_info_async("Push 已完成", "当前是 detached HEAD，已自动创建恢复分支并完成 push。\n" + branch + "\n\n后续请切回该分支继续开发。")
                self.run_on_ui_thread(self.request_status_refresh)
            except (subprocess.CalledProcessError, RuntimeError) as exc:
                output = (getattr(exc, "stdout", "") or getattr(exc, "stderr", "") or str(exc)).strip()
                self.write_log("push 失败：" + output)
                failed_time = datetime.now().strftime("%H:%M:%S")
                self.run_on_ui_thread(self.push_state_var.set, "待 push：未知 | 最近 push 失败：" + failed_time)
                self.run_on_ui_thread(self.append_push_history, "push 失败")
                self.show_error_async("Push 失败", self.format_push_error_message(output))
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
            self.write_log("已新增 origin：" + github_url)
        elif current_url != github_url:
            self.run_git(repo_path, "remote", "set-url", "origin", github_url)
            self.write_log("已更新 origin：" + github_url)

    def resolve_push_branch(self, repo_path: Path) -> tuple[str, bool]:
        branch = self.run_git(repo_path, "branch", "--show-current").stdout.strip()
        if branch:
            return branch, False
        head_sha = self.run_git(repo_path, "rev-parse", "--short", "HEAD").stdout.strip() or "head"
        recovery_branch = f"recovered/{datetime.now().strftime('%Y-%m-%d-%H%M%S')}-{head_sha}"
        self.run_git(repo_path, "checkout", "-b", recovery_branch)
        return recovery_branch, True

    def request_status_refresh(self, force=False):
        if self.refresh_running:
            if force:
                self.refresh_pending = True
            return
        repo_path = self.get_repo_path()
        if not repo_path:
            self.reset_repo_view_state()
            self.tip_var.set("请选择一个 Git 项目文件夹。")
            return
        request_generation = self.refresh_generation
        self.refresh_running = True

        def work():
            try:
                snapshot = self.collect_status(repo_path)
                self.root.after(0, lambda: self.apply_snapshot(snapshot, repo_path, request_generation))
            finally:
                self.refresh_running = False
                if self.refresh_pending:
                    self.refresh_pending = False
                    self.root.after(0, lambda: self.request_status_refresh(force=True))
                else:
                    self.root.after(8000, self.request_status_refresh)

        threading.Thread(target=work, daemon=True).start()

    def collect_status(self, repo_path: Path) -> RepoSnapshot:
        branch = self.run_git(repo_path, "branch", "--show-current").stdout.strip()
        if branch:
            branch_state = "姝ｅ父鍒嗘敮"
        else:
            head_result = self.run_git(repo_path, "rev-parse", "--short", "HEAD", check=False)
            head_sha = head_result.stdout.strip() or "-"
            if head_result.returncode == 0:
                branch = f"detached@{head_sha}"
                branch_state = "detached HEAD"
            else:
                branch = "unborn"
                branch_state = "empty repository"

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

        history_limit = self.commit_refresh_limit + 1
        history_result = self.run_git(
            repo_path,
            "log",
            f"-{history_limit}",
            "--date=format:%Y-%m-%d %H:%M:%S",
            "--pretty=%H|%h|%ad|%s",
            check=False,
        )
        history_lines = history_result.stdout.splitlines() if history_result.returncode == 0 else []
        commits: list[CommitItem] = []
        for line in history_lines[:self.commit_refresh_limit]:
            parts = line.split("|", 3)
            if len(parts) == 4:
                commits.append(CommitItem(full_sha=parts[0], sha=parts[1], timestamp=parts[2], message=parts[3]))
        commits_has_more = len(history_lines) > self.commit_refresh_limit
        self.commit_history_loading_more = False

        cache_key = str(repo_path)
        now = time.monotonic()
        should_refresh_identity = (
            cache_key != self.identity_cache_repo
            or now - self.identity_cache_loaded_at >= 30.0
            or (not self.identity_cache_name and not self.identity_cache_email)
        )
        if should_refresh_identity:
            config_name = self.run_git(repo_path, "config", "--get", "user.name", check=False).stdout.strip()
            config_email = self.run_git(repo_path, "config", "--get", "user.email", check=False).stdout.strip()
            self.identity_cache_repo = cache_key
            self.identity_cache_name = config_name
            self.identity_cache_email = config_email
            self.identity_cache_loaded_at = now
        else:
            config_name = self.identity_cache_name
            config_email = self.identity_cache_email
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
            commits_has_more=commits_has_more,
        )

    def apply_snapshot(self, snapshot: RepoSnapshot, repo_path: Path, request_generation: int):
        current_repo = self.get_repo_path()
        if request_generation != self.refresh_generation:
            return
        if not current_repo:
            return
        try:
            if current_repo.resolve() != repo_path.resolve():
                return
        except Exception:
            if current_repo != repo_path:
                return

        self.branch_var.set(f"branch {snapshot.branch}")
        if snapshot.branch_state == "empty repository":
            self.worktree_var.set("仓库已初始化，但还没有提交")
            self.tip_var.set("这是一个新的 Git 仓库。请先 Commit 一次，再执行 Push。")
        elif snapshot.branch_state == "detached HEAD":
            self.worktree_var.set("当前不在正常分支")
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
            empty = tk.Frame(self.commit_list_frame, bg=CARD_BG)
            empty.grid(row=0, column=0, sticky="ew")
            empty.columnconfigure(0, weight=1)
            tk.Label(empty, text="还没有可显示的 commit 记录", bg=CARD_BG, fg=TEXT_FAINT,
                     anchor="center", font=F_BODY, pady=32).grid(row=0, column=0, sticky="ew")
            self.commit_rows.append(empty)
            return
        for idx, item in enumerate(commits):
            row = RoundedCard(self.commit_list_frame, radius=12, fill=ROW_BG, outline=ROW_BG,
                              outline_width=0, bg=CARD_BG, padding=0)
            row.grid(row=idx, column=0, sticky="ew", pady=(0, 12))
            rinner = row.inner
            rinner.columnconfigure(1, weight=1)

            strip = tk.Frame(rinner, bg=ACCENT, width=4)
            strip.grid(row=0, column=0, sticky="ns")
            strip.grid_propagate(False)
            rinner.columnconfigure(0, weight=0)

            content = tk.Frame(rinner, bg=ROW_BG)
            content.grid(row=0, column=1, sticky="ew", padx=(16, 12), pady=16)
            content.columnconfigure(0, weight=1)
            tk.Label(content, text=item.sha, bg=ROW_BG, fg=ACCENT, anchor="w", justify="left",
                     font=F_MONO).grid(row=0, column=0, sticky="w")
            tk.Label(content, text=item.message, bg=ROW_BG, fg=TEXT, anchor="w", justify="left",
                     wraplength=520, font=F_BODY).grid(row=1, column=0, sticky="ew", pady=(6, 0))

            right = tk.Frame(rinner, bg=ROW_BG)
            right.grid(row=0, column=2, sticky="e", padx=(10, 16), pady=16)
            tk.Label(right, text=item.timestamp, bg=ROW_BG, fg=TEXT_MUTED,
                     font=F_MUTED).grid(row=0, column=0, padx=(0, 14))
            checkout_btn = ModernButton(
                right, text="切换到此版本", command=lambda sha=item.sha: self.checkout_commit(sha),
                variant="ghost", radius=12, font=F_BUTTON_SM, height=36,
            )
            checkout_btn.grid(row=0, column=1)
            self.attach_commit_mousewheel(row)
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
                self.write_log("已切换到 commit：" + sha)
                self.request_status_refresh()
            except subprocess.CalledProcessError as exc:
                output = (exc.stdout or exc.stderr or str(exc)).strip()
                self.write_log("切换失败：" + output)
                messagebox.showerror("切换失败", output)
            finally:
                self.set_busy(False)

        threading.Thread(target=work, daemon=True).start()

    def apply_snapshot(self, snapshot: RepoSnapshot, repo_path: Path, request_generation: int):
        current_repo = self.get_repo_path()
        if request_generation != self.refresh_generation:
            return
        if not current_repo:
            return
        try:
            if current_repo.resolve() != repo_path.resolve():
                return
        except Exception:
            if current_repo != repo_path:
                return

        self.branch_var.set(f"branch {snapshot.branch}")
        if snapshot.branch_state == "empty repository":
            self.worktree_var.set("仓库已初始化，但还没有提交")
            self.tip_var.set("这是一个新的 Git 仓库。请先 Commit 一次，再执行 Push。")
        elif snapshot.branch_state == "detached HEAD":
            self.worktree_var.set("当前不在正常分支")
            self.tip_var.set("当前是 detached HEAD，适合查看历史版本，但不适合长期开发。")
        elif snapshot.dirty:
            self.worktree_var.set(f"工作区有改动 {snapshot.changed_count}")
            self.tip_var.set("当前有未提交改动。等待 Auto Commit 或手动 Commit。")
        else:
            self.worktree_var.set("工作区干净")
            self.tip_var.set("当前工作区比较干净。")

        self.push_state_var.set(f"待 push：{snapshot.ahead} 条 commit")
        if self.active_checkout_sha:
            display_commits = self.displayed_commits
        else:
            display_commits = self.merge_displayed_commits(snapshot.commits)
        self.commit_history_has_more = snapshot.commits_has_more or len(display_commits) > len(snapshot.commits)
        self.render_commit_list(display_commits)

    def commit_signature(self, commits: list[CommitItem]) -> list[tuple[str, str, str]]:
        return [(item.sha, item.message, item.timestamp) for item in commits]

    def relayout_commit_rows(self):
        return

    def update_commit_scrollregion(self):
        self.commit_canvas.update_idletasks()
        bbox = self.commit_canvas.bbox("all")
        self.commit_canvas.configure(scrollregion=bbox)

    def capture_commit_scroll_state(self) -> dict[str, float | bool]:
        self.update_commit_scrollregion()
        bbox = self.commit_canvas.bbox("all")
        total_height = max(0, (bbox[3] - bbox[1]) if bbox else 0)
        viewport_height = max(1, self.commit_canvas.winfo_height())
        start, _end = self.commit_canvas.yview()
        max_top = max(0, total_height - viewport_height)
        top_px = self.commit_canvas.canvasy(0)
        return {
            "at_top": start <= 0.001,
            "top_px": max(0.0, min(float(top_px), float(max_top))),
            "start": float(start),
        }

    def restore_commit_scroll_state(self, state: dict[str, float | bool], added_height: float = 0.0):
        self.update_commit_scrollregion()
        if state.get("at_top"):
            self.commit_canvas.yview_moveto(0.0)
            return
        bbox = self.commit_canvas.bbox("all")
        total_height = max(0, (bbox[3] - bbox[1]) if bbox else 0)
        viewport_height = max(1, self.commit_canvas.winfo_height())
        max_top = max(0, total_height - viewport_height)
        target_top = float(state.get("top_px", 0.0)) + max(0.0, added_height)
        target_top = max(0.0, min(target_top, float(max_top)))
        fraction = 0.0 if max_top <= 0 else target_top / max_top
        self.commit_canvas.yview_moveto(fraction)

    def clear_commit_rows(self):
        for row in self.commit_rows:
            if row.winfo_exists():
                row.destroy()
        for child in self.commit_list_frame.winfo_children():
            if child.winfo_exists():
                child.destroy()
        self.commit_rows.clear()
        self.commit_row_meta.clear()
        self.empty_commit_row = None
        self.commit_loading_row = None

    def show_empty_commit_row(self):
        if self.empty_commit_row and self.empty_commit_row.winfo_exists():
            return
        empty = tk.Frame(self.commit_list_frame, bg=CARD_BG)
        empty.pack(fill="x")
        empty.columnconfigure(0, weight=1)
        tk.Label(
            empty,
            text="还没有可显示的 commit 记录",
            bg=CARD_BG,
            fg=TEXT_FAINT,
            anchor="center",
            font=F_BODY,
            pady=32,
        ).grid(row=0, column=0, sticky="ew")
        self.empty_commit_row = empty

    def hide_empty_commit_row(self):
        if self.empty_commit_row and self.empty_commit_row.winfo_exists():
            self.empty_commit_row.destroy()
        self.empty_commit_row = None

    def show_commit_loading_row(self):
        if self.commit_loading_row and self.commit_loading_row.winfo_exists():
            return
        loading = tk.Frame(self.commit_list_frame, bg=CARD_BG)
        loading.pack(fill="x", pady=(0, 10))
        loading.columnconfigure(0, weight=1)
        tk.Label(
            loading,
            text="正在加载更多提交记录...",
            bg=CARD_BG,
            fg=TEXT_MUTED,
            anchor="center",
            font=F_MUTED,
            pady=10,
        ).grid(row=0, column=0, sticky="ew")
        self.commit_loading_row = loading

    def hide_commit_loading_row(self):
        if self.commit_loading_row and self.commit_loading_row.winfo_exists():
            self.commit_loading_row.destroy()
        self.commit_loading_row = None

    def mount_commit_row(self, row: tk.Widget, before: tk.Widget | None = None):
        pack_kwargs = {"fill": "x", "pady": (0, 12)}
        if before is not None and before.winfo_exists():
            row.pack(before=before, **pack_kwargs)
        else:
            row.pack(**pack_kwargs)

    def fetch_more_commits(self, repo_path: Path, skip_count: int, limit: int) -> list[CommitItem]:
        history_lines = self.run_git(
            repo_path,
            "log",
            f"--skip={skip_count}",
            f"-{limit}",
            "--date=format:%Y-%m-%d %H:%M:%S",
            "--pretty=%H|%h|%ad|%s",
        ).stdout.splitlines()
        commits: list[CommitItem] = []
        for line in history_lines:
            parts = line.split("|", 3)
            if len(parts) == 4:
                commits.append(CommitItem(full_sha=parts[0], sha=parts[1], timestamp=parts[2], message=parts[3]))
        return commits

    def append_older_commit_rows(self, commits: list[CommitItem]):
        for item in commits:
            row = self.build_commit_row(item)
            self.mount_commit_row(row, before=self.commit_loading_row)
            self.commit_rows.append(row)

    def finish_commit_history_load(self):
        self.commit_history_loading_more = False
        self.hide_commit_loading_row()

    def apply_more_commits(self, commits: list[CommitItem]):
        if commits:
            self.append_older_commit_rows(commits)
            self.displayed_commits.extend(commits)
            self.last_commit_signature = self.commit_signature(self.displayed_commits)
            self.last_rendered_commit_empty = False
        self.commit_history_limit = max(self.commit_history_limit, len(self.displayed_commits))
        self.commit_history_has_more = len(commits) >= self.commit_history_step
        self.finish_commit_history_load()

    def update_commit_row(self, old_sha: str, item: CommitItem):
        meta = self.commit_row_meta.pop(old_sha)
        meta["item"] = item
        meta["sha_label"].configure(text=item.sha)
        meta["message_label"].configure(text=item.message)
        meta["time_label"].configure(text=item.timestamp)
        self.commit_row_meta[item.full_sha] = meta

    def get_prepend_count(self, commits: list[CommitItem]) -> int:
        if not self.displayed_commits:
            return 0
        for count in range(1, len(commits) + 1):
            if commits[count:] == self.displayed_commits[:len(commits) - count]:
                return count
        return 0

    def merge_displayed_commits(self, recent_commits: list[CommitItem]) -> list[CommitItem]:
        if not self.displayed_commits:
            return list(recent_commits)
        if len(self.displayed_commits) <= len(recent_commits):
            return list(recent_commits)
        current_prefix = self.displayed_commits[:len(recent_commits)]
        if current_prefix == recent_commits:
            return list(self.displayed_commits)

        overlap_count = self.get_prepend_count(recent_commits)
        if overlap_count > 0:
            tail_start = len(recent_commits) - overlap_count
            return list(recent_commits) + self.displayed_commits[tail_start:]
        return list(recent_commits)

    def sync_commit_rows(self, commits: list[CommitItem]):
        self.hide_empty_commit_row()
        self.hide_commit_loading_row()
        existing_meta = dict(self.commit_row_meta)
        new_row_order: list[tk.Widget] = []
        new_meta: dict[str, dict[str, object]] = {}

        for item in commits:
            meta = existing_meta.pop(item.full_sha, None)
            if meta is None:
                row = self.build_commit_row(item)
                meta = self.commit_row_meta[item.full_sha]
            else:
                row = meta["row"]
            row.pack_forget()
            self.mount_commit_row(row)
            new_row_order.append(row)
            new_meta[item.full_sha] = meta

        for meta in existing_meta.values():
            row = meta.get("row")
            if row:
                row.destroy()

        self.commit_rows = new_row_order
        self.commit_row_meta = new_meta

    def build_commit_row(self, item: CommitItem) -> tk.Widget:
        row = tk.Frame(self.commit_list_frame, bg=ROW_BG, highlightthickness=0, bd=0)
        row.columnconfigure(1, weight=1)

        strip = tk.Frame(row, bg=ACCENT, width=4)
        strip.grid(row=0, column=0, sticky="ns")
        strip.grid_propagate(False)
        row.columnconfigure(0, weight=0)

        content = tk.Frame(row, bg=ROW_BG)
        content.grid(row=0, column=1, sticky="ew", padx=(16, 12), pady=16)
        content.columnconfigure(0, weight=1)
        sha_label = tk.Label(content, text=item.sha, bg=ROW_BG, fg=ACCENT, anchor="w", justify="left",
                             font=F_MONO)
        sha_label.grid(row=0, column=0, sticky="w")
        message_label = tk.Label(content, text=item.message, bg=ROW_BG, fg=TEXT, anchor="w", justify="left",
                                 wraplength=520, font=F_BODY)
        message_label.grid(row=1, column=0, sticky="ew", pady=(6, 0))

        right = tk.Frame(row, bg=ROW_BG)
        right.grid(row=0, column=2, sticky="e", padx=(10, 16), pady=16)
        time_label = tk.Label(right, text=item.timestamp, bg=ROW_BG, fg=TEXT_MUTED,
                              font=F_MUTED)
        time_label.grid(row=0, column=0, padx=(0, 14))
        checkout_btn = ModernButton(
            right, text="切换到此版本", command=lambda commit_sha=item.full_sha: self.checkout_commit(commit_sha),
            variant="ghost", radius=12, font=F_BUTTON_SM, height=36,
        )
        checkout_btn.grid(row=0, column=1)
        self.attach_commit_mousewheel(row)
        self.commit_row_meta[item.full_sha] = {
            "row": row,
            "button": checkout_btn,
            "item": item,
            "sha_label": sha_label,
            "message_label": message_label,
            "time_label": time_label,
            "action_mode": None,
        }
        return row

    def render_commit_list(self, commits: list[CommitItem]):
        scroll_state = self.capture_commit_scroll_state()
        signature = self.commit_signature(commits)
        if not commits:
            self.displayed_commits = []
            self.last_commit_signature = []
            self.clear_commit_rows()
            empty = tk.Frame(self.commit_list_frame, bg=CARD_BG)
            empty.pack(fill="x")
            empty.columnconfigure(0, weight=1)
            tk.Label(empty, text="还没有可显示的 commit 记录", bg=CARD_BG, fg=TEXT_FAINT,
                     anchor="center", font=F_BODY, pady=32).grid(row=0, column=0, sticky="ew")
            self.commit_rows.append(empty)
            self.restore_commit_scroll_state(scroll_state)
            self.update_commit_action_buttons()
            return

        if not self.try_prepend_commit_rows(commits, signature) and signature != self.last_commit_signature:
            self.displayed_commits = list(commits)
            self.last_commit_signature = signature
            self.clear_commit_rows()
            for item in commits:
                row = self.build_commit_row(item)
                row.pack(fill="x", pady=(0, 12))
                self.commit_rows.append(row)
            self.restore_commit_scroll_state(scroll_state)
        self.update_commit_action_buttons()

    def try_prepend_commit_rows(self, commits: list[CommitItem], signature: list[tuple[str, str, str]]) -> bool:
        scroll_state = self.capture_commit_scroll_state()
        if not self.last_commit_signature or not self.displayed_commits:
            return False
        if len(self.commit_rows) != len(self.displayed_commits):
            return False

        prepend_count = None
        for count in range(1, len(commits) + 1):
            if commits[count:] == self.displayed_commits[:len(commits) - count]:
                prepend_count = count
                break
        if prepend_count is None:
            return False

        first_existing_row = self.commit_rows[0] if self.commit_rows else None
        new_rows = []
        for item in reversed(commits[:prepend_count]):
            row = self.build_commit_row(item)
            pack_kwargs = {"fill": "x", "pady": (0, 12)}
            if first_existing_row is not None:
                row.pack(before=first_existing_row, **pack_kwargs)
            else:
                row.pack(**pack_kwargs)
            new_rows.insert(0, row)
        self.commit_rows = new_rows + self.commit_rows
        self.displayed_commits = list(commits)
        self.last_commit_signature = signature

        while len(self.commit_rows) > len(commits):
            row = self.commit_rows.pop()
            row.destroy()
        valid_shas = {item.full_sha for item in commits}
        for commit_sha in list(self.commit_row_meta):
            if commit_sha not in valid_shas:
                self.commit_row_meta.pop(commit_sha, None)
        self.relayout_commit_rows()
        added_height = 0.0
        for row in new_rows:
            added_height += row.winfo_height() + 12
        self.restore_commit_scroll_state(scroll_state, added_height=added_height)
        return True

    def render_commit_list(self, commits: list[CommitItem]):
        signature = self.commit_signature(commits)
        is_empty = not commits
        checkout_state_changed = self.last_rendered_checkout_sha != self.active_checkout_sha
        if (
            signature == self.last_commit_signature
            and is_empty == self.last_rendered_commit_empty
            and not checkout_state_changed
        ):
            return

        scroll_state = self.capture_commit_scroll_state()
        if not commits:
            self.displayed_commits = []
            self.last_commit_signature = []
            self.clear_commit_rows()
            self.show_empty_commit_row()
            self.restore_commit_scroll_state(scroll_state)
            self.last_rendered_commit_empty = True
            self.last_rendered_checkout_sha = self.active_checkout_sha
            self.update_commit_action_buttons()
            return

        self.hide_empty_commit_row()
        self.hide_commit_loading_row()
        prepend_count = self.get_prepend_count(commits)
        if prepend_count > 0 and self.try_prepend_commit_rows(commits, signature, scroll_state, prepend_count):
            self.last_rendered_commit_empty = False
            self.last_rendered_checkout_sha = self.active_checkout_sha
            self.update_commit_action_buttons()
            return

        if signature != self.last_commit_signature:
            self.sync_commit_rows(commits)
            self.displayed_commits = list(commits)
            self.last_commit_signature = signature
            self.restore_commit_scroll_state(scroll_state)
        self.last_rendered_commit_empty = False
        self.last_rendered_checkout_sha = self.active_checkout_sha
        self.update_commit_action_buttons()

    def try_prepend_commit_rows(self, commits: list[CommitItem], signature: list[tuple[str, str, str]],
                                scroll_state: dict[str, float | bool], prepend_count: int) -> bool:
        if not self.last_commit_signature or not self.displayed_commits:
            return False
        if len(self.commit_rows) != len(self.displayed_commits):
            return False
        if prepend_count <= 0:
            return False

        first_existing_row = self.commit_rows[0] if self.commit_rows else None
        new_rows = []
        for item in reversed(commits[:prepend_count]):
            row = self.build_commit_row(item)
            self.mount_commit_row(row, before=first_existing_row)
            new_rows.insert(0, row)
        self.commit_rows = new_rows + self.commit_rows
        self.displayed_commits = list(commits)
        self.last_commit_signature = signature

        while len(self.commit_rows) > len(commits):
            row = self.commit_rows.pop()
            row.destroy()
        valid_shas = {item.full_sha for item in commits}
        for commit_sha in list(self.commit_row_meta):
            if commit_sha not in valid_shas:
                self.commit_row_meta.pop(commit_sha, None)
        added_height = 0.0
        for row in new_rows:
            added_height += row.winfo_reqheight() + 12
        self.restore_commit_scroll_state(scroll_state, added_height=added_height)
        return True

    def update_commit_action_buttons(self):
        for commit_sha, meta in self.commit_row_meta.items():
            button = meta.get("button")
            if not button:
                continue
            if commit_sha == self.active_checkout_sha:
                button.configure(text="取消此次切换", command=self.cancel_checkout, variant="danger_outline")
            else:
                button.configure(
                    text="切换到此版本",
                    command=lambda target_sha=commit_sha: self.checkout_commit(target_sha),
                    variant="ghost",
                )

    def update_commit_action_buttons(self):
        for commit_sha, meta in self.commit_row_meta.items():
            button = meta.get("button")
            if not button:
                continue
            if commit_sha == self.active_checkout_sha:
                if meta.get("action_mode") != "cancel":
                    button.configure(text="取消此次切换", command=self.cancel_checkout, variant="danger_outline")
                    meta["action_mode"] = "cancel"
            else:
                if meta.get("action_mode") != "checkout":
                    button.configure(
                        text="切换到此版本",
                        command=lambda target_sha=commit_sha: self.checkout_commit(target_sha),
                        variant="ghost",
                    )
                    meta["action_mode"] = "checkout"

    def checkout_commit(self, sha: str):
        repo_path = self.get_repo_path(show_errors=True)
        if not repo_path or self.busy:
            return
        if not messagebox.askyesno("切换版本", f"将切换到 commit {sha[:7]}。\n这会进入该版本状态，是否继续？"):
            return

        def work():
            self.set_busy(True)
            try:
                if self.active_checkout_sha and self.checkout_restore_ref:
                    restore_ref = self.checkout_restore_ref
                    restore_label = self.checkout_restore_label or self.checkout_restore_ref
                else:
                    restore_ref, restore_label = self.capture_checkout_restore_target(repo_path)
                self.run_git(repo_path, "checkout", sha)
                self.active_checkout_sha = sha
                self.checkout_restore_ref = restore_ref
                self.checkout_restore_label = restore_label
                self.write_log("已切换到 commit：" + sha)
                self.run_on_ui_thread(self.update_commit_action_buttons)
                self.run_on_ui_thread(self.request_status_refresh)
            except subprocess.CalledProcessError as exc:
                output = (exc.stdout or exc.stderr or str(exc)).strip()
                self.write_log("切换失败：" + output)
                self.show_error_async("鍒囨崲澶辫触", output)
            finally:
                self.set_busy(False)

        threading.Thread(target=work, daemon=True).start()

    def cancel_checkout(self):
        repo_path = self.get_repo_path(show_errors=True)
        if not repo_path or self.busy or not self.active_checkout_sha or not self.checkout_restore_ref:
            return

        restore_ref = self.checkout_restore_ref
        restore_label = self.checkout_restore_label or restore_ref
        active_sha = self.active_checkout_sha

        def work():
            self.set_busy(True)
            try:
                self.run_git(repo_path, "checkout", restore_ref)
                self.write_log(f"宸插彇娑堝垏鎹細{active_sha} -> {restore_label}")
                self.active_checkout_sha = None
                self.checkout_restore_ref = None
                self.checkout_restore_label = None
                self.run_on_ui_thread(self.update_commit_action_buttons)
                self.run_on_ui_thread(self.request_status_refresh)
            except subprocess.CalledProcessError as exc:
                output = (exc.stdout or exc.stderr or str(exc)).strip()
                self.write_log("取消切换失败：" + output)
                self.show_error_async("鍙栨秷鍒囨崲澶辫触", output)
            finally:
                self.set_busy(False)

        threading.Thread(target=work, daemon=True).start()

    def capture_checkout_restore_target(self, repo_path: Path) -> tuple[str, str]:
        branch_result = self.run_git(repo_path, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
        branch = branch_result.stdout.strip()
        if branch:
            return branch, branch
        full_sha = self.run_git(repo_path, "rev-parse", "HEAD").stdout.strip()
        short_sha = self.run_git(repo_path, "rev-parse", "--short", "HEAD").stdout.strip() or full_sha[:7]
        return full_sha, f"detached@{short_sha}"

    def open_log_window(self):
        if self.log_window and self.log_window.winfo_exists():
            self.log_window.lift()
            self.refresh_log_window()
            return
        win = tk.Toplevel(self.root)
        win.title("杩愯鏃ュ織")
        win.configure(bg=WINDOW)
        win.columnconfigure(0, weight=1)
        win.rowconfigure(1, weight=1)
        self._size_toplevel(win, 1040, 680)

        top = tk.Frame(win, bg=WINDOW)
        top.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 0))
        top.columnconfigure(0, weight=1)
        tk.Label(top, text="杩愯鏃ュ織", bg=WINDOW, fg=TEXT, font=F_CARD_TITLE).grid(row=0, column=0, sticky="w")
        tk.Label(top, text="日志文件：当前项目目录", bg=WINDOW, fg=TEXT_MUTED,
                 font=F_MUTED).grid(row=1, column=0, sticky="w", pady=(4, 0))
        refresh_btn = ModernButton(
            top, text="鍒锋柊鏃ュ織", command=self.refresh_log_window, variant="secondary",
            radius=12, font=F_BUTTON_SM, height=40,
        )
        refresh_btn.grid(row=0, column=1, rowspan=2, padx=(12, 0))

        body = RoundedCard(win, radius=16, padding=4)
        body.grid(row=1, column=0, sticky="nsew", padx=20, pady=18)
        binner = body.inner
        binner.columnconfigure(0, weight=1)
        binner.rowconfigure(0, weight=1)
        self.log_text = tk.Text(binner, wrap="word", state="disabled", bg=CARD_BG, fg=TEXT,
                                insertbackground=TEXT, relief="flat", borderwidth=0,
                                font=F_MONO, padx=16, pady=16, highlightthickness=0)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(binner, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set)

        self.log_window = win
        self.refresh_log_window()

    def _size_toplevel(self, win, w, h):
        win.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w = min(w, sw - 80)
        h = min(h, sh - 100)
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 3)
        win.geometry(f"{w}x{h}+{x}+{y}")

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

    def open_log_window(self):
        if self.log_window and self.log_window.winfo_exists():
            self.log_window.lift()
            self.refresh_log_window()
            return
        win = tk.Toplevel(self.root)
        win.title("运行日志")
        win.configure(bg=WINDOW)
        win.columnconfigure(0, weight=1)
        win.rowconfigure(1, weight=1)
        self._size_toplevel(win, 1040, 680)

        top = tk.Frame(win, bg=WINDOW)
        top.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 0))
        top.columnconfigure(0, weight=1)
        log_path = self.get_log_path()
        log_path_text = str(log_path) if log_path else "未选择项目，暂无日志文件"
        tk.Label(top, text="运行日志", bg=WINDOW, fg=TEXT, font=F_CARD_TITLE).grid(row=0, column=0, sticky="w")
        tk.Label(top, text=f"日志文件：{log_path_text}", bg=WINDOW, fg=TEXT_MUTED,
                 font=F_MUTED).grid(row=1, column=0, sticky="w", pady=(4, 0))
        refresh_btn = ModernButton(
            top, text="刷新日志", command=self.refresh_log_window, variant="secondary",
            radius=12, font=F_BUTTON_SM, height=40,
        )
        refresh_btn.grid(row=0, column=1, rowspan=2, padx=(12, 0))

        body = RoundedCard(win, radius=16, padding=4)
        body.grid(row=1, column=0, sticky="nsew", padx=20, pady=18)
        binner = body.inner
        binner.columnconfigure(0, weight=1)
        binner.rowconfigure(0, weight=1)
        self.log_text = tk.Text(
            binner,
            wrap="word",
            state="disabled",
            bg=CARD_BG,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            borderwidth=0,
            font=F_MONO,
            padx=16,
            pady=16,
            highlightthickness=0,
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(binner, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set)

        self.log_window = win
        self.refresh_log_window()

    def refresh_log_window(self):
        if not self.log_window or not self.log_window.winfo_exists() or not self.log_text:
            return
        log_path = self.get_log_path()
        content = log_path.read_text(encoding="utf-8", errors="replace") if log_path and log_path.exists() else ""
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.insert("1.0", content)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def write_log(self, text: str):
        log_path = self.get_log_path()
        if log_path is None:
            return
        line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {text}"
        with self.log_lock:
            if not log_path.exists():
                log_path.write_text("", encoding="utf-8")
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
    def set_busy(self, is_busy: bool):
        if threading.current_thread() is not threading.main_thread():
            self.root.after(0, lambda: self.set_busy(is_busy))
            return
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
            try:
                widget.configure(state=state)
            except Exception:
                pass
        self.switch_canvas.configure(cursor="arrow" if self.busy else "hand2")
        if self.busy:
            self.mode_var.set("处理中")
            self.mode_badge.configure(bg=WARN_SOFT, fg=WARN)
        elif self.auto_worker and self.auto_worker.is_alive():
            self.mode_var.set("监控中")
            self.mode_badge.configure(bg=SUCCESS_SOFT, fg=SUCCESS)
        else:
            self.mode_var.set("空闲")
            self.mode_badge.configure(bg=ROW_BG, fg=TEXT_MUTED)
        self.render_switch()


def main():
    enable_high_dpi()
    configure_tk_runtime()
    reset_external_dll_search_path()
    root = tk.Tk()
    apply_dpi_scaling(root)
    AutoCommitApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
