"""Backup de metadate sau complet (cu fisiere), zilnic sau la cerere."""

from __future__ import annotations

import logging
import os
import re
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..domain.common import fmt_utc, utcnow
from ..errors import StorageError
from ..storage.atomic import dump_json
from ..storage.paths import is_reparse_point, walk_no_links
from ..storage.ziputil import safe_extract_zip
from .workspace import Workspace

log = logging.getLogger(__name__)

_NAME_RE = re.compile(r"^focusdesk-(meta|full)-(\d{8})-(\d{6})\.zip$")
_EXCLUDED_SYSTEM = {"backups", "logs"}
_META_EXCLUDED_DIRS = {"files", "snapshots"}


@dataclass
class BackupResult:
    path: Path
    kind: str
    file_count: int
    external_copy: Path | None = None
    external_error: str | None = None


def _iter_files(ws: Workspace, full: bool):
    root = ws.root
    for dirpath, dirnames, filenames in walk_no_links(root):
        rel_dir = Path(dirpath).relative_to(root)
        parts = rel_dir.parts
        if parts[:1] == ("_system",) and len(parts) >= 2 and parts[1] in _EXCLUDED_SYSTEM:
            dirnames[:] = []
            continue
        if not full:
            dirnames[:] = [d for d in dirnames if d not in _META_EXCLUDED_DIRS]
        if parts[:2] == ("_system", "trash") and not full:
            dirnames[:] = []
            continue
        for fn in filenames:
            if fn.endswith(".tmp") or fn == "workspace.lock":
                continue
            yield Path(dirpath) / fn


def create_backup(ws: Workspace, *, full: bool = False, external_dir: Path | None = None) -> BackupResult:
    """Zip atomic; un backup pe acelasi disc nu protejeaza de defectarea discului."""
    ws.repo._require_writable()
    kind = "full" if full else "meta"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest_dir = ws.repo.backups_dir
    dest_dir.mkdir(parents=True, exist_ok=True)
    final = dest_dir / f"focusdesk-{kind}-{stamp}.zip"
    tmp = final.with_suffix(".zip.part")
    count = 0
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in _iter_files(ws, full):
                try:
                    zf.write(path, path.relative_to(ws.root).as_posix())
                    count += 1
                except FileNotFoundError:
                    continue  # fisier sters in timpul backup-ului
            zf.writestr("_backup_manifest.json", dump_json({
                "kind": kind, "created_at": fmt_utc(utcnow()), "workspace_id": ws.id,
                "workspace_name": ws.name, "file_count": count,
                "includes_files": full,
            }))
        os.replace(tmp, final)
    except (OSError, zipfile.BadZipFile) as exc:
        tmp.unlink(missing_ok=True)
        raise StorageError(f"Backup-ul a eșuat: {exc}") from exc
    result = BackupResult(final, kind, count)
    ext = external_dir or (Path(ws.settings.backup.external_dir) if ws.settings.backup.external_dir else None)
    if ext is not None:
        try:
            ext.mkdir(parents=True, exist_ok=True)
            copy = ext / final.name
            shutil.copyfile(final, copy.with_suffix(".zip.part"))
            os.replace(copy.with_suffix(".zip.part"), copy)
            result.external_copy = copy
            apply_retention(ext, ws.settings.backup.retention)
        except OSError as exc:
            result.external_error = str(exc)
    apply_retention(dest_dir, ws.settings.backup.retention)
    return result


def list_backups(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted((p for p in directory.iterdir() if _NAME_RE.match(p.name)), key=lambda p: p.name)


def apply_retention(directory: Path, keep: int) -> list[Path]:
    removed: list[Path] = []
    for kind in ("meta", "full"):
        items = [p for p in list_backups(directory) if _NAME_RE.match(p.name).group(1) == kind]  # type: ignore[union-attr]
        for p in items[: max(0, len(items) - max(1, keep))]:
            try:
                p.unlink()
                removed.append(p)
            except OSError:
                pass
    return removed


def ensure_daily_backup(ws: Workspace) -> BackupResult | None:
    """Creeaza un backup daca nu exista unul azi; apelat la prima pornire/scriere a zilei."""
    if ws.read_only or not ws.settings.backup.daily:
        return None
    today = datetime.now().strftime("%Y%m%d")
    for p in list_backups(ws.repo.backups_dir):
        if _NAME_RE.match(p.name).group(2) == today:  # type: ignore[union-attr]
            return None
    return create_backup(ws, full=ws.settings.backup.include_files)


def restore_backup_to_folder(zip_path: Path, dest: Path) -> Path:
    """Extrage intr-un folder NOU; nu suprascrie niciodata workspace-ul curent."""
    dest = Path(dest)
    if dest.exists() and any(dest.iterdir()):
        raise StorageError("Folderul de destinație nu este gol.")
    safe_extract_zip(zip_path, dest)
    return dest
