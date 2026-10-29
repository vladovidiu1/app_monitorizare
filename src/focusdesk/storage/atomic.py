"""Scriere atomica si citire sigura a fisierelor JSON/text."""

from __future__ import annotations

from ..i18n import tr

import hashlib
import json
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from ..errors import CorruptFileError, StorageError


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _replace_with_retry(src: Path, dst: Path) -> None:
    # OneDrive/antivirus pot bloca scurt fisierul tinta pe Windows.
    last: Exception | None = None
    for attempt in range(6):
        try:
            os.replace(src, dst)
            return
        except PermissionError as exc:
            last = exc
            time.sleep(0.05 * (attempt + 1))
    assert last is not None
    raise last


def atomic_write_bytes(path: Path, data: bytes, *, keep_backup: bool = False) -> str:
    """Scrie `data` prin fisier temporar in acelasi director; intoarce hash-ul scris."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.{uuid.uuid4().hex[:8]}.tmp"
    try:
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if keep_backup and path.exists():
            _backup_if_valid_json(path)
        _replace_with_retry(tmp, path)
    except OSError as exc:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise StorageError(tr('storage.atomic.scrierea_fisierului_a_esuat', path_name=path.name, exc=exc)) from exc
    return sha256_bytes(data)


def _backup_if_valid_json(path: Path) -> None:
    try:
        current = path.read_bytes()
        json.loads(current.decode("utf-8"))
    except (OSError, ValueError):
        return
    try:
        shutil.copyfile(path, path.with_name(path.name + ".bak"))
    except OSError:
        pass


def dump_json(data: Any) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def atomic_write_json(path: Path, data: Any, *, keep_backup: bool = True) -> str:
    return atomic_write_bytes(path, dump_json(data), keep_backup=keep_backup)


def atomic_write_text(path: Path, text: str) -> str:
    return atomic_write_bytes(path, text.encode("utf-8"))


def read_json(path: Path, *, allow_backup: bool = True) -> tuple[Any, str, bool]:
    """Citeste JSON. Intoarce (date, hash_fisier_principal, din_backup)."""
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise CorruptFileError(tr('extra.storage.atomic.nu_se_poate_citi', path=path, exc=exc)) from exc
    digest = sha256_bytes(raw)
    try:
        return json.loads(raw.decode("utf-8-sig")), digest, False
    except (ValueError, UnicodeDecodeError) as primary:
        bak = path.with_name(path.name + ".bak")
        if allow_backup and bak.exists():
            try:
                return json.loads(bak.read_text(encoding="utf-8")), digest, True
            except (ValueError, OSError):
                pass
        raise CorruptFileError(tr('storage.atomic.json_invalid_in', path=path, primary=primary)) from primary
