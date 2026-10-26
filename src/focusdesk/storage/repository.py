"""Repository pe filesystem pentru un workspace FocusDesk."""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from ..domain.common import new_id, utcnow, fmt_utc
from ..domain.models import (
    SCHEMA_VERSION, HistoryEvent, Kind, NoteEntry, Node, WorkspaceMeta,
)
from ..domain.session import OperationRecord, RecurrenceTemplate, SessionRecord
from ..domain.settings import Settings
from ..errors import (
    CorruptFileError, ExternalModificationError, NotFoundError, ReadOnlyError,
    StorageError, ValidationError, WorkspaceLockedError,
)
from .atomic import atomic_write_json, atomic_write_text, read_json, sha256_file
from .lock import WorkspaceLock
from .paths import ensure_path_fits, is_node_dirname, is_reparse_point, physical_dirname
from .records import RecordStore

log = logging.getLogger(__name__)

# Nodurile noi nu au `children/`: ierarhia este in `parent_id`, nu in adancimea directoarelor (altfel calea creste
# cu fiecare nivel si lovește limita Windows). `children/` ramane recunoscut doar pentru workspace-uri vechi.
NODE_SUBDIRS = ("notes", "files", "snapshots")


@dataclass
class LoadIssue:
    severity: str  # "error" | "warning"
    code: str
    message: str
    path: str | None = None
    node_id: str | None = None


def migrate_node_data(data: dict) -> dict:
    version = data.get("schema_version", 1)
    if not isinstance(version, int) or version > SCHEMA_VERSION:
        raise CorruptFileError(f"schema_version {version!r} este mai nouă decât cea suportată ({SCHEMA_VERSION})")
    return data


