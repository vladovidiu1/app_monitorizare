"""Atasamente (administrate/externe) si folderul de cod al unui nod."""

from __future__ import annotations

import logging
import ntpath
import os
import shutil
import stat
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
    code_owner_id: str | None = None
    source_mode: str | None = None
    source_path: str | None = None


@dataclass(frozen=True)
class LocalFile:
    """Read-only snapshot for file pickers; never registers or copies an attachment."""

    path: str
    size_bytes: int | None = None
    state: str = "ready"  # ready | missing | inaccessible | directory
    detail: str = ""

    @property
    def name(self) -> str:
        return ntpath.basename(self.path)


def normalized_file_key(path: str | os.PathLike) -> str:
    """Windows path equality, also reproducible in tests on non-Windows hosts."""
    value = os.fspath(path)
    if os.name == "nt" or not ntpath.isabs(value):
        value = os.path.abspath(value)
    return ntpath.normcase(ntpath.normpath(value))


def format_size(value: int) -> str:
    amount = float(value)
    for unit in ("B", "KB", "MB", "GB"):
        if amount < 1024 or unit == "GB":
            return f"{amount:.1f} {unit}" if unit != "B" else f"{value} B"
        amount /= 1024
    raise AssertionError("unreachable")


def inspect_local_file(path: str | os.PathLike) -> LocalFile:
    """Check actual read access, not merely an access() flag. Never read the full content."""
    value = os.path.abspath(path)
    try:
        info = Path(value).stat()
        if stat.S_ISDIR(info.st_mode):
            return LocalFile(value, state="directory", detail="Selectează documentele din interiorul folderului.")
        if not stat.S_ISREG(info.st_mode):
            return LocalFile(value, state="inaccessible", detail="Calea nu este un fișier obișnuit.")
        with Path(value).open("rb") as stream:
            stream.read(1)
        return LocalFile(value, info.st_size)
    except FileNotFoundError:
        return LocalFile(value, state="missing", detail="Fișierul nu mai există.")
    except OSError as exc:
        return LocalFile(value, state="inaccessible", detail=str(exc))


@dataclass(frozen=True)
class FileLocation:
    label: str
    path: Path


@dataclass(frozen=True)
class DirectoryEntry:
    path: Path
    is_dir: bool
    size_bytes: int | None
    modified_ns: int | None = None
    is_link: bool = False
    state: str = "ready"
    detail: str = ""


@dataclass(frozen=True)
class ExplorerSource:
    key: str
    label: str
    path: Path | None
    note: str = ""
    is_dir: bool = True
    reference_ids: tuple[str, ...] = ()
    error: str = ""


