"""Repository pe filesystem pentru un workspace FocusDesk."""

from __future__ import annotations

from ..i18n import tr

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
from .records import RecordStore, signature, checksum, write_cache
from .node_cache import NavigationNode, navigation_data

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
        raise CorruptFileError(tr('storage.repository.schema_version_este_mai_noua_decat_cea_suportata', version=version, schema_version=SCHEMA_VERSION))
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
        self._stamps = {}
        self._edit_baselines = {}
        self._mutex = threading.RLock()
        self.active_task_ids = set()
        self.task_ids = set()
        self.project_ids = set()
        self.reload_generation = 0
        self.generation = 0
        self.aggregate_generation = 0
        self._cache_entries = {}
        self._notes = {}
        self._index_dirty = False
        self.sessions = RecordStore(self.system_dir / "sessions", SessionRecord, writable=lambda: not self.read_only)
        self.history = RecordStore(self.system_dir / "history", HistoryEvent, writable=lambda: not self.read_only)
        self.operations = RecordStore(self.system_dir / "operations", OperationRecord, writable=lambda: not self.read_only, before_write=self.mark_index_dirty)
        self.recurrences = RecordStore(self.system_dir / "recurrences", RecurrenceTemplate, keep_backup=True, writable=lambda: not self.read_only)

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
                raise NotFoundError(tr('extra.storage.repository.nu_este_un_workspace_focusdesk', root=root))
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
        self.write_index()
        for store in (self.sessions, self.history, self.operations, self.recurrences, *self._notes.values()):
            store.flush()
        self.lock.release()

    @property
    def cache_path(self):
        return self.system_dir / 'cache' / 'nodes.json'

    def mark_index_dirty(self):
        if self.read_only:
            return
        marker = self.system_dir / 'cache' / 'nodes-dirty.json'
        if not marker.exists():
            atomic_write_json(marker, {'dirty': True}, keep_backup=False)
        self._index_dirty = True

    def index_node(self, node):
        from ..domain.models import CLOSED_STATUSES
        for collection in (self.task_ids,self.active_task_ids,self.project_ids): collection.discard(node.id)
        if node.kind == Kind.TASK:
            self.task_ids.add(node.id)
            if node.status not in CLOSED_STATUSES: self.active_task_ids.add(node.id)
        elif node.kind == Kind.PROJECT: self.project_ids.add(node.id)

    def invalidate_records(self):
        for store in (self.sessions, self.history, self.operations, self.recurrences, *self._notes.values()):
            store.invalidate()


    def _require_writable(self) -> None:
        if self.read_only:
            raise ReadOnlyError(tr('ui.app.workspace_ul_este_deschis_doar_pentru_citire'))

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
            self.issues.append(LoadIssue('warning', 'settings_invalid', tr('extra.storage.repository.settings_json_invalid', exc=exc)))
            return Settings()

    def save_settings(self, settings: Settings) -> None:
        self._require_writable()
        atomic_write_json(self.settings_path, settings.model_dump(mode="json"))

    # ---- loading ----------------------------------------------------
    def load(self, *, force=False) -> None:
        with self._mutex:
            self.reload_generation += 1
            self.generation += 1
            self.aggregate_generation += 1
            self._index_dirty = True
            self._cache_entries = {}
            if not force and not (self.system_dir / 'cache' / 'nodes-dirty.json').exists():
                try:
                    cached, _, _ = read_json(self.cache_path, allow_backup=False)
                    if cached['version'] == 1 and cached['workspace_id'] == self.meta.id and cached['checksum'] == checksum(cached['nodes']) and isinstance(cached['nodes'],dict):
                        self._cache_entries = cached['nodes']
                        self._index_dirty = False
                except (CorruptFileError, KeyError, TypeError):
                    pass
            self.nodes.clear()
            self.dirs.clear()
            self._hashes.clear()
            self._stamps.clear()
            self.issues = []
            if self.nodes_dir.exists():
                self._scan(self.nodes_dir, None, parent_known=False)
            self.task_ids.clear(); self.active_task_ids.clear(); self.project_ids.clear()
            for node in self.nodes.values(): self.index_node(node)
            self._validate_graph()
            if len(self._cache_entries) != len(self.nodes): self._index_dirty = True
            self._cache_entries = {}
            if not self.index_path.exists(): self._index_dirty = True

    def _issue(self, severity: str, code: str, message: str, path: Path | None = None,
               node_id: str | None = None) -> None:
        self.issues.append(LoadIssue(severity, code, message, str(path) if path else None, node_id))

    def _scan(self, container: Path, physical_parent: str | None, parent_known: bool = True) -> None:
        if not container.exists():
            return
        try:
            entries = sorted(container.iterdir(), key=lambda p: p.name)
        except OSError as exc:
            self._issue('error', 'scan_failed', tr('extra.storage.repository.nu_se_poate_citi', container=container, exc=exc), container)
            return
        for entry in entries:
            self._load_entry(entry, physical_parent, parent_known)

    def _load_entry(self, entry: Path, physical_parent: str | None, parent_known: bool = True) -> None:
        if not entry.is_dir() or is_reparse_point(entry) or entry.name.startswith("."):
            return
        njson = entry / "node.json"
        if not njson.is_file():
            self._issue("warning", "dir_without_node_json",
                        tr('storage.repository.directorul_nu_contine_node_json_si_a_fost_ignorat', entry_name=entry.name), entry)
            return
        try:
            entry_data = self._cache_entries.get(str(entry.relative_to(self.root)))
            if isinstance(entry_data, dict) and entry_data.get('stamp') == signature(njson):
                try:
                    digest = entry_data['digest']
                    if set(entry_data['meta']) != set(Node.model_fields) - {'attachments','checklist'}:
                        raise ValueError('metadate incomplete')
                    node = NavigationNode.model_validate(entry_data['meta'])
                    if not isinstance(digest, str) or len(digest) != 64:
                        raise ValueError('hash invalid')
                    node._loader = lambda path=njson: Node.model_validate(migrate_node_data(read_json(path)[0]))
                    from_bak = False
                except (KeyError, TypeError, ValueError):
                    self._index_dirty = True
                    data, digest, from_bak = read_json(njson)
                    node = Node.model_validate(migrate_node_data(data))
            else:
                self._index_dirty = True
                data, digest, from_bak = read_json(njson)
                node = Node.model_validate(migrate_node_data(data))
        except (CorruptFileError, PydanticValidationError) as exc:
            self._issue("error", "node_corrupt", f"{njson}: {exc}", njson)
            # Copiii raman incarcabili; parintele fizic este necunoscut.
            self._scan(entry / "children", None, parent_known=False)
            return
        if from_bak:
            self._stamps.pop(node.id,None)
            self._issue("warning", "node_from_backup",
                        tr('extra.storage.repository.node_json_corupt_s_a_folosit_copia_bak', entry_name=entry.name), njson, node.id)
        if node.id in self.nodes:
            self._issue("error", "duplicate_id",
                        tr('storage.repository.uuid_duplicat_in_deja_in', node_id=node.id, entry=entry, self_dirs_node_id=self.dirs[node.id]), entry, node.id)
            return
        if not is_node_dirname(entry.name):
            self._issue("warning", "unusual_dirname", tr('storage.repository.nume_director_neobisnuit', entry_name=entry.name), entry, node.id)
        self.nodes[node.id] = node
        self.index_node(node)
        self.dirs[node.id] = entry
        self._hashes[(node.id, "node.json")] = digest
        if not from_bak: self._stamps[node.id] = signature(njson)
        if parent_known and node.parent_id != physical_parent:
            self._issue("warning", "parent_mismatch",
                        tr('storage.repository.parent_id_nu_corespunde_locatiei_fizice', node_title=node.title), entry, node.id)
        self._scan(entry / "children", node.id)

    def load_node_dir(self, entry: Path, physical_parent: str | None = None) -> None:
        """Incarca un singur director de nod (si eventualii copii din layout vechi), de ex. dupa restaurare din cos."""
        with self._mutex:
            self.mark_index_dirty()
            self.generation += 1
            self.aggregate_generation += 1
            self._load_entry(entry, physical_parent, parent_known=False)

    def _validate_graph(self) -> None:
        for node in self.nodes.values():
            if node.parent_id is not None and node.parent_id not in self.nodes:
                self._issue("warning", "missing_parent",
                            tr('storage.repository.refera_un_parinte_inexistent_apare_ca_orfan', node_title=node.title), self.dirs[node.id], node.id)
            for ref in node.related_node_ids:
                if ref not in self.nodes:
                    self._issue("warning", "dangling_related", tr('storage.repository.legatura_catre_nod_inexistent', node_title=node.title, ref=ref),
                                None, node.id)
            for ref in node.depends_on_ids:
                if ref not in self.nodes:
                    self._issue("warning", "dangling_dependency",
                                tr('storage.repository.dependenta_catre_nod_inexistent', node_title=node.title, ref=ref), None, node.id)
        for node in self.nodes.values():
            if node.continuation_of and node.continuation_of not in self.nodes:
                self._issue('warning','missing_continuation',tr('storage.repository.taskul_sursa_al_cerintei_este_indisponibil'),None,node.id)
            current=node.continuation_of;visited={node.id}
            while current in self.nodes:
                if current in visited:
                    self._issue('error','continuation_cycle',tr('storage.repository.ciclu_in_lantul_cerintelor'),None,node.id);break
                visited.add(current);current=self.nodes[current].continuation_of
        for node in self.nodes.values():
            seen = {node.id}
            cur = node.parent_id
            while cur is not None and cur in self.nodes:
                if cur in seen:
                    self._issue("error", "parent_cycle", tr('storage.repository.ciclu_in_ierarhie_la', node_title=node.title), None, node.id)
                    break
                seen.add(cur)
                cur = self.nodes[cur].parent_id

    # ---- node persistence -------------------------------------------
    def create_node(self, node: Node, description: str = "") -> Path:
        with self._mutex:
            self._require_writable()
            if node.id in self.nodes:
                raise ValidationError(tr('extra.storage.repository.uuid_deja_folosit', node_id=node.id))
            if node.parent_id is not None and node.parent_id not in self.nodes:
                raise NotFoundError(tr('storage.repository.parintele_nu_exista', node_parent_id=node.parent_id))
            target = self.nodes_dir / physical_dirname(node.title, node.id)
            ensure_path_fits(target)
            if target.exists():
                raise StorageError(tr('storage.repository.directorul_exista_deja', target_name=target.name))
            self.mark_index_dirty()
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
                raise StorageError(tr('storage.repository.crearea_nodului_a_esuat', exc=exc)) from exc
            self.generation += 1
            self.aggregate_generation += 1
            self.nodes[node.id] = node
            self.index_node(node)
            self.dirs[node.id] = target
            self._hashes[(node.id, "node.json")] = digest
            self._stamps[node.id] = signature(target / "node.json")
            return target

    def _check_unmodified(self, node_id: str, name: str, path: Path) -> None:
        recorded = self._edit_baselines.get((node_id,name),self._hashes.get((node_id, name)))
        if recorded is None:
            return
        if not path.exists():
            raise ExternalModificationError(tr('storage.repository.a_fost_sters_din_afara_aplicatiei', name=name, path_parent_name=path.parent.name))
        if sha256_file(path) != recorded:
            raise ExternalModificationError(
                tr('storage.repository.din_a_fost_modificat_din_afara_aplicatiei_reincarca_workspace_ul', name=name, path_parent_name=path.parent.name)
            )

    def write_node(self, new: Node) -> Node:
        """Scrie varianta `new` (cu revizie incrementata). Nu schimba starea in memorie daca scrierea esueaza."""
        with self._mutex:
            self._require_writable()
            old = self.nodes.get(new.id)
            if old is None:
                raise NotFoundError(tr('storage.repository.nodul_nu_exista', new_id=new.id))
            path = self.dirs[new.id] / "node.json"
            self._check_unmodified(new.id, "node.json", path)
            stored = new.model_copy(update={"revision": old.revision + 1, "updated_at": utcnow()})
            self.mark_index_dirty()
            digest = atomic_write_json(path, stored.model_dump(mode="json"))
            self.generation += 1
            if any(getattr(old,k) != getattr(stored,k) for k in ('parent_id','status','estimated_minutes','remaining_minutes')):
                self.aggregate_generation += 1
            self.nodes[new.id] = stored
            self.index_node(stored)
            self._edit_baselines.pop((new.id,"node.json"),None)
            self._hashes[(new.id, "node.json")] = digest
            self._stamps[new.id] = signature(path)
            return stored

    def reload_node(self, node_id: str) -> Node:
        with self._mutex:
            path = self.dirs[node_id] / "node.json"
            data, digest, _ = read_json(path)
            node = Node.model_validate(migrate_node_data(data))
            self.generation += 1
            self.aggregate_generation += 1
            self.nodes[node_id] = node
            self.index_node(node)
            self._hashes[(node_id, "node.json")] = digest
            self._stamps[node_id] = signature(path)
            return node

    def note_dir_relocated(self, node_id: str, new_dir: Path) -> None:
        """Actualizeaza caile in memorie pentru nod si descendentii lui dupa o mutare fizica."""
        with self._mutex:
            self.mark_index_dirty()
            self.generation += 1
            self.aggregate_generation += 1
            old_dir = self.dirs[node_id]
            for nid, d in list(self.dirs.items()):
                try:
                    rel = d.relative_to(old_dir)
                except ValueError:
                    continue
                self.dirs[nid] = new_dir / rel

    def forget_subtree(self, node_ids: list[str]) -> None:
        with self._mutex:
            self.mark_index_dirty()
            self.generation += 1
            self.aggregate_generation += 1
            for nid in node_ids:
                self.nodes.pop(nid, None)
                self.task_ids.discard(nid); self.active_task_ids.discard(nid); self.project_ids.discard(nid)
                self.dirs.pop(nid, None)
                self._stamps.pop(nid,None)
                self._hashes.pop((nid, "node.json"), None)
                self._hashes.pop((nid, "description.md"), None)

    # ---- description ------------------------------------------------
    def read_description(self, node_id: str, *, observe: bool = True) -> str:
        """An editor load observes a new baseline; a read-only snapshot must preserve it."""
        path = self.dirs[node_id] / "description.md"
        if observe:
            self._edit_baselines.pop((node_id,"description.md"),None)
            self._edit_baselines.pop((node_id,"node.json"),None)
        if not path.exists():
            if observe:
                self._hashes.pop((node_id, "description.md"), None)
            return ""
        raw = path.read_bytes()
        from .atomic import sha256_bytes

        if observe:
            self._hashes[(node_id, "description.md")] = sha256_bytes(raw)
        return raw.decode("utf-8-sig")

    def write_description(self, node_id: str, text: str) -> None:
        with self._mutex:
            self._require_writable()
            path = self.dirs[node_id] / "description.md"
            self._check_unmodified(node_id, "description.md", path)
            self._hashes[(node_id, "description.md")] = atomic_write_text(path, text)
            self._edit_baselines.pop((node_id,"description.md"),None)

    # ---- notes ------------------------------------------------------
    def notes_store(self, node_id: str) -> RecordStore[NoteEntry]:
        directory = self.dirs[node_id] / 'notes'
        if node_id not in self._notes or self._notes[node_id].directory != directory:
            self._notes[node_id] = RecordStore(directory, NoteEntry, writable=lambda: not self.read_only)
        return self._notes[node_id]

    # ---- index ------------------------------------------------------
    def write_index(self) -> None:
        """Checkpoint disposable indexes at close/reload, never on every field edit."""
        if self.read_only or not self._index_dirty:
            return
        entries = {}
        legacy = {}
        try:
            for nid, node in self.nodes.items():
                rel = str(self.dirs[nid].relative_to(self.root))
                if nid not in self._stamps: continue
                entries[rel] = {'meta':navigation_data(node),
                                'stamp':self._stamps[nid],
                                'digest':self._hashes[(nid,'node.json')]}
                legacy[nid] = {'title':node.title,'kind':node.kind.value,'parent_id':node.parent_id,
                               'status':node.status.value if node.status else None,
                               'due_date':node.due_date.isoformat() if node.due_date else None,'dir':rel}
            write_cache(self.cache_path, {'version':1,'workspace_id':self.meta.id,'nodes':entries,'checksum':checksum(entries)})
            # Preserve legacy schema for backup/diagnostic consumers. Not a loading authority.
            atomic_write_json(self.index_path, {'schema_version':SCHEMA_VERSION,
                'generated_at':fmt_utc(utcnow()),'nodes':legacy}, keep_backup=False)
            (self.system_dir / 'cache' / 'nodes-dirty.json').unlink(missing_ok=True)
            self._index_dirty = False
        except (StorageError, OSError, KeyError):
            log.warning('Index nescris; va fi reconciliat la deschidere.',exc_info=True)
