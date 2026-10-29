"""Deschidere in Explorer, aplicatia asociata si VS Code, fara shell si fara executia scripturilor."""

from __future__ import annotations

from ..i18n import tr

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

from ..errors import FocusDeskError

log = logging.getLogger(__name__)

# Fisiere care ar rula la "deschidere" cu aplicatia asociata; se deschid in editor sau se afiseaza in Explorer.
RUNNABLE_EXTENSIONS = frozenset({
    ".exe", ".com", ".bat", ".cmd", ".ps1", ".psm1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh", ".hta",
    ".msi", ".msp", ".reg", ".lnk", ".scr", ".jar", ".py", ".pyw", ".pyz", ".cpl", ".url",
})
CREATE_NO_WINDOW = 0x08000000


class OpenError(FocusDeskError):
    pass


def is_runnable(path: Path) -> bool:
    return path.suffix.lower() in RUNNABLE_EXTENSIONS


def reveal_in_explorer(path: Path) -> None:
    """Deschide folderul sau afiseaza fisierul selectat in Explorer."""
    path = Path(path)
    if not path.exists():
        raise OpenError(tr('integrations.system.calea_nu_exista', path=path))
    if sys.platform != "win32":
        raise OpenError(tr('integrations.system.deschiderea_in_explorer_este_disponibila_doar_pe_windows'))
    try:
        if path.is_dir():
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["explorer", f"/select,{path}"], shell=False)
    except OSError as exc:
        raise OpenError(tr('extra.integrations.system.nu_s_a_putut_deschide_explorer', exc=exc)) from exc


def open_with_default_app(path: Path) -> None:
    path = Path(path)
    if not path.exists():
        raise OpenError(tr('integrations.system.fisierul_nu_exista', path=path))
    if path.is_dir():
        reveal_in_explorer(path)
        return
    if is_runnable(path):
        raise OpenError(
            tr('integrations.system.este_un_script_executabil_si_nu_se_deschide_automat_ar_putea_rula_folo', path_name=path.name)
        )
    if sys.platform != "win32":
        raise OpenError(tr('integrations.system.deschiderea_cu_aplicatia_asociata_este_disponibila_doar_pe_windows'))
    try:
        os.startfile(str(path))  # type: ignore[attr-defined]
    except OSError as exc:
        raise OpenError(tr('integrations.system.nu_s_a_putut_deschide_fisierul', exc=exc)) from exc


def find_vscode(configured: str | None = None) -> Path | None:
    """Cauta executabilul VS Code (Code.exe, apoi `code` din PATH)."""
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured))
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(Path(local) / "Programs" / "Microsoft VS Code" / "Code.exe")
    for env in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(env)
        if base:
            candidates.append(Path(base) / "Microsoft VS Code" / "Code.exe")
    for c in candidates:
        if c.is_file():
            return c
    found = shutil.which("code")
    if found:
        p = Path(found)
        exe = p.parent.parent / "Code.exe"
        return exe if exe.is_file() else p
    return None


def open_in_vscode(folder_or_file: Path, configured: str | None = None, *, extra_files: list[Path] | None = None) -> None:
    exe = find_vscode(configured)
    if exe is None:
        raise OpenError(tr('integrations.system.vs_code_nu_a_fost_gasit_alege_executabilul_in_setari_integrari'))
    target = Path(folder_or_file)
    if not target.exists():
        raise OpenError(tr('integrations.system.calea_nu_exista_2', target=target))
    # Caile sunt absolute (incep cu litera de unitate), deci nu pot fi interpretate ca optiuni.
    args = [str(exe), str(target.resolve())]
    for f in extra_files or []:
        if Path(f).exists():
            args.append(str(Path(f).resolve()))
    try:
        subprocess.Popen(args, shell=False, creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    except OSError as exc:
        raise OpenError(tr('extra.integrations.system.vs_code_nu_a_putut_fi_pornit', exc=exc)) from exc
