"""Sincronizare sesiuni -> calendar Outlook, cu operatii inregistrate inainte de efectul extern.

Serviciul ruleaza pe thread-ul UI si lucreaza doar cu tipuri primitive; apelurile COM le face ComWorker.
`Save()` in Outlook confirma salvarea locala, nu sincronizarea serverului Exchange sau prezenta in Teams.
"""

from __future__ import annotations

from ..i18n import tr

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from ..domain.common import utcnow
from ..domain.session import OperationRecord, SessionRecord
from ..integrations.outlook import AppointmentFields, SyncRequest, SyncResult
from .sessions import SessionService
from .workspace import Workspace

log = logging.getLogger(__name__)

CAL_OP_PREFIX = "calendar_"


@dataclass
class PlannedOp:
    session_id: str
    op: OperationRecord
    request: SyncRequest


@dataclass
class SyncSummary:
    created: int = 0
    updated: int = 0
    cancelled: int = 0
    conflicts: int = 0
    failed: int = 0
    messages: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.created + self.updated + self.cancelled + self.conflicts + self.failed


class CalendarSyncService:
    def __init__(self, ws: Workspace, sessions: SessionService) -> None:
        self.ws = ws
        self.sessions = sessions

    # ---- config -----------------------------------------------------
    def target(self) -> tuple[str, str] | None:
        o = self.ws.settings.outlook
        if o.enabled and o.calendar_store_id and o.calendar_folder_id:
            return o.calendar_store_id, o.calendar_folder_id
        return None

    # ---- recovery ---------------------------------------------------
    def recover_interrupted(self) -> int:
        """Operatii de calendar ramase `pending` (crash): raman vizibile ca esuate si se pot reincerca fara duplicate."""
        n = 0
        for op in self.ws.repo.operations.list_all():
            if op.type.startswith(CAL_OP_PREFIX) and op.state == "pending":
                op.state = "failed"
                op.error = tr('services.calendar_sync.intrerupta_inainte_de_rezultat_reincearca_se_cauta_evenimentul_dupa_uu')
                op.updated_at = utcnow()
                self.ws.repo.operations.save(op)
                sid = op.data.get("session_id")
                try:
                    s = self.ws.repo.sessions.get(sid) if sid else None
                except Exception:
                    s = None
                if s is not None and s.sync.state in ("saved_locally", "none", "pending"):
                    s.sync.state = "pending"
                    self.ws.repo.sessions.save(s)
                n += 1
        return n

    def failed_operations(self) -> list[OperationRecord]:
        return [op for op in self.ws.repo.operations.list_all()
                if op.type.startswith(CAL_OP_PREFIX) and op.state == "failed"]

    # ---- building requests ------------------------------------------
    def _fields(self, s: SessionRecord) -> AppointmentFields | None:
        node = self.ws.nodes.get(s.node_id)
        if node is None:
            return None
        o = self.ws.settings.outlook
        return AppointmentFields(
            subject=self.sessions.title_for(node), start_utc=s.start_at, end_utc=s.end_at,
            body=self.sessions.description_for(node, s, include_details=o.include_details),
            session_id=s.id, workspace_id=self.ws.id, reminder_minutes=o.reminder_minutes, category=o.category)

    def needed_ops(self, session_ids: list[str] | None = None) -> list[tuple[SessionRecord, str]]:
        out: list[tuple[SessionRecord, str]] = []
        now = utcnow()
        for s in self.ws.repo.sessions.list_all():
            if session_ids is not None and s.id not in session_ids:
                continue
            st = s.sync.state
            if st in ("conflict", "detached", "exported", "saved_locally", "cancelled"):
                continue
            has_entry = bool(s.sync.entry_id)
            if s.status == "cancelled":
                if has_entry and st in ("pending", "failed"):
                    out.append((s, "cancel"))
                continue
            if s.status != "planned" or not s.reserve_calendar or s.end_at < now:
                continue
            if has_entry:
                out.append((s, "update"))
            elif st in ("pending", "failed", "none"):
                out.append((s, "create"))
        return out

    def prepare(self, session_ids: list[str] | None = None) -> list[PlannedOp]:
        """Inregistreaza operatiile (pending) INAINTE de efectul extern si construieste cererile COM."""
        target = self.target()
        planned: list[PlannedOp] = []
        for s, op in self.needed_ops(session_ids):
            if s.status == "cancelled" and op == "cancel" and not s.sync.entry_id:
                continue
            fields = self._fields(s) if op != "cancel" else None
            if op != "cancel" and (fields is None or target is None):
                continue
            store = s.sync.store_id or (target[0] if target else None)
            folder = s.sync.calendar_folder_id or (target[1] if target else None)
            req = SyncRequest(op=op, session_id=s.id, workspace_id=self.ws.id, store_id=store, folder_id=folder,
                              entry_id=s.sync.entry_id, stored_signature=s.sync.signature, fields=fields)
            rec = OperationRecord(type=CAL_OP_PREFIX + op, data={"session_id": s.id, "provider": "outlook"})
            self.ws.repo.operations.save(rec)
            planned.append(PlannedOp(s.id, rec, req))
        return planned

    def request_for_conflict(self, session_id: str, choice: str) -> PlannedOp | None:
        """`choice`: 'local' (aplica planul local) | 'pull' (preia din Outlook). `detach` se rezolva local."""
        s = self.ws.repo.sessions.get(session_id)
        fields = self._fields(s)
        target = self.target()
        req = SyncRequest(op="update" if choice == "local" else "pull", session_id=s.id, workspace_id=self.ws.id,
                          store_id=s.sync.store_id or (target[0] if target else None),
                          folder_id=s.sync.calendar_folder_id or (target[1] if target else None),
                          entry_id=s.sync.entry_id, stored_signature=s.sync.signature, fields=fields,
                          force=(choice == "local"))
        rec = OperationRecord(type=CAL_OP_PREFIX + req.op, data={"session_id": s.id, "provider": "outlook",
                                                                "resolution": choice})
        self.ws.repo.operations.save(rec)
        return PlannedOp(s.id, rec, req)

    def detach(self, session_id: str) -> SessionRecord:
        s = self.ws.repo.sessions.get(session_id)
        s.sync.state = "detached"
        s.reserve_calendar = False
        self.ws.repo.sessions.save(s)
        self.ws.emit("sessions_changed")
        return s

    # ---- applying results ---------------------------------------------
    def apply(self, planned: PlannedOp, result: SyncResult, summary: SyncSummary | None = None) -> SessionRecord | None:
        summary = summary if summary is not None else SyncSummary()
        try:
            s = self.ws.repo.sessions.get(planned.session_id)
        except Exception:
            self._finish(planned.op, "failed", tr('services.calendar_sync.sesiune_inexistenta'))
            return None
        now = utcnow()
        state = result.state
        if state in ("saved_locally", "ok"):
            if planned.request.op == "pull":
                if result.pulled_start and result.pulled_end and result.pulled_end > result.pulled_start:
                    s.set_interval(result.pulled_start, result.pulled_end)
            s.sync.provider = "outlook"
            s.sync.state = "saved_locally"
            s.sync.entry_id, s.sync.store_id = result.entry_id, result.store_id
            s.sync.calendar_folder_id = result.folder_id
            s.sync.signature = result.signature
            s.sync.last_synced_at = now
            s.sync.error = None
            self._count(planned.request.op, summary)
            self._finish(planned.op, "done")
        elif state == "cancelled":
            s.sync.provider = "outlook"
            s.sync.state = "cancelled"
            s.sync.last_synced_at = now
            s.sync.error = None
            summary.cancelled += 1
            self._finish(planned.op, "done")
        elif state in ("conflict", "deleted"):
            if state == "deleted" and planned.request.op == "pull":
                s.status = "cancelled"
                s.sync.state = "detached"
                s.reserve_calendar = False
                s.sync.error = tr('services.calendar_sync.evenimentul_a_fost_sters_in_outlook_sesiunea_locala_a_fost_anulata')
                summary.updated += 1
                self._finish(planned.op, "done")
            else:
                s.sync.state = "conflict"
                s.sync.error = result.message or tr('ui.planning.conflict_cu_outlook')
                summary.conflicts += 1
                summary.messages.append(f"Conflict: {result.message}")
                self._finish(planned.op, "failed", result.message)
        else:
            s.sync.state = "failed"
            s.sync.error = result.message
            summary.failed += 1
            summary.messages.append(result.message)
            self._finish(planned.op, "failed", result.message)
        self.ws.repo.sessions.save(s)
        self.ws.emit("sessions_changed")
        return s

    def fail_all(self, planned: list[PlannedOp], message: str) -> None:
        """Timeout/eroare globala COM: operatiile raman vizibile si pot fi reincercate."""
        for p in planned:
            try:
                s = self.ws.repo.sessions.get(p.session_id)
                s.sync.state = "failed"
                s.sync.error = message
                self.ws.repo.sessions.save(s)
            except Exception:
                pass
            self._finish(p.op, "failed", message)
        self.ws.emit("sessions_changed")

    @staticmethod
    def _count(op: str, summary: SyncSummary) -> None:
        if op == "create":
            summary.created += 1
        elif op in ("update", "pull"):
            summary.updated += 1

    def _finish(self, op: OperationRecord, state: str, error: str | None = None) -> None:
        op.state = state  # type: ignore[assignment]
        op.error = error
        op.updated_at = utcnow()
        self.ws.repo.operations.save(op)
