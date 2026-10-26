"""Nume fizice sigure pentru Windows si verificari de cai."""

from __future__ import annotations

import os
import re
import stat
import unicodedata
from pathlib import Path
from typing import Iterator

from ..domain.common import short_id
from ..errors import PathTooLongError, UnsafePathError

WINDOWS_RESERVED = frozenset(
    {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
)
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_NODE_DIR_RE = re.compile(r"^.+--[0-9a-f]{8}$")
MAX_PATH = 259
DEFAULT_RESERVE = 50  # loc pentru node.json, fisiere atasate scurte si un nivel de copii


def slugify(title: str, max_len: int = 20) -> str:
    text = unicodedata.normalize("NFKD", title)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    text = text[:max_len].strip("-")
    if not text:
        text = "nod"
    if text.split(".")[0] in WINDOWS_RESERVED:
        text = "_" + text
    return text


def physical_dirname(title: str, node_id: str) -> str:
    return f"{slugify(title)}--{short_id(node_id)}"


def is_node_dirname(name: str) -> bool:
    return bool(_NODE_DIR_RE.match(name))


def sanitize_filename(name: str) -> str:
    """Nume de fisier valid pe Windows, pastrand diacriticele."""
    name = _ILLEGAL.sub("_", name).strip().rstrip(". ")
    if not name:
        name = "fisier"
    stem = name.split(".")[0].lower()
    if stem in WINDOWS_RESERVED:
        name = "_" + name
    return name[:150]


def clean_abs(path: str | os.PathLike) -> str:
    p = os.path.abspath(os.fspath(path))
    if p.startswith("\\\\?\\"):
        p = p[4:]
    return p


def ensure_path_fits(path: str | os.PathLike, reserve: int = DEFAULT_RESERVE) -> None:
    length = len(clean_abs(path))
    if length + reserve > MAX_PATH:
        raise PathTooLongError(
            f"Calea ar depăși limita Windows ({length + reserve} > {MAX_PATH} caractere): {clean_abs(path)}"
        )


def is_reparse_point(path: str | os.PathLike) -> bool:
    try:
        st = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(st.st_mode):
        return True
    attrs = getattr(st, "st_file_attributes", 0)
    return bool(attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def is_within(base: str | os.PathLike, candidate: str | os.PathLike) -> bool:
    b = os.path.normcase(clean_abs(base))
    c = os.path.normcase(clean_abs(candidate))
    try:
        return os.path.commonpath([b, c]) == b
    except ValueError:
        return False


def resolve_inside(base: str | os.PathLike, rel: str) -> Path:
    """Rezolva o cale relativa strict in interiorul `base`, fara `..` sau linkuri."""
    if not rel or os.path.isabs(rel) or re.match(r"^[A-Za-z]:", rel):
        raise UnsafePathError(f"Cale relativă invalidă: {rel!r}")
    parts = [p for p in re.split(r"[\\/]+", rel) if p]
    if any(p == ".." for p in parts):
        raise UnsafePathError(f"Calea iese din folderul permis: {rel!r}")
    current = Path(clean_abs(base))
    for part in parts:
        if part == ".":
            continue
        current = current / part
        if is_reparse_point(current):
            raise UnsafePathError(f"Calea conține un link/junction: {current}")
    if not is_within(base, current):
        raise UnsafePathError(f"Calea iese din folderul permis: {rel!r}")
    return current


def walk_no_links(root: str | os.PathLike) -> Iterator[tuple[str, list[str], list[str]]]:
    """os.walk care nu urmeaza si nu listeaza symlink-uri/junctions."""
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if not is_reparse_point(os.path.join(dirpath, d))]
        filenames = [f for f in filenames if not is_reparse_point(os.path.join(dirpath, f))]
        yield dirpath, dirnames, filenames