class WorkspaceRepository:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.lock = WorkspaceLock(self.root / "_system" / "workspace.lock")
        self.read_only = False
        self.meta: WorkspaceMeta | None = None
        self.nodes: dict[str, Node] = {}
        self.dirs: dict[str, Path] = {}
        self.issues: list[LoadIssue] = []
        self._hashes: dict[tuple[str, str], str] = {}
        self._mutex = threading.RLock()
        self.sessions = RecordStore(self.system_dir / "sessions", SessionRecord)
        self.history = RecordStore(self.system_dir / "history", HistoryEvent)
        self.operations = RecordStore(self.system_dir / "operations", OperationRecord)
        self.recurrences = RecordStore(self.system_dir / "recurrences", RecurrenceTemplate, keep_backup=True)

    # ---- layout -----------------------------------------------------
    @property
    def nodes_dir(self) -> Path:
        return self.root / "nodes"

    @property
    def system_dir(self) -> Path:
        return self.root / "_system"

    @property
    def trash_dir(self) -> Path:
        return self.system_dir / "trash"

    @property
    def backups_dir(self) -> Path:
        return self.system_dir / "backups"

    @property
    def logs_dir(self) -> Path:
        return self.system_dir / "logs"

    @property
    def settings_path(self) -> Path:
        return self.system_dir / "settings.json"

    @property
    def index_path(self) -> Path:
        return self.system_dir / "index.json"

    @staticmethod
    def is_workspace(root: Path) -> bool:
        return (Path(root) / "workspace.json").is_file()

    # ---- opening ----------------------------------------------------
    @classmethod
    def open(cls, root: Path, *, create: bool = False, name: str = "FocusDesk",
             read_only: bool = False) -> "WorkspaceRepository":
        repo = cls(root)
        if not cls.is_workspace(root):
            if not create:
                raise NotFoundError(f"{root} nu este un workspace FocusDesk.")
            repo._create_layout(name)
        if read_only:
            repo.read_only = True
        else:
            try:
                repo.lock.acquire()
            except WorkspaceLockedError:
                repo.read_only = True
                repo.lock_conflict = True  # type: ignore[attr-defined]
        repo._load_meta()
        return repo

    lock_conflict = False

    def _create_layout(self, name: str) -> None:
        for d in (self.nodes_dir, self.system_dir, self.sessions.directory, self.history.directory,
                  self.operations.directory, self.trash_dir, self.backups_dir, self.logs_dir):
            d.mkdir(parents=True, exist_ok=True)
        meta = WorkspaceMeta(name=name)
        atomic_write_json(self.root / "workspace.json", meta.model_dump(mode="json"))
        atomic_write_json(self.settings_path, Settings().model_dump(mode="json"))

    def _load_meta(self) -> None:
        data, _, _ = read_json(self.root / "workspace.json")
        self.meta = WorkspaceMeta.model_validate(data)
        for d in (self.nodes_dir, self.sessions.directory, self.history.directory,
                  self.operations.directory, self.trash_dir, self.backups_dir, self.logs_dir):
            if not self.read_only:
                d.mkdir(parents=True, exist_ok=True)

    def close(self) -> None:
        self.lock.release()

    def _require_writable(self) -> None:
        if self.read_only:
            raise ReadOnlyError("Workspace-ul este deschis doar pentru citire.")

    def rename_workspace(self, name: str) -> None:
        self._require_writable()
        assert self.meta is not None
        meta = self.meta.model_copy(update={"name": name.strip() or self.meta.name})
        atomic_write_json(self.root / "workspace.json", meta.model_dump(mode="json"))
        self.meta = meta

    # ---- settings ---------------------------------------------------
    def load_settings(self) -> Settings:
        try:
            data, _, _ = read_json(self.settings_path)
            return Settings.model_validate(data)
        except (CorruptFileError, PydanticValidationError, NotFoundError) as exc:
            log.warning("settings.json invalid, folosesc valori implicite: %s", exc)
            self.issues.append(LoadIssue("warning", "settings_invalid", f"settings.json invalid: {exc}"))
            return Settings()

    def save_settings(self, settings: Settings) -> None:
        self._require_writable()
        atomic_write_json(self.settings_path, settings.model_dump(mode="json"))

    # ---- loading ----------------------------------------------------
    def load(self) -> None:
        with self._mutex:
            self.nodes.clear()
            self.dirs.clear()
            self._hashes.clear()
            self.issues = []
            if self.nodes_dir.exists():
                self._scan(self.nodes_dir, None, parent_known=False)
            self._validate_graph()

    def _issue(self, severity: str, code: str, message: str, path: Path | None = None,
               node_id: str | None = None) -> None:
        self.issues.append(LoadIssue(severity, code, message, str(path) if path else None, node_id))

    def _scan(self, container: Path, physical_parent: str | None, parent_known: bool = True) -> None:
        if not container.exists():
            return
        try:
            entries = sorted(container.iterdir(), key=lambda p: p.name)
        except OSError as exc:
            self._issue("error", "scan_failed", f"Nu se poate citi {container}: {exc}", container)
            return
        for entry in entries:
            self._load_entry(entry, physical_parent, parent_known)

    def _load_entry(self, entry: Path, physical_parent: str | None, parent_known: bool = True) -> None:
        if not entry.is_dir() or is_reparse_point(entry) or entry.name.startswith("."):
            return
        njson = entry / "node.json"
        if not njson.is_file():
            self._issue("warning", "dir_without_node_json",
                        f"Directorul {entry.name} nu conține node.json și a fost ignorat.", entry)
            return
        try:
            data, digest, from_bak = read_json(njson)
            node = Node.model_validate(migrate_node_data(data))
        except (CorruptFileError, PydanticValidationError) as exc:
            self._issue("error", "node_corrupt", f"{njson}: {exc}", njson)
            # Copiii raman incarcabili; parintele fizic este necunoscut.
            self._scan(entry / "children", None, parent_known=False)
            return
        if from_bak:
            self._issue("warning", "node_from_backup",
                        f"node.json corupt, s-a folosit copia .bak: {entry.name}", njson, node.id)
        if node.id in self.nodes:
            self._issue("error", "duplicate_id",
                        f"UUID duplicat {node.id} în {entry} (deja în {self.dirs[node.id]}).", entry, node.id)
            return
        if not is_node_dirname(entry.name):
            self._issue("warning", "unusual_dirname", f"Nume director neobișnuit: {entry.name}", entry, node.id)
        self.nodes[node.id] = node
        self.dirs[node.id] = entry
        self._hashes[(node.id, "node.json")] = digest
        if parent_known and node.parent_id != physical_parent:
            self._issue("warning", "parent_mismatch",
                        f"'{node.title}': parent_id nu corespunde locației fizice.", entry, node.id)
        self._scan(entry / "children", node.id)

    def load_node_dir(self, entry: Path, physical_parent: str | None = None) -> None:
        """Incarca un singur director de nod (si eventualii copii din layout vechi), de ex. dupa restaurare din cos."""
        with self._mutex:
            self._load_entry(entry, physical_parent, parent_known=False)

    def _validate_graph(self) -> None:
        for node in self.nodes.values():
            if node.parent_id is not None and node.parent_id not in self.nodes:
                self._issue("warning", "missing_parent",
                            f"'{node.title}' referă un părinte inexistent; apare ca orfan.", self.dirs[node.id], node.id)
            for ref in node.related_node_ids:
                if ref not in self.nodes:
                    self._issue("warning", "dangling_related", f"'{node.title}': legătură către nod inexistent {ref}.",
                                None, node.id)
            for ref in node.depends_on_ids:
                if ref not in self.nodes:
                    self._issue("warning", "dangling_dependency",
                                f"'{node.title}': dependență către nod inexistent {ref}.", None, node.id)
        for node in self.nodes.values():
            seen = {node.id}
            cur = node.parent_id
            while cur is not None and cur in self.nodes:
                if cur in seen:
                    self._issue("error", "parent_cycle", f"Ciclu în ierarhie la '{node.title}'.", None, node.id)
                    break
                seen.add(cur)
                cur = self.nodes[cur].parent_id

    # ---- node persistence -------------------------------------------
    def create_node(self, node: Node, description: str = "") -> Path:
        with self._mutex:
            self._require_writable()
            if node.id in self.nodes:
                raise ValidationError(f"UUID deja folosit: {node.id}")
            if node.parent_id is not None and node.parent_id not in self.nodes:
                raise NotFoundError(f"Părintele {node.parent_id} nu există.")
            target = self.nodes_dir / physical_dirname(node.title, node.id)
            ensure_path_fits(target)
            if target.exists():
                raise StorageError(f"Directorul există deja: {target.name}")
            try:
                target.mkdir(parents=True)
                for sub in NODE_SUBDIRS:
                    (target / sub).mkdir()
                data = node.model_dump(mode="json")
                digest = atomic_write_json(target / "node.json", data)
                atomic_write_text(target / "description.md", description)
            except StorageError:
                raise
            except OSError as exc:
                raise StorageError(f"Crearea nodului a eșuat: {exc}") from exc
            self.nodes[node.id] = node
            self.dirs[node.id] = target
            self._hashes[(node.id, "node.json")] = digest
            return target

    def _check_unmodified(self, node_id: str, name: str, path: Path) -> None:
        recorded = self._hashes.get((node_id, name))
        if recorded is None:
            return
        if not path.exists():
            raise ExternalModificationError(f"{name} a fost șters din afara aplicației ({path.parent.name}).")
        if sha256_file(path) != recorded:
            raise ExternalModificationError(
                f"{name} din '{path.parent.name}' a fost modificat din afara aplicației. Reîncarcă workspace-ul."
            )

    def write_node(self, new: Node) -> Node:
        """Scrie varianta `new` (cu revizie incrementata). Nu schimba starea in memorie daca scrierea esueaza."""
        with self._mutex:
            self._require_writable()
            old = self.nodes.get(new.id)
            if old is None:
                raise NotFoundError(f"Nodul {new.id} nu există.")
            path = self.dirs[new.id] / "node.json"
            self._check_unmodified(new.id, "node.json", path)
            stored = new.model_copy(update={"revision": old.revision + 1, "updated_at": utcnow()})
            digest = atomic_write_json(path, stored.model_dump(mode="json"))
            self.nodes[new.id] = stored
            self._hashes[(new.id, "node.json")] = digest
            return stored

    def reload_node(self, node_id: str) -> Node:
        with self._mutex:
            path = self.dirs[node_id] / "node.json"
            data, digest, _ = read_json(path)
            node = Node.model_validate(migrate_node_data(data))
            self.nodes[node_id] = node
            self._hashes[(node_id, "node.json")] = digest
            return node

    def note_dir_relocated(self, node_id: str, new_dir: Path) -> None:
        """Actualizeaza caile in memorie pentru nod si descendentii lui dupa o mutare fizica."""
        with self._mutex:
            old_dir = self.dirs[node_id]
            for nid, d in list(self.dirs.items()):
                try:
                    rel = d.relative_to(old_dir)
                except ValueError:
                    continue
                self.dirs[nid] = new_dir / rel

    def forget_subtree(self, node_ids: list[str]) -> None:
        with self._mutex:
            for nid in node_ids:
                self.nodes.pop(nid, None)
                self.dirs.pop(nid, None)
                self._hashes.pop((nid, "node.json"), None)
                self._hashes.pop((nid, "description.md"), None)

    # ---- description ------------------------------------------------
    def read_description(self, node_id: str) -> str:
        path = self.dirs[node_id] / "description.md"
        if not path.exists():
            self._hashes.pop((node_id, "description.md"), None)
            return ""
        raw = path.read_bytes()
        from .atomic import sha256_bytes

        self._hashes[(node_id, "description.md")] = sha256_bytes(raw)
        return raw.decode("utf-8-sig")

    def write_description(self, node_id: str, text: str) -> None:
        with self._mutex:
            self._require_writable()
            path = self.dirs[node_id] / "description.md"
            self._check_unmodified(node_id, "description.md", path)
            self._hashes[(node_id, "description.md")] = atomic_write_text(path, text)

    # ---- notes ------------------------------------------------------
    def notes_store(self, node_id: str) -> RecordStore[NoteEntry]:
        return RecordStore(self.dirs[node_id] / "notes", NoteEntry)

    # ---- index ------------------------------------------------------
    def write_index(self) -> None:
        """Cache reconstructibil; stergerea lui nu pierde date."""
        if self.read_only:
            return
        entries: dict[str, Any] = {}
        for nid, node in self.nodes.items():
            try:
                rel = str(self.dirs[nid].relative_to(self.root))
            except ValueError:
                rel = str(self.dirs[nid])
            entries[nid] = {
                "title": node.title, "kind": node.kind.value, "parent_id": node.parent_id,
                "status": node.status.value if node.status else None,
                "due_date": node.due_date.isoformat() if node.due_date else None,
                "dir": rel,
            }
        try:
            atomic_write_json(self.index_path, {
                "schema_version": SCHEMA_VERSION, "generated_at": fmt_utc(utcnow()), "nodes": entries,
            }, keep_backup=False)
        except StorageError as exc:
            log.warning("Index nescris: %s", exc)
