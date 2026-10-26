"""PyInstaller inputs. Bundle CPU DLLs and their MSVC dependencies, never a GGUF."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def windows_runtime_binaries() -> list[tuple[str, str]]:
    if sys.platform != "win32":
        return []
    roots = [Path(sys.base_prefix), Path(sys.prefix), Path(os.environ.get("WINDIR", "C:/Windows")) / "System32"]
    # An explicit directory from the MSVC redistributable installation on the BUILD host.
    if os.environ.get("FOCUSDESK_VC_REDIST"):
        roots.insert(0, Path(os.environ["FOCUSDESK_VC_REDIST"]))
    roots.extend(Path(p) for p in os.environ.get("PATH", "").split(os.pathsep) if p)
    redist_roots = []
    if os.environ.get("VCToolsRedistDir"):
        redist_roots.append(Path(os.environ["VCToolsRedistDir"]))
    for name in ("ProgramFiles", "ProgramFiles(x86)"):
        if os.environ.get(name):
            redist_roots.extend((Path(os.environ[name]) / "Microsoft Visual Studio").glob("*/*/VC/Redist/MSVC"))
    result = []
    for name in ("msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll", "vcomp140.dll"):
        matches = [root / name for root in roots if (root / name).is_file()]
        if not matches:
            matches = [p for root in redist_roots for p in root.rglob(name)
                       if "x64" in p.parts and "debug" not in str(p).lower()]
        if not matches:
            raise RuntimeError(f"Lipsește runtime-ul redistribuibil {name} pe mașina de build. "
                               "Setează FOCUSDESK_VC_REDIST la folderul DLL-urilor x64 Microsoft autorizate.")
        result.append((str(matches[0]), "llama_cpp/lib"))
    return result