class FileService:
    def __init__(self, ws: Workspace) -> None:
        self.ws = ws

    # ---- attachments ------------------------------------------------
    def files_dir(self, node_id: str) -> Path:
        return self.ws.node_dir(node_id) / "files"

    def browse_locations(self, node_id: str) -> list[FileLocation]:
        """Task/ancestor files, external references and code, without scanning descendants.

        The browser lists one directory on demand, including files manually added on disk.
        This read-only API can also serve the Files tab's future explorer.
        """
        locations: list[FileLocation] = []
        seen: set[str] = set()

        def add(label: str, path: Path) -> None:
            key = normalized_file_key(path)
            if key not in seen:
                seen.add(key)
                locations.append(FileLocation(label, path))

        for node in (self.ws.get(node_id), *reversed(self.ws.ancestors(node_id))):
            add(f"{node.title} — fișiere", self.files_dir(node.id))
            for att in node.attachments:
                try:
                    path = self.resolve(node.id, att)
                except UnsafePathError:
                    continue
                add(f"{node.title} — {att.name}", path if att.is_dir else path.parent)
        try:
            source = self.effective_source(node_id)
        except (NotFoundError, ValidationError):
            source = None
        if source:
            add("Folder de cod", source.path)
        return locations

    def explorer_sources(self, node_id: str) -> list[ExplorerSource]:
        """Metadata only: use the existing source association, files/ and legacy references."""
        node = self.ws.get(node_id)
        sources = []
        try:
            source = self.effective_source(node_id)
            if source:
                owner = self.ws.get(source.owner_id)
                note = f"Moștenit de la {owner.title}. " if source.inherited else ""
                if source.mode == "shared":
                    note += "Folder de cod comun. "
                note += "Administrat în workspace." if (source.source_mode or source.mode) == "managed" else "Extern; nu intră automat în backup."
                sources.append(ExplorerSource("work", "Folderul proiectului / de lucru", source.path, note))
        except (NotFoundError, UnsafePathError, ValidationError) as exc:
            sources.append(ExplorerSource("work", "Folderul proiectului / de lucru", None, error=str(exc)))
        own = self.files_dir(node_id)
        same = next((s for s in sources if s.path and normalized_file_key(s.path) == normalized_file_key(own)), None)
        if same:
            sources[sources.index(same)] = ExplorerSource(same.key, same.label + " · Fișierele taskului", own, same.note)
        else:
            sources.append(ExplorerSource("files", "Fișierele taskului" if node.kind == Kind.TASK else "Fișierele proiectului", own,
                                          "Conținutul real din files/; inclus în backupul complet."))
        roots = [s for s in sources if s.path]
        if len(roots) == 2 and (is_within(roots[0].path, roots[1].path) or is_within(roots[1].path, roots[0].path)):
            sources = [ExplorerSource(s.key, s.label, s.path, s.note + " Suprapunere între rădăcini: conținut comun, fără copii suplimentare.") for s in sources]
        seen = set()
        for att in sorted(node.attachments, key=lambda a: (not a.is_dir, len(a.path))):
            try:
                path = self.resolve(node_id, att)
            except UnsafePathError as exc:
                sources.append(ExplorerSource("link-" + att.id, att.name, None, is_dir=att.is_dir,
                                              reference_ids=(att.id,), error=str(exc)))
                continue
            key = normalized_file_key(path)
            if any(s.path and s.is_dir and is_within(s.path, path) for s in sources):
                continue  # Still available as a reference action on the corresponding disk row.
            if key in seen:
                continue
            seen.add(key)
            ids = tuple(a.id for a in node.attachments if a.mode == att.mode and a.path == att.path)
            sources.append(ExplorerSource("link-" + att.id, att.name, path,
                                          "Legătură externă." if att.mode == "external" else "Referință administrată existentă.",
                                          att.is_dir, ids))
        return sources

    @staticmethod
    def explorer_path(root: Path, candidate: Path) -> Path:
        """Revalidate boundaries and every path component, including the selected root.

        Call from I/O workers: lstat can block on a disconnected network share.
        """
        root, candidate = Path(clean_abs(root)), Path(clean_abs(candidate))
        if not is_within(root, candidate):
            raise UnsafePathError("Calea iese din rădăcina aleasă.")
        ensure_path_fits(candidate, reserve=0)
        for parent in (root, *root.parents):
            if is_reparse_point(parent):
                raise UnsafePathError(f"Legătură/junction fără traversare automată: {parent}")
        rel = candidate.relative_to(root)
        return resolve_inside(root, rel.as_posix()) if rel.parts else root

    @staticmethod
    def describe_entry(root: Path, path: Path, *, readable: bool = False) -> DirectoryEntry:
        checked = FileService.explorer_path(root, path)
        try:
            info = checked.lstat()
            directory = stat.S_ISDIR(info.st_mode)
            if not directory and not stat.S_ISREG(info.st_mode):
                raise UnsafePathError("Calea nu este un fișier sau folder obișnuit.")
            if readable:
                if directory:
                    with os.scandir(checked):
                        pass
                else:
                    with checked.open("rb") as stream:
                        stream.read(1)
            return DirectoryEntry(checked, directory, None if directory else info.st_size, info.st_mtime_ns)
        except OSError as exc:
            raise StorageError(f"Calea nu este disponibilă: {checked}\n{exc}") from exc

    @staticmethod
    def browse_directory(directory: Path, *, root: Path | None = None, include_links: bool = False,
                         cancel=None) -> list[DirectoryEntry]:
        """One level, metadata only. An inaccessible child does not invalidate its siblings."""
        directory = FileService.explorer_path(root or directory, directory)
        try:
            entries = []
            with os.scandir(directory) as children:
                for child in children:
                    if cancel:
                        cancel.check()
                    try:
                        info = child.stat(follow_symlinks=False)
                        link = stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)
                        if link and not include_links:
                            continue
                        directory_child = stat.S_ISDIR(info.st_mode)
                        state = "link" if link else "ready" if directory_child or stat.S_ISREG(info.st_mode) else "unsupported"
                        entries.append(DirectoryEntry(Path(child.path), directory_child,
                                                      info.st_size if stat.S_ISREG(info.st_mode) and not link else None,
                                                      info.st_mtime_ns, link, state,
                                                      "Legătură/junction: fără traversare automată." if link else
                                                      "Element special; nu se deschide automat." if state == "unsupported" else ""))
                    except FileNotFoundError:
                        continue  # Removed during listing; the next refresh reconciles it.
                    except OSError as exc:
                        entries.append(DirectoryEntry(Path(child.path), False, None, state="inaccessible", detail=str(exc)))
            return sorted(entries, key=lambda item: (not item.is_dir, item.path.name.casefold()))
        except OSError as exc:
            raise StorageError(f"Folderul nu poate fi citit: {directory}\n{exc}") from exc

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

    def disable_code_folder(self, node_id: str) -> None:
        """Stop inheritance on this node, preserving the parent association and all files."""
        self.ws.update_node(node_id, source_workspace=SourceWorkspace(mode="disabled", path=""))

    def effective_source(self, node_id: str) -> ResolvedSource | None:
        """Folderul de cod propriu sau mostenit de la cel mai apropiat stramos."""
        chain = [self.ws.get(node_id), *reversed(self.ws.ancestors(node_id))]
        for i, n in enumerate(chain):
            sw = n.source_workspace
            if sw is None:
                continue
            if sw.mode == 'disabled': return None
            if sw.mode == 'shared':
                if sw.shared_mode == 'managed':
                    if sw.owner_node_id not in self.ws.nodes:
                        raise NotFoundError('Folder de cod comun indisponibil: nodul care păstrează codul este în coș sau lipsește. Restaurează-l sau alege alt folder.')
                    path = resolve_inside(self.ws.node_dir(sw.owner_node_id),sw.path)
                else: path = Path(sw.path)
                # Checkpoints belong to the referencing requirement, not the code owner.
                return ResolvedSource(path,n.id,'shared',i>0,sw.owner_node_id,sw.shared_mode,sw.path)
            if sw.mode == "managed":
                path = resolve_inside(self.ws.node_dir(n.id), sw.path)
            else:
                path = Path(sw.path)
            return ResolvedSource(path,n.id,sw.mode,i>0,n.id,sw.mode,sw.path)
        return None

    def checkpoint_owner(self,node_id):
        # Saved versions remain accessible even when the shared live folder disappears.
        for node in (self.ws.get(node_id),*reversed(self.ws.ancestors(node_id))):
            if node.source_workspace is not None:
                return node.id if node.source_workspace.mode!='disabled' else node_id
        return node_id

    def usable_source_dir(self, node_id: str) -> Path | None:
        from ..errors import FocusDeskError
        try: src = self.effective_source(node_id)
        except FocusDeskError: return None
        return src.path if src and src.path.is_dir() else None

    def shared_access(self,node_id):
        """Snapshot a code location without copying it or inheriting its checkpoint owner."""
        src=self.effective_source(node_id)
        if src is None: raise ValidationError('Sursa nu are folder de cod. Alege un folder sau continuă fără acces la cod.')
        return SourceWorkspace(mode='shared',path=src.source_path,owner_node_id=src.code_owner_id,shared_mode=src.source_mode)

    def shared_users(self,node_id):
        src=self.effective_source(node_id)
        if src is None:return []
        key=os.path.normcase(str(src.path))
        result=[]
        for node in self.ws.nodes.values():
            try: other=self.effective_source(node.id)
            except (NotFoundError,ValidationError):continue
            if other and os.path.normcase(str(other.path))==key:result.append(node.id)
        return result
