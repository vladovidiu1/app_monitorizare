"""Operatii ZIP sigure: extragere cu protectie la path traversal."""

from __future__ import annotations

from ..i18n import tr

import os
import stat
import zipfile
from pathlib import Path, PurePosixPath

from ..errors import UnsafePathError
from .paths import clean_abs, is_within

DEFAULT_MAX_TOTAL = 8 * 1024 ** 3


def validate_member_name(name: str) -> PurePosixPath:
    if "\x00" in name or name.startswith(("/", "\\")):
        raise UnsafePathError(tr('storage.ziputil.nume_de_arhiva_invalid', name=name))
    normalized = name.replace("\\", "/")
    p = PurePosixPath(normalized)
    if p.is_absolute() or (len(normalized) > 1 and normalized[1] == ":"):
        raise UnsafePathError(tr('storage.ziputil.cale_absoluta_in_arhiva', name=name))
    if any(part == ".." for part in p.parts):
        raise UnsafePathError(tr('storage.ziputil.cale_cu_in_arhiva', name=name))
    return p


def safe_extract_zip(zip_path: Path, dest: Path, *, max_total: int = DEFAULT_MAX_TOTAL) -> list[Path]:
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    with zipfile.ZipFile(zip_path) as zf:
        infos = zf.infolist()
        # Validam intai toate intrarile; nu extragem nimic daca exista una nesigura.
        total = 0
        for info in infos:
            validate_member_name(info.filename)
            target = Path(clean_abs(dest / validate_member_name(info.filename)))
            if not is_within(dest, target):
                raise UnsafePathError(tr('storage.ziputil.intrarea_iese_din_folderul_destinatie', info_filename=info.filename))
            mode = info.external_attr >> 16
            if mode and stat.S_ISLNK(mode):
                raise UnsafePathError(tr('storage.ziputil.arhiva_contine_un_symlink', info_filename=info.filename))
            total += info.file_size
            if total > max_total:
                raise UnsafePathError(tr('storage.ziputil.arhiva_depaseste_limita_de_dimensiune_la_extragere'))
        for info in infos:
            rel = validate_member_name(info.filename)
            target = Path(clean_abs(dest / rel))
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                while chunk := src.read(1024 * 1024):
                    out.write(chunk)
            written.append(target)
    return written
