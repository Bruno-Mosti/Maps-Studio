# -*- mode: python ; coding: utf-8 -*-
# Build from the project root:  python -m PyInstaller --clean --noconfirm MapsStudio.spec
# Produces one self-contained file in dist/: MapsStudio.exe (Windows) or MapsStudio (Linux).
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH)
sys.path.insert(0, str(ROOT))
from maps_studio import VERSION  # noqa: E402

dnd_datas, dnd_binaries, dnd_hidden = collect_all("tkinterdnd2")

version_file = None
if sys.platform == "win32":
    major, minor, patch = (int(p) for p in VERSION.split("."))
    version_file = str(ROOT / "build" / "version_info.txt")
    Path(version_file).parent.mkdir(exist_ok=True)
    Path(version_file).write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({major}, {minor}, {patch}, 0), prodvers=({major}, {minor}, {patch}, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('ProductName', 'Maps Studio'),
    StringStruct('FileDescription', 'Maps Studio'),
    StringStruct('FileVersion', '{VERSION}'),
    StringStruct('ProductVersion', '{VERSION}'),
    StringStruct('OriginalFilename', 'MapsStudio.exe')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])])
""", encoding="utf-8")

a = Analysis(
    [str(ROOT / "MapsStudio.py")],
    pathex=[str(ROOT)],
    binaries=dnd_binaries,
    datas=[(str(ROOT / "assets" / "logo.png"), "assets")] + dnd_datas,
    hiddenimports=dnd_hidden,
    excludes=["numpy", "matplotlib", "PIL", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="MapsStudio",
    debug=False, strip=False, upx=False,
    console=False,
    icon=str(ROOT / "assets" / "logo.ico") if sys.platform == "win32" else None,
    version=version_file,
)
