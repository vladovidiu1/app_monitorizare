# Build from the repository root. The model stays in dist/models, outside onefile temp.
import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, copy_metadata

root = Path(SPECPATH)
sys.path.insert(0, str(root / "packaging"))
from ai_bundle import windows_runtime_binaries

datas = collect_data_files("focusdesk") + collect_data_files("llama_cpp")
for package in ("llama-cpp-python", "numpy", "jinja2", "diskcache"):
    datas += copy_metadata(package)
binaries = collect_dynamic_libs("llama_cpp") + windows_runtime_binaries()
a = Analysis(
    [str(root / "packaging" / "entry.py")], pathex=[str(root / "src")],
    binaries=binaries, datas=datas,
    hiddenimports=["llama_cpp", "llama_cpp.llama_chat_format", "focusdesk.ai.process", "focusdesk.ai.runtime"],
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False,
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
