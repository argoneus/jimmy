# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

# pypandoc: https://github.com/orgs/pyinstaller/discussions/8387
datas = []
datas += collect_data_files('pypandoc')


# Generate list of hidden imports
# hidden import for dynamically loaded modules "apps.*":
# - https://stackoverflow.com/a/77395744/7410886
# - https://stackoverflow.com/a/35805418/7410886
# - https://pyinstaller.org/en/stable/when-things-go-wrong.html#listing-hidden-imports
from pathlib import Path
def list_python_files(folder):
    file_list = []
    for file_ in folder.iterdir():
        if file_.suffix == ".py" and file_.name != "__init__.py":
            file_list.append(f"{folder.stem}.{file_.stem}")
    return file_list

hiddenimports = list_python_files(Path("src/apps"))


a = Analysis(
    ['src/joplin_custom_importer.py'],
    pathex=[],
    binaries=[],
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
    a.binaries,
    a.datas,
    [],
    name='joplin_custom_importer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)