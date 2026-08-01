# -*- mode: python ; coding: utf-8 -*-
# Onedir Windows build (Nexus / Production). UPX off — AV false positives.
from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

datas = []
binaries = []
hiddenimports = [
    'mmh3',
    'REMSG',
    'REMSGUtil',
    'REWString',
    'HexTool',
]

# Themes / DnD natives only — not collect_all (avoids dist-info + extras).
datas += collect_data_files('customtkinter')
binaries += collect_dynamic_libs('customtkinter')
datas += collect_data_files('tkinterdnd2')
binaries += collect_dynamic_libs('tkinterdnd2')

# chardet (REMSG) ships many mypyc pipeline extensions — collect them all.
hiddenimports += collect_submodules('chardet')
binaries += collect_dynamic_libs('chardet')

datas += [('re2_outfit_converter/assets', 're2_outfit_converter/assets')]
datas += [('re2_outfit_converter/vendor/remsg', 're2_outfit_converter/vendor/remsg')]


def _runtime_toc(entries):
    """Drop metadata / tests / stray docs that clutter _internal."""
    kept = []
    for entry in entries:
        dest = str(entry[0]).replace('\\', '/').lower()
        if '.dist-info/' in dest or dest.endswith('.dist-info'):
            continue
        if '/tests/' in dest or dest.startswith('tests/'):
            continue
        if '/test/' in dest or dest.startswith('test/'):
            continue
        if dest.endswith('.md') and 're2_outfit_converter/' not in dest:
            continue
        kept.append(entry)
    return kept


a = Analysis(
    ['main.py'],
    pathex=['.', 're2_outfit_converter/vendor/remsg'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={
        'pil': {
            'include_plugins': [
                'BmpImagePlugin',
                'GifImagePlugin',
                'JpegImagePlugin',
                'PngImagePlugin',
                'WebPImagePlugin',
            ],
        },
    },
    runtime_hooks=[],
    excludes=[
        'numpy',
        'numpy.libs',
        'pytest',
        '_pytest',
        'py',
        'pluggy',
    ],
    noarchive=False,
    optimize=0,
)
a.datas = _runtime_toc(a.datas)
a.binaries = _runtime_toc(a.binaries)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='RE2 Outfit Converter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='re2_outfit_converter/assets/app_icon.ico',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='RE2 Outfit Converter',
)
