# -*- mode: python ; coding: utf-8 -*-
# Single-file Windows release (few loose files after extract).
# UPX off — packed binaries often trip Nexus / AV false positives.
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = [
    'mmh3',
    'chardet',
    'chardet.pipeline',
    'chardet.pipeline.orchestrator',
    'chardet.pipeline.orchestrator__mypyc',
    'REMSG',
    'REMSGUtil',
    'REWString',
    'HexTool',
]
tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('tkinterdnd2')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('chardet')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
try:
    tmp_ret = collect_all('mmh3')
    datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
except Exception:
    pass
datas += [('re2_outfit_converter/assets', 're2_outfit_converter/assets')]
datas += [('re2_outfit_converter/vendor/remsg', 're2_outfit_converter/vendor/remsg')]


a = Analysis(
    ['main.py'],
    pathex=['.', 're2_outfit_converter/vendor/remsg'],
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
    a.binaries,
    a.datas,
    [],
    name='RE2 Outfit Converter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='re2_outfit_converter/assets/app_icon.ico',
)
