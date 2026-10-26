# Build from the repository root; user data always stays outside the bundle.
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

root = Path(SPECPATH)
a = Analysis(
    [str(root / "packaging" / "entry.py")], pathex=[str(root / "src")],
    binaries=[], datas=collect_data_files("focusdesk"),
    hiddenimports=["win32com.client", "pythoncom", "pywintypes"],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=["llama_cpp", "numpy", "jinja2", "diskcache"], noarchive=False,
)
pyz = PYZ(a.pure)
onefile = os.environ.get("FOCUSDESK_ONEFILE") == "1"
options = dict(name="FocusDesk", debug=False, strip=False, upx=False, console=False,
               icon=str(root / "src/focusdesk/resources/focusdesk.ico"))
if onefile:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, **options)
else:
    exe = EXE(pyz, a.scripts, exclude_binaries=True, **options)
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="FocusDesk")
