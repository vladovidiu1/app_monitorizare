"""Fatada principala pentru operatiile pe noduri; singurul punct de scriere folosit de UI."""

from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from ..domain.common import new_id, utcnow
from pydantic import ValidationError as PydanticValidationError
from ..domain.models import (
    CLOSED_STATUSES, ChecklistItem, HistoryEvent, Kind, NoteEntry, Node, Priority, Status,
)
from ..domain.settings import Settings
from ..errors import CycleError, NotFoundError, ValidationError
from ..storage import operations as ops
from ..storage.repository import LoadIssue, WorkspaceRepository

log = logging.getLogger(__name__)

Listener = Callable[[str, dict], None]
_IMMUTABLE_FIELDS = {"id", "kind", "parent_id", "created_at", "revision", "updated_at", "schema_version"}


class Workspace:
    def __init__(self, repo: WorkspaceRepository) -> None:
        self.repo = repo
        self.settings: Settings = repo.load_settings()
        self.recovery_messages: list[str] = []
        self._listeners: list[Listener] = []

    # ---- life cycle -------------------------------------------------
    @classmethod
    def open(cls, root: Path, *, create: bool = False, name: str = "FocusDesk",
             read_only: bool = False) -> "Workspace":
        repo = WorkspaceRepository.open(Path(root), create=create, name=name, read_only=read_only)
        ws = cls(repo)
        ws.recovery_messages = ops.recover_pending(repo)
        moved = ops.flatten_layout(repo)
        if moved:
            ws.recovery_messages.append(
                f"Structura fizică a fost actualizată: {moved} directoare de task-uri au fost scoase din "
                "foldere imbricate (ierarhia rămâne neschimbată; acum poate avea orice adâncime).")
        repo.load()
        repo.write_index()
        return ws

    def close(self) -> None:
        self.repo.close()

    def reload(self) -> None:
        self.repo.load()
        self.repo.write_index()
        self.emit("reloaded")

    @property
    def read_only(self) -> bool:
        return self.repo.read_only

    @property
    def name(self) -> str:
        return self.repo.meta.name if self.repo.meta else "FocusDesk"

    @property
    def id(self) -> str:
        assert self.repo.meta is not None
        return self.repo.meta.id

    @property
    def root(self) -> Path:
        return self.repo.root

    @property
    def issues(self) -> list[LoadIssue]:
        return self.repo.issues

    # ---- events -----------------------------------------------------
    def subscribe(self, listener: Listener) -> None:
        self._listeners.append(listener)

    def emit(self, event: str, **data: Any) -> None:
        for listener in list(self._listeners):
            try:
                listener(event, data)
            except Exception:
                log.exception("Listener eșuat pentru %s", event)

    # ---- read access ------------------------------------------------
    @property
    def nodes(self) -> dict[str, Node]:
        return self.repo.nodes

    def get(self, node_id: str) -> Node:
        try:
            return self.repo.nodes[node_id]
        except KeyError as exc:
            raise NotFoundError(f"Nodul {node_id} nu există.") from exc

    def node_dir(self, node_id: str) -> Path:
        return self.repo.dirs[node_id]

    def children_map(self) -> dict[str | None, list[Node]]:
        """Copii grupati dupa parinte; orfanii (parinte lipsa/ciclu) apar la radacina."""
        nodes = self.repo.nodes
        cmap: dict[str | None, list[Node]] = {}
        for n in nodes.values():
            pid = n.parent_id if n.parent_id in nodes else None
            cmap.setdefault(pid, []).append(n)
        # Noduri din cicluri: nu sunt accesibile din radacina, le expunem ca orfani.
        reachable: set[str] = set()
        stack = [n.id for n in cmap.get(None, [])]
        while stack:
            cur = stack.pop()
            if cur in reachable:
                continue
            reachable.add(cur)
            stack.extend(c.id for c in cmap.get(cur, []))
        for n in nodes.values():
            if n.id not in reachable:
                cmap[n.parent_id] = [c for c in cmap.get(n.parent_id, []) if c.id != n.id]
                cmap.setdefault(None, []).append(n)
                reachable.add(n.id)
                stack = [c.id for c in cmap.get(n.id, [])]
                while stack:
                    cur = stack.pop()
                    if cur not in reachable:
                        reachable.add(cur)
                        stack.extend(c.id for c in cmap.get(cur, []))
        for lst in cmap.values():
            lst.sort(key=lambda n: (n.sort_order, n.title.lower()))
        return cmap

    def children(self, parent_id: str | None) -> list[Node]:
        return self.children_map().get(parent_id, [])

    def ancestors(self, node_id: str) -> list[Node]:
        """Lantul de parinti de la radacina pana la parintele direct."""
        chain: list[Node] = []
        seen = {node_id}
        cur = self.get(node_id).parent_id
        while cur is not None and cur in self.repo.nodes and cur not in seen:
            seen.add(cur)
            chain.append(self.repo.nodes[cur])
            cur = self.repo.nodes[cur].parent_id
        chain.reverse()
        return chain

    def breadcrumb(self, node_id: str) -> str:
        parts = [n.title for n in self.ancestors(node_id)] + [self.get(node_id).title]
        return " › ".join(parts)

    def subtree_ids(self, node_id: str, include_self: bool = True) -> list[str]:
        return ops.descendants(self.repo, node_id, include_self)

    def nearest_project(self, node_id: str) -> Node | None:
        for anc in reversed(self.ancestors(node_id)):
            if anc.kind == Kind.PROJECT:
                return anc
        return None

    # ---- validation -------------------------------------------------
    def check_parent(self, kind: Kind, parent_id: str | None) -> None:
        if parent_id is None:
            return
        parent = self.get(parent_id)
        if parent.kind == Kind.TASK and kind != Kind.TASK:
            raise ValidationError("Un task poate conține doar subtask-uri.")
        if parent.kind == Kind.PROJECT and kind == Kind.PROJECT:
            raise ValidationError("Un proiect nu poate conține alt proiect; folosește o categorie.")
        if kind == Kind.PROJECT and parent.kind not in (Kind.FOLDER,):
            raise ValidationError("Un proiect poate fi doar la rădăcină sau într-un folder.")

    def _check_writable(self) -> None:
        self.repo._require_writable()

    # ---- create -----------------------------------------------------
    def create_node(self, kind: Kind | str, title: str, parent_id: str | None = None,
                    description: str = "", **fields: Any) -> Node:
        self._check_writable()
        kind = Kind(kind)
        self.check_parent(kind, parent_id)
        siblings = [n for n in self.repo.nodes.values() if n.parent_id == parent_id]
        sort_order = max((n.sort_order for n in siblings), default=0) + 10
        data: dict[str, Any] = {"kind": kind, "title": title, "parent_id": parent_id, "sort_order": sort_order}
        if kind == Kind.TASK:
            data["status"] = Status.TODO
            data["priority"] = Priority.NORMAL
        elif kind == Kind.PROJECT:
            data["status"] = Status.TODO
            data["priority"] = Priority.NORMAL
        data.update({k: v for k, v in fields.items() if k not in _IMMUTABLE_FIELDS})
        self._check_references(data)
        node = self._build_node(data)
        self.repo.create_node(node, description)
        self.record_event("created", node.id, {"title": node.title, "kind": node.kind.value})
        self._after_change()
        self.emit("node_created", node_id=node.id)
        return node

    def quick_capture(self, title: str, parent_id: str | None = None) -> Node:
        """Captura rapida: task in Inbox (status `inbox`), fara alte campuri."""
        return self.create_node(Kind.TASK, title, parent_id, status=Status.INBOX)

    @staticmethod
    def _build_node(data: dict[str, Any]) -> Node:
        try:
            return Node.model_validate(data)
        except PydanticValidationError as exc:
            msgs = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" if e["loc"] else e["msg"]
                             for e in exc.errors())
            raise ValidationError(msgs.replace("Value error, ", "")) from exc

    def _check_references(self, data: dict[str, Any], self_id: str | None = None) -> None:
        for key in ("related_node_ids", "depends_on_ids"):
            for ref in data.get(key, []) or []:
                if ref not in self.repo.nodes:
                    raise ValidationError("Referință către un nod inexistent.")
                if self_id and ref == self_id:
                    raise ValidationError("Un nod nu poate face referire la sine.")

    # ---- update -----------------------------------------------------
    def update_node(self, node_id: str, **changes: Any) -> Node:
        self._check_writable()
        old = self.get(node_id)
        bad = set(changes) & _IMMUTABLE_FIELDS
        if bad:
            raise ValidationError(f"Câmpuri care nu se modifică direct: {', '.join(sorted(bad))}")
        if "depends_on_ids" in changes:
            self._check_dependency_cycle(node_id, list(changes["depends_on_ids"]))
        self._check_references(changes, node_id)
        merged = old.model_dump(mode="python")
        merged.update(changes)
        new_status = changes.get("status")
        if new_status is not None and Status(new_status) != old.status:
            now = utcnow()
            if "completed_at" in changes:
                pass  # data aleasa explicit de utilizator
            elif Status(new_status) in CLOSED_STATUSES:
                merged["completed_at"] = now
            else:
                merged["completed_at"] = None
            if Status(new_status) != Status.WAITING and "waiting_reason" not in changes:
                merged["waiting_reason"] = None
        if (merged.get("pinned_today") is not None
                and merged["pinned_today"] != old.pinned_today):
            self._check_today_limit(merged["pinned_today"], node_id)
        new = self._build_node(merged)
        stored = self.repo.write_node(new)
        if new_status is not None and Status(new_status) != old.status:
            self.record_event("status_changed", node_id, {"from": old.status.value if old.status else None,
                                                          "to": Status(new_status).value})
        if "title" in changes and changes["title"] != old.title:
            self.record_event("renamed", node_id, {"from": old.title, "to": stored.title})
        self._after_change()
        self.emit("node_updated", node_id=node_id)
        return stored

    def rename(self, node_id: str, title: str) -> Node:
        """Schimba titlul; directorul fizic si UUID-ul raman neschimbate."""
        return self.update_node(node_id, title=title)

    def rename_physical(self, node_id: str) -> Path:
        self._check_writable()
        new_dir = ops.rename_physical_dir(self.repo, node_id)
        self.emit("node_updated", node_id=node_id)
        return new_dir

    def _check_today_limit(self, day: date, node_id: str) -> None:
        pinned = [n for n in self.repo.nodes.values()
                  if n.pinned_today == day and n.id != node_id and n.status not in CLOSED_STATUSES]
        if len(pinned) >= self.settings.max_today_priorities:
            raise ValidationError(
                f"Poți marca cel mult {self.settings.max_today_priorities} priorități pentru o zi."
            )

    def set_description(self, node_id: str, text: str) -> None:
        self._check_writable()
        self.repo.write_description(node_id, text)
        self.emit("node_updated", node_id=node_id)

    def get_description(self, node_id: str) -> str:
        return self.repo.read_description(node_id)

    def toggle_checklist(self, node_id: str, items: list[tuple[str, bool]]) -> Node:
        return self.update_node(node_id, checklist=[ChecklistItem(text=t, done=d) for t, d in items])

    # ---- structure --------------------------------------------------
    def move(self, node_id: str, new_parent_id: str | None, sort_order: int | None = None) -> None:
        self._check_writable()
        node = self.get(node_id)
        self.check_parent(node.kind, new_parent_id)
        if new_parent_id is not None and new_parent_id in self.subtree_ids(node_id):
            raise CycleError("Nu poți muta un nod în interiorul propriilor descendenți.")
        if sort_order is None and new_parent_id != node.parent_id:
            siblings = [n for n in self.repo.nodes.values() if n.parent_id == new_parent_id]
            sort_order = max((n.sort_order for n in siblings), default=0) + 10
        old_parent = node.parent_id
        ops.move_node(self.repo, node_id, new_parent_id, sort_order)
        if old_parent != new_parent_id:
            self.record_event("moved", node_id, {"from": old_parent, "to": new_parent_id})
        self._after_change()
        self.emit("node_moved", node_id=node_id)

    def reorder(self, node_id: str, direction: int) -> None:
        """Muta nodul cu o pozitie in sus (-1) sau in jos (+1) printre frati."""
        self._check_writable()
        node = self.get(node_id)
        siblings = self.children(node.parent_id if node.parent_id in self.repo.nodes else None)
        idx = next((i for i, n in enumerate(siblings) if n.id == node_id), None)
        if idx is None:
            return
        j = idx + direction
        if j < 0 or j >= len(siblings):
            return
        siblings[idx], siblings[j] = siblings[j], siblings[idx]
        for pos, sib in enumerate(siblings):
            wanted = (pos + 1) * 10
            if sib.sort_order != wanted:
                self.repo.write_node(sib.model_copy(update={"sort_order": wanted}))
        self._after_change()
        self.emit("node_moved", node_id=node_id)

    # ---- links ------------------------------------------------------
    def add_related(self, node_id: str, other_id: str) -> None:
        node = self.get(node_id)
        self.get(other_id)
        if other_id == node_id:
            raise ValidationError("Un nod nu poate face referire la sine.")
        self.update_node(node_id, related_node_ids=[*node.related_node_ids, other_id])

    def remove_related(self, node_id: str, other_id: str) -> None:
        node = self.get(node_id)
        self.update_node(node_id, related_node_ids=[i for i in node.related_node_ids if i != other_id])

    def add_dependency(self, node_id: str, dep_id: str) -> None:
        node = self.get(node_id)
        self.update_node(node_id, depends_on_ids=[*node.depends_on_ids, dep_id])

    def remove_dependency(self, node_id: str, dep_id: str) -> None:
        node = self.get(node_id)
        self.update_node(node_id, depends_on_ids=[i for i in node.depends_on_ids if i != dep_id])

    def _check_dependency_cycle(self, node_id: str, new_deps: list[str]) -> None:
        node = self.get(node_id)
        if node.kind == Kind.FOLDER and new_deps:
            raise ValidationError("Un folder nu are dependențe.")
        for dep in new_deps:
            if dep == node_id:
                raise CycleError("Un task nu poate depinde de el însuși.")
            if dep not in self.repo.nodes:
                raise ValidationError("Dependență către un nod inexistent.")
        # Cautam daca node_id este accesibil pornind de la oricare dintre noile dependente.
        seen: set[str] = set()
        stack = list(new_deps)
        while stack:
            cur = stack.pop()
            if cur == node_id:
                raise CycleError("Dependența ar crea un ciclu.")
            if cur in seen or cur not in self.repo.nodes:
                continue
            seen.add(cur)
            stack.extend(self.repo.nodes[cur].depends_on_ids)

    def unfinished_dependencies(self, node_id: str) -> list[Node]:
        node = self.get(node_id)
        out = []
        for dep_id in node.depends_on_ids:
            dep = self.repo.nodes.get(dep_id)
            if dep is not None and dep.status not in CLOSED_STATUSES:
                out.append(dep)
        return out

    def referrers(self, node_id: str) -> list[Node]:
        """Noduri care refera `node_id` prin legaturi (nu parinti fizici)."""
        return [n for n in self.repo.nodes.values()
                if node_id in n.related_node_ids or node_id in n.depends_on_ids]

    def linked_nodes(self, node_id: str) -> list[Node]:
        node = self.get(node_id)
        ids = list(dict.fromkeys([*node.related_node_ids, *[n.id for n in self.referrers(node_id)
                                                          if node_id in n.related_node_ids]]))
        return [self.repo.nodes[i] for i in ids if i in self.repo.nodes]

    # ---- archive / trash --------------------------------------------
    def archive(self, node_id: str, future_sessions: str = "ask") -> Node:
        """`future_sessions`: 'keep' | 'cancel'; 'ask' ridica eroare daca exista sesiuni viitoare."""
        self._check_writable()
        pending = self.future_sessions(node_id)
        if pending:
            if future_sessions == "ask":
                raise ValidationError(f"Nodul are {len(pending)} sesiuni viitoare; alege păstrarea sau anularea lor.")
            if future_sessions == "cancel":
                self.cancel_sessions(pending)
        node = self.update_node(node_id, archived_at=utcnow())
        self.record_event("archived", node_id, {})
        return node

    def unarchive(self, node_id: str) -> Node:
        return self.update_node(node_id, archived_at=None)

    def trash(self, node_id: str) -> None:
        self._check_writable()
        node = self.get(node_id)
        ids = self.subtree_ids(node_id)
        self.record_event("trashed", node_id, {"title": node.title, "count": len(ids)})
        ops.trash_node(self.repo, node_id)
        self._after_change()
        self.emit("node_trashed", node_id=node_id)

    def list_trash(self) -> list[dict[str, Any]]:
        return ops.list_trash(self.repo)

    def restore(self, node_id: str, new_parent_id: str | None = ...) -> None:  # type: ignore[assignment]
        self._check_writable()
        ops.restore_node(self.repo, node_id, new_parent_id)
        self.record_event("restored", node_id, {})
        self._after_change()
        self.emit("node_restored", node_id=node_id)

    def purge_trash(self, node_id: str) -> None:
        ops.purge_trash_entry(self.repo, node_id)
        self.emit("trash_changed")

    # ---- sessions (acces minim; logica completa in services.sessions) ---
    def future_sessions(self, node_id: str) -> list:
        now = utcnow()
        ids = set(self.subtree_ids(node_id))
        return [s for s in self.repo.sessions.list_all()
                if s.node_id in ids and s.status == "planned" and s.start_at > now]

    def cancel_sessions(self, sessions: list) -> None:
        for s in sessions:
            s.status = "cancelled"
            if s.sync.state in ("saved_locally", "pending", "conflict") and s.sync.entry_id:
                s.sync.state = "pending"  # reconciliat cu calendarul extern la urmatoarea sincronizare
            self.repo.sessions.save(s)
        self.emit("sessions_changed")

    # ---- journal ----------------------------------------------------
    def add_note(self, node_id: str, text: str, kind: str = "note", **extra: Any) -> NoteEntry:
        self._check_writable()
        self.get(node_id)
        text = text.strip()
        if not text:
            raise ValidationError("Notița este goală.")
        entry = NoteEntry(node_id=node_id, text=text, kind=kind, **extra)  # type: ignore[arg-type]
        self.repo.notes_store(node_id).save(entry)
        self.emit("notes_changed", node_id=node_id)
        return entry

    def list_notes(self, node_id: str) -> list[NoteEntry]:
        notes = self.repo.notes_store(node_id).list_all()
        notes.sort(key=lambda n: n.at, reverse=True)
        return notes

    def record_event(self, type_: str, node_id: str | None, data: dict | None = None) -> None:
        if self.read_only:
            return
        try:
            self.repo.history.save(HistoryEvent(type=type_, node_id=node_id, data=data or {}))
        except Exception:
            log.exception("Evenimentul de istoric nu a putut fi scris")

    def list_history(self, node_id: str | None = None) -> list[HistoryEvent]:
        events = self.repo.history.list_all()
        if node_id is not None:
            events = [e for e in events if e.node_id == node_id]
        events.sort(key=lambda e: e.at, reverse=True)
        return events

    # ---- settings ---------------------------------------------------
    def update_settings(self, settings: Settings) -> None:
        self.repo.save_settings(settings)
        self.settings = settings
        self.emit("settings_changed")

    # ---- internals --------------------------------------------------
    def _after_change(self) -> None:
        self.repo.write_index()
