"""Atasamente (administrate/externe) si folderul de cod al unui nod."""

from __future__ import annotations

import logging
import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from ..domain.common import utcnow
from ..domain.models import Attachment, Kind, SourceWorkspace
from ..errors import NotFoundError, StorageError, UnsafePathError, ValidationError
from ..storage.paths import (
    clean_abs, ensure_path_fits, is_reparse_point, is_within, resolve_inside, sanitize_filename, walk_no_links,
)
from .workspace import Workspace

log = logging.getLogger(__name__)


class NameConflict(StorageError):
    def __init__(self, name: str) -> None:
        super().__init__(f"Există deja un fișier cu numele „{name}”.")
        self.name = name


@dataclass
class ResolvedSource:
    path: Path
    owner_id: str  # nodul care defineste folderul (poate fi un parinte)
    mode: str
    inherited: bool


class FileService:
    def __init__(self, ws: Workspace) -> None:
        self.ws = ws

    # ---- attachments ------------------------------------------------
    def files_dir(self, node_id: str) -> Path:
        return self.ws.node_dir(node_id) / "files"

    def add_external(self, node_id: str, path: str | os.PathLike, name: str | None = None) -> Attachment:
        p = Path(path)
        if not p.is_absolute():
            raise ValidationError("Calea externă trebuie să fie absolută.")
        if not p.exists():
            raise NotFoundError(f"Calea nu există: {p}")
        node = self.ws.get(node_id)
        att = Attachment(name=name or p.name, mode="external", path=str(p), is_dir=p.is_dir())
        self.ws.update_node(node_id, attachments=[*node.attachments, att])
        return att

    def add_managed(self, node_id: str, src: str | os.PathLike, *, on_conflict: str | None = None) -> Attachment:
        """Copiaza fisierul/folderul in `files/` al nodului. `on_conflict`: 'keep_both' | 'replace' | None (=eroare)."""
        name, is_dir = self.copy_managed(node_id, src, on_conflict=on_conflict)
        return self.register_managed(node_id, name, is_dir)

    def copy_managed(self, node_id: str, src: str | os.PathLike, *, on_conflict: str | None = None) -> tuple[str, bool]:
        """Partea de I/O (fara a modifica workspace-ul in memorie); sigura de rulat intr-un worker."""
        self.ws.repo._require_writable()
        src_p = Path(src)
        if not src_p.exists():
            raise NotFoundError(f"Sursa nu există: {src_p}")
        if is_reparse_point(src_p):
            raise UnsafePathError("Nu se copiază symlink-uri/junctions.")
        files = self.files_dir(node_id)
        files.mkdir(parents=True, exist_ok=True)
        name = sanitize_filename(src_p.name)
        target = files / name
        if target.exists():
            if on_conflict is None:
                raise NameConflict(name)
            if on_conflict == "keep_both":
                target = self._unique_name(files, name)
                name = target.name
            elif on_conflict != "replace":
                raise ValidationError(f"Politică necunoscută: {on_conflict}")
        ensure_path_fits(target, reserve=10)
        tmp = files / f".{uuid.uuid4().hex[:8]}.tmp"
        try:
            if src_p.is_dir():
                self._copy_tree_no_links(src_p, tmp)
                if target.exists():
                    self._remove_path(target)
                os.replace(tmp, target)
            else:
                shutil.copy2(src_p, tmp)
                os.replace(tmp, target)
        except OSError as exc:
            self._remove_path(tmp, ignore=True)
            raise StorageError(f"Copierea a eșuat: {exc}") from exc
        return name, src_p.is_dir()

    def register_managed(self, node_id: str, name: str, is_dir: bool) -> Attachment:
        node = self.ws.get(node_id)
        rel = f"files/{name}"
        existing = next((a for a in node.attachments if a.mode == "managed" and a.path == rel), None)
        if existing is not None:
            return existing  # referința există, conținut înlocuit
        att = Attachment(name=name, mode="managed", path=rel, is_dir=is_dir)
        self.ws.update_node(node_id, attachments=[*node.attachments, att])
        return att

    @staticmethod
    def _unique_name(directory: Path, name: str) -> Path:
        stem, dot, ext = name.rpartition(".")
        if not dot:
            stem, ext = name, ""
        i = 2
        while True:
            cand = directory / (f"{stem} ({i}).{ext}" if ext else f"{stem} ({i})")
            if not cand.exists():
                return cand
            i += 1

    @staticmethod
    def _remove_path(path: Path, ignore: bool = False) -> None:
        try:
            if path.is_dir() and not is_reparse_point(path):
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()
        except OSError:
            if not ignore:
                raise

    @staticmethod
    def _copy_tree_no_links(src: Path, dst: Path) -> None:
        dst.mkdir(parents=True)
        for dirpath, dirnames, filenames in walk_no_links(src):
            rel = Path(dirpath).relative_to(src)
            (dst / rel).mkdir(parents=True, exist_ok=True)
            for fn in filenames:
                ensure_path_fits(dst / rel / fn, reserve=0)
                shutil.copy2(Path(dirpath) / fn, dst / rel / fn)

    def remove_attachment(self, node_id: str, attachment_id: str, *, delete_managed_copy: bool = False) -> None:
        """Elimina referinta. Fisierul extern original nu se sterge niciodata."""
        node = self.ws.get(node_id)
        att = next((a for a in node.attachments if a.id == attachment_id), None)
        if att is None:
            raise NotFoundError("Atașamentul nu există.")
        if att.mode == "managed" and delete_managed_copy:
            p = self.resolve(node_id, att)
            self._remove_path(p, ignore=False)
        self.ws.update_node(node_id, attachments=[a for a in node.attachments if a.id != attachment_id])

    def resolve(self, node_id: str, att: Attachment) -> Path:
        if att.mode == "managed":
            return resolve_inside(self.ws.node_dir(node_id), att.path)
        return Path(att.path)

    def status(self, node_id: str, att: Attachment) -> str:
        """'ok' | 'missing' | 'unsafe'"""
        try:
            p = self.resolve(node_id, att)
        except UnsafePathError:
            return "unsafe"
        return "ok" if p.exists() else "missing"

    def relocate(self, node_id: str, attachment_id: str, new_path: str | os.PathLike) -> None:
        node = self.ws.get(node_id)
        att = next((a for a in node.attachments if a.id == attachment_id), None)
        if att is None or att.mode != "external":
            raise ValidationError("Doar legăturile externe pot fi relocate.")
        p = Path(new_path)
        if not p.exists() or not p.is_absolute():
            raise ValidationError("Noua cale trebuie să existe și să fie absolută.")
        updated = [a.model_copy(update={"path": str(p), "is_dir": p.is_dir()}) if a.id == attachment_id else a
                   for a in node.attachments]
        self.ws.update_node(node_id, attachments=updated)

    # ---- code folder --------------------------------------------------
    def set_code_folder(self, node_id: str, path: str | os.PathLike, mode: str = "external") -> None:
        node = self.ws.get(node_id)
        if node.kind == Kind.FOLDER:
            raise ValidationError("Folderul de cod se asociază proiectelor sau task-urilor.")
        if mode == "external":
            p = Path(path)
            if not p.is_absolute() or not p.is_dir():
                raise ValidationError("Folderul de cod extern trebuie să existe și să fie o cale absolută.")
            sw = SourceWorkspace(path=str(p), mode="external")
        else:
            rel = str(path).replace("\\", "/")
            target = resolve_inside(self.ws.node_dir(node_id), rel)
            target.mkdir(parents=True, exist_ok=True)
            sw = SourceWorkspace(path=rel, mode="managed")
        self.ws.update_node(node_id, source_workspace=sw)

    def clear_code_folder(self, node_id: str) -> None:
        self.ws.update_node(node_id, source_workspace=None)

    def effective_source(self, node_id: str) -> ResolvedSource | None:
        """Folderul de cod propriu sau mostenit de la cel mai apropiat stramos."""
        chain = [self.ws.get(node_id), *reversed(self.ws.ancestors(node_id))]
        for i, n in enumerate(chain):
            sw = n.source_workspace
            if sw is None:
                continue
            if sw.mode == "managed":
                path = resolve_inside(self.ws.node_dir(n.id), sw.path)
            else:
                path = Path(sw.path)
            return ResolvedSource(path, n.id, sw.mode, inherited=i > 0)
        return None

    def usable_source_dir(self, node_id: str) -> Path | None:
        src = self.effective_source(node_id)
        return src.path if src and src.path.is_dir() else None
