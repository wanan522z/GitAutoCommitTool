# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys


base_prefix = Path(sys.base_prefix)
tcl_root = base_prefix / "tcl"
dll_root = base_prefix / "DLLs"

hiddenimports = [
    "_tkinter",
]

binaries = [
    (str(dll_root / "_tkinter.pyd"), "."),
    (str(dll_root / "tcl86t.dll"), "."),
    (str(dll_root / "tk86t.dll"), "."),
]

datas = []
tkinter_lib = base_prefix / "Lib" / "tkinter"
if tkinter_lib.exists():
    for path in tkinter_lib.rglob("*"):
        if not path.is_file():
            continue
        relative_parent = path.relative_to(tkinter_lib).parent
        destination = "tkinter"
        if relative_parent != Path("."):
            destination = f"tkinter/{relative_parent.as_posix()}"
        datas.append((str(path), destination))
for folder_name, destination_root in (("tcl8.6", "_tcl_data"), ("tk8.6", "_tk_data")):
    folder = tcl_root / folder_name
    if folder.exists():
        for path in folder.rglob("*"):
            if not path.is_file():
                continue
            relative_parent = path.relative_to(folder).parent
            destination = destination_root
            if relative_parent != Path("."):
                destination = f"{destination_root}/{relative_parent.as_posix()}"
            datas.append((str(path), destination))

tcl_modules_dir = tcl_root / "tcl8"
if tcl_modules_dir.exists():
    for path in tcl_modules_dir.rglob("*"):
        if not path.is_file():
            continue
        relative_parent = path.relative_to(tcl_modules_dir).parent
        destination = "tcl8"
        if relative_parent != Path("."):
            destination = f"tcl8/{relative_parent.as_posix()}"
        datas.append((str(path), destination))


a = Analysis(
    ['git_auto_commit_gui.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['pyi_rth_custom_tkinter_path.py'],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='GitAutoCommitTool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
