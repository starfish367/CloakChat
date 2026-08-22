# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec cho CloakChat GUI trên Windows/Linux."""
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

# Không dùng collect_all("kivy"): một số bản PyInstaller/Kivy quét
# kivy.garden với path không hợp lệ. Chỉ thu thập các package cần thiết.
kivy_datas = collect_data_files("kivy")
kivy_binaries = collect_dynamic_libs("kivy")
kivy_hiddenimports = (
    collect_submodules("kivy.core")
    + collect_submodules("kivy.uix")
    + [
        "kivy.factory_registers",
        "kivy.core.window.window_sdl2",
        "kivy.core.text.text_sdl2",
        "kivy.core.image.img_pil",
        "kivy.core.image.img_sdl2",
    ]
)

project_dir = Path(SPEC).parent
binary_data = []
tor_binary = project_dir / "tor_bin" / "tor.exe"
if tor_binary.is_file():
    binary_data.append((str(tor_binary), "tor_bin"))

analysis = Analysis(
    [str(project_dir / "cloakchat_gui.py")],
    pathex=[str(project_dir)],
    binaries=kivy_binaries,
    datas=kivy_datas + binary_data,
    hiddenimports=kivy_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="CloakChatGUI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
