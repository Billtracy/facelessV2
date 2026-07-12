# -*- mode: python ; coding: utf-8 -*-
#
# Build with:  pyinstaller --noconfirm main.spec
#
# This spec is the single source of truth for the Windows build. It bundles
# every data file and native library the app needs at runtime; do not build
# with ad-hoc CLI flags.

import os
from PyInstaller.utils.hooks import collect_all, copy_metadata

datas = [
    ('settings_template.json', '.'),
    ('assets', 'assets'),
]
binaries = []
hiddenimports = [
    'pydub',
    'soundfile',
    'PIL.ImageDraw',
    'PIL.ImageFont',
    'tkinter',
    'tkinter.ttk',
    'tkinter.font',
    # imported lazily in logic.py, so PyInstaller can't discover it
    'google.genai',
]

# Packages whose data files / native libraries must ship inside the bundle:
# - customtkinter: theme JSON files
# - kokoro_onnx + espeakng_loader + phonemizer: espeak-ng DLL and
#   espeak-ng-data (kokoro's tokenizer loads them at runtime)
# - imageio_ffmpeg: the ffmpeg.exe binary (audio loading + video mux)
# - imageio / movis / librosa: lazily-loaded plugins and data registries
collect_packages = (
    'customtkinter',
    'movis',
    'kokoro_onnx',
    'espeakng_loader',
    'phonemizer',
    'imageio_ffmpeg',
    'imageio',
    'librosa',
    'edge_tts',
    'groq',
    'google.genai',
)
for pkg in collect_packages:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as e:
        print(f"[main.spec] WARNING: could not collect '{pkg}': {e}")

# Version metadata some libraries look up at runtime
for meta in ('requests', 'packaging', 'imageio', 'imageio-ffmpeg'):
    try:
        datas += copy_metadata(meta)
    except Exception:
        pass

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='FacelessGenerator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX corrupts some DLLs (onnxruntime, tcl/tk) and triggers antivirus
    # false positives - keep it off
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico' if os.path.exists('icon.ico') else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='FacelessGenerator',
)
