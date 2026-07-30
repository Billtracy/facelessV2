# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller build spec for the Faceless Channel Generator.
# Build with:  pyinstaller --noconfirm main.spec
#
# This mirrors the verified one-line command in BUILD_INSTRUCTIONS.md so the
# two never drift apart. Output goes to dist/FacelessGenerator/.

import os
from PyInstaller.utils.hooks import collect_all, copy_metadata

datas = []
binaries = []
hiddenimports = [
    "pydub",
    "requests",          # used by the LLM/Pexels clients and youtube_uploader
    "PIL",
    "PIL.ImageDraw",
    "PIL.ImageFont",
    "numpy",
    "soundfile",         # used by sound_preview voice samples
    "tkinter",
    "tkinter.ttk",
    "tkinter.font",
]

# --collect-all equivalents: pull in every submodule, data file and binary.
for pkg in (
    "customtkinter",
    "groq",
    "edge_tts",
    "movis",
    "kokoro_onnx",
    "imageio_ffmpeg",    # CRITICAL: bundles the ffmpeg binary
    "google.genai",
    "language_tags",
    "pykakasi",
    "espeakng_loader",
    "phonemizer",
):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# --copy-metadata equivalents (version resolution at runtime).
for pkg in ("imageio", "requests", "packaging"):
    datas += copy_metadata(pkg)

# --add-data equivalents (bundled assets, template, TTS model).
datas += [
    ("settings_template.json", "."),
    ("assets", "assets"),
]
for model_file in ("kokoro-v0_19.int8.onnx", "voices.bin"):
    model_path = os.path.join("models", model_file)
    if os.path.exists(model_path):
        datas += [(model_path, "models")]

icon_file = "icon.ico" if os.path.exists("icon.ico") else None


a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FacelessGenerator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # --windowed
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="FacelessGenerator",
)
