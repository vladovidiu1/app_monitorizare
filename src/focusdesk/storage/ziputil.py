"""Operatii ZIP sigure: extragere cu protectie la path traversal."""

from __future__ import annotations

import os
import stat
import zipfile
from pathlib import Path, PurePosixPath

from ..errors import UnsafePathError
from .paths import clean_abs, is_within

DEFAULT_MAX_TOTAL = 8 * 1024 ** 3


def validate_member_name(name: str) -> PurePosixPath:
    if "\x00" in name or name.startswith(("/", "\\")):
        raise UnsafePathError(f"Nume de arhivă invalid: {name!r}")
    normalized = name.replace("\\", "/")
    p = PurePosixPath(normalized)
    if p.is_absolute() or (len(normalized) > 1 and normalized[1] == ":"):
        raise UnsafePathError(f"Cale absolută în arhivă: {name!r}")
    if any(part == ".." for part in p.parts):
        raise UnsafePathError(f"Cale cu '..' în arhivă: {name!r}")
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
                raise UnsafePathError(f"Intrarea iese din folderul destinație: {info.filename!r}")
            mode = info.external_attr >> 16
            if mode and stat.S_ISLNK(mode):
                raise UnsafePathError(f"Arhiva conține un symlink: {info.filename!r}")
            total += info.file_size
            if total > max_total:
                raise UnsafePathError("Arhiva depășește limita de dimensiune la extragere.")
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
