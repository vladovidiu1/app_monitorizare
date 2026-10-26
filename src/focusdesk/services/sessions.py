"""Sesiuni de lucru planificate (calendar local)."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta

from ..domain.common import utcnow
from ..domain.models import CLOSED_STATUSES, Kind, Node
from ..domain.session import SessionRecord
from ..errors import FocusDeskError, NotFoundError, ValidationError
from .workspace import Workspace

log = logging.getLogger(__name__)

TITLE_PREFIX = "[FocusDesk] Lucru — "


def _minute(d: datetime) -> datetime:
    """Sesiunile se tin la precizie de minut (persistenta in secunde, Outlook in minute)."""
    return d.replace(second=0, microsecond=0)


class OverlapError(ValidationError):
    def __init__(self, conflicts: list[SessionRecord]) -> None:
        super().__init__(f"Intervalul se suprapune cu {len(conflicts)} sesiune(i) existente.")
        self.conflicts = conflicts


class BlockedByDependencies(ValidationError):
    def __init__(self, blockers: list[Node]) -> None:
        super().__init__("Task-ul depinde de task-uri nefinalizate: " + ", ".join(b.title for b in blockers))
        self.blockers = blockers


def session_signature(s: SessionRecord) -> str:
    raw = f"{s.start_at.isoformat()}|{s.end_at.isoformat()}|{s.status}|{s.node_id}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


class SessionService:
    def __init__(self, ws: Workspace) -> None:
        self.ws = ws

    # ---- queries ----------------------------------------------------
    def all(self, *, check=None) -> list[SessionRecord]:
        return self.ws.repo.sessions.list_all(check=check)

    def for_node(self, node_id: str, include_cancelled: bool = True) -> list[SessionRecord]:
        out = [s for s in self.all() if s.node_id == node_id and (include_cancelled or s.status != "cancelled")]
        return sorted(out, key=lambda s: s.start_at)

    def between(self, start: datetime, end: datetime, statuses: tuple[str, ...] = ("planned", "active")) -> list[SessionRecord]:
        return sorted((s for s in self.all() if s.status in statuses and s.start_at < end and s.end_at > start),
                      key=lambda s: s.start_at)

    def overlaps(self, start: datetime, end: datetime, ignore_id: str | None = None) -> list[SessionRecord]:
        return [s for s in self.between(start, end) if s.id != ignore_id]

    # ---- creation ---------------------------------------------------
    def create(self, node_id: str, start: datetime, end: datetime, *, note: str | None = None,
               reserve_calendar: bool = False, origin: str = "manual", allow_overlap: bool = False,
               override_dependencies: bool = False) -> SessionRecord:
        self.ws.repo._require_writable()
        node = self.ws.get(node_id)
        start, end = _minute(start), _minute(end)
        if node.kind != Kind.TASK:
            raise ValidationError("Sesiunile se planifică pentru task-uri.")
        if node.status in CLOSED_STATUSES:
            raise ValidationError("Task-ul este finalizat sau anulat.")
        if end <= start:
            raise ValidationError("Sfârșitul trebuie să fie după început.")
        if end <= utcnow():
            raise ValidationError("Sesiunea se termină în trecut.")
        blockers = self.ws.unfinished_dependencies(node_id)
        if blockers and not override_dependencies:
            raise BlockedByDependencies(blockers)
        conflicts = self.overlaps(start, end)
        if conflicts and not allow_overlap:
            raise OverlapError(conflicts)
        s = SessionRecord(node_id=node_id, workspace_id=self.ws.id, start_at=start, end_at=end,
                          tz=self.ws.settings.timezone, note=(note or "").strip() or None,
                          reserve_calendar=reserve_calendar, origin=origin)  # type: ignore[arg-type]
        if reserve_calendar:
            s.sync.state = "pending"
        self.ws.repo.sessions.save(s)
        self.ws.emit("sessions_changed")
        return s

    def update(self, session_id: str, *, start: datetime | None = None, end: datetime | None = None,
               note: str | None = None, reserve_calendar: bool | None = None,
               allow_overlap: bool = False) -> SessionRecord:
        self.ws.repo._require_writable()
        s = self.ws.repo.sessions.get(session_id)
        if s.status not in ("planned",):
            raise ValidationError("Se pot modifica doar sesiunile planificate.")
        new_start, new_end = _minute(start or s.start_at), _minute(end or s.end_at)
        if new_end <= new_start:
            raise ValidationError("Sfârșitul trebuie să fie după început.")
        conflicts = self.overlaps(new_start, new_end, ignore_id=s.id)
        if conflicts and not allow_overlap:
            raise OverlapError(conflicts)
        changed_time = (new_start, new_end) != (s.start_at, s.end_at)
        s.set_interval(new_start, new_end)
        if note is not None:
            s.note = note.strip() or None
        if reserve_calendar is not None:
            s.reserve_calendar = reserve_calendar
        if s.sync.state in ("saved_locally", "conflict") and changed_time:
            s.sync.state = "pending"  # urmeaza update in calendarul extern
        elif s.reserve_calendar and s.sync.state in ("none", "detached"):
            s.sync.state = "pending"
        self.ws.repo.sessions.save(s)
        self.ws.emit("sessions_changed")
        return s

    def cancel(self, session_id: str) -> SessionRecord:
        self.ws.repo._require_writable()
        s = self.ws.repo.sessions.get(session_id)
        if s.status not in ("planned", "active"):
            raise ValidationError("Sesiunea nu mai poate fi anulată.")
        s.status = "cancelled"
        if s.sync.entry_id and s.sync.state in ("saved_locally", "pending", "conflict"):
            s.sync.state = "pending"
        elif s.sync.state == "pending":
            s.sync.state = "cancelled"
        self.ws.repo.sessions.save(s)
        self.ws.emit("sessions_changed")
        return s

    def mark_missed(self, now: datetime | None = None) -> int:
        """Sesiunile planificate care au trecut fara sa fie pornite devin `missed`."""
        if self.ws.read_only:
            return 0
        now = now or utcnow()
        n = 0
        for s in self.all():
            if s.status == "planned" and s.end_at < now:
                s.status = "missed"
                self.ws.repo.sessions.save(s)
                n += 1
        if n:
            self.ws.emit("sessions_changed")
        return n

    # ---- calendar text ------------------------------------------------
    @staticmethod
    def title_for(node: Node) -> str:
        return f"{TITLE_PREFIX}{node.title}"

    def description_for(self, node: Node, session: SessionRecord, *, include_details: bool = False) -> str:
        """Fara cai locale; fragment din descriere doar cu optiune explicita."""
        lines = [
            "Rezervare de timp creată de FocusDesk (sesiune de lucru personală).",
            f"Task: {node.title}",
            f"Task UUID: {node.id}",
            f"Sesiune UUID: {session.id}",
            f"Workspace UUID: {self.ws.id}",
        ]
        if node.next_action:
            lines.append(f"Următorul pas: {node.next_action}")
        if session.note:
            lines.append(f"Notă: {session.note}")
        if include_details:
            try:
                desc = self.ws.get_description(node.id).strip()
            except FocusDeskError:
                desc = ""
            if desc:
                lines.append("Descriere: " + desc[:500])
        return "\n".join(lines)
