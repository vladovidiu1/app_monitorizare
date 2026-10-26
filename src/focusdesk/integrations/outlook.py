"""Logica Outlook independenta de COM: modele, executia operatiilor de sincronizare, politici de disponibilitate.

Backend-ul (COM real sau fals pentru teste) lucreaza doar cu tipuri primitive; obiectele COM nu parasesc thread-ul COM.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Protocol

from ..domain.settings import OutlookSettings
from .calendar import AvailabilityResult, BusyInterval

UTC = timezone.utc

BUSY, TENTATIVE, FREE, OOF, WORKING_ELSEWHERE = "busy", "tentative", "free", "oof", "working_elsewhere"
# olBusyStatus: 0 Free, 1 Tentative, 2 Busy, 3 OutOfOffice, 4 WorkingElsewhere
BUSY_STATUS_NAMES = {0: FREE, 1: TENTATIVE, 2: BUSY, 3: OOF, 4: WORKING_ELSEWHERE}
MAX_EVENTS = 3000


@dataclass
class CalendarInfo:
    store_id: str
    store_name: str
    store_kind: str  # exchange_primary | exchange_additional | exchange_public | other
    folder_id: str
    name: str
    is_default: bool = True

    @property
    def is_exchange(self) -> bool:
        return self.store_kind.startswith("exchange")

    @property
    def label(self) -> str:
        kind = {"exchange_primary": "Exchange / Microsoft 365 (cutie principală)",
                "exchange_additional": "Exchange (cutie suplimentară)",
                "exchange_public": "Exchange (folder public)",
                "other": "Fișier local / alt tip (NU se sincronizează cu Teams/Exchange)"}.get(self.store_kind, self.store_kind)
        return f"{self.store_name} › {self.name}  —  {kind}"


@dataclass
class RawEvent:
    start: datetime  # UTC
    end: datetime  # UTC
    busy_status: str
    all_day: bool = False
    subject: str = ""
    session_id: str | None = None


@dataclass
class AppointmentFields:
    subject: str
    start_utc: datetime
    end_utc: datetime
    body: str
    session_id: str
    workspace_id: str
    reminder_minutes: int = 15
    category: str | None = None
    busy_status: int = 2


@dataclass
class AppointmentInfo:
    entry_id: str
    store_id: str
    folder_id: str
    subject: str
    start_utc: datetime
    end_utc: datetime
    busy_status: int
    session_id: str | None
    workspace_id: str | None

    def signature(self) -> str:
        return signature_of(self.subject, self.start_utc, self.end_utc, self.busy_status)


def signature_of(subject: str, start: datetime, end: datetime, busy_status: int) -> str:
    def m(d: datetime) -> str:
        return d.astimezone(UTC).strftime("%Y%m%dT%H%MZ")

    return hashlib.sha1(f"{subject}|{m(start)}|{m(end)}|{busy_status}".encode("utf-8")).hexdigest()[:16]


class OutlookBackend(Protocol):
    def diagnose(self) -> dict: ...

    def list_calendars(self) -> list[CalendarInfo]: ...

    def read_events(self, store_id: str, folder_id: str, start_utc: datetime, end_utc: datetime) -> list[RawEvent]: ...

    def read_calendar_events(self, store_id: str, folder_id: str, start_utc: datetime,
                             end_utc: datetime) -> list[RawEvent]: ...

    def find_by_session(self, store_id: str, folder_id: str, session_id: str, workspace_id: str,
                        around_start: datetime, around_end: datetime) -> AppointmentInfo | None: ...

    def get(self, entry_id: str, store_id: str) -> AppointmentInfo | None: ...

    def create(self, store_id: str, folder_id: str, fields: AppointmentFields) -> AppointmentInfo: ...

    def update(self, entry_id: str, store_id: str, fields: AppointmentFields) -> AppointmentInfo: ...

    def delete(self, entry_id: str, store_id: str) -> None: ...

    def send_mail(self, to: list[str], cc: list[str], subject: str, body: str, *, send: bool) -> str: ...


# ---- availability ---------------------------------------------------------

def merge_intervals(items: list[BusyInterval]) -> list[BusyInterval]:
    out: list[BusyInterval] = []
    for it in sorted(items, key=lambda x: (x.start, x.end)):
        if out and it.start <= out[-1].end:
            last = out[-1]
            out[-1] = BusyInterval(last.start, max(last.end, it.end), last.source, last.title, last.status)
        else:
            out.append(it)
    return out


def availability_from_events(events: list[RawEvent], settings: OutlookSettings,
                             start_utc: datetime, end_utc: datetime) -> AvailabilityResult:
    """Aplica politicile pentru Tentative/WorkingElsewhere; evenimentele libere (Free) nu blocheaza."""
    busy: list[BusyInterval] = []
    warnings: list[str] = []
    for ev in events:
        if ev.end <= start_utc or ev.start >= end_utc:
            continue
        status = ev.busy_status
        if status == FREE:
            continue
        if status == TENTATIVE and settings.tentative_policy == "free":
            continue
        if status == WORKING_ELSEWHERE and settings.working_elsewhere_policy == "free":
            continue
        busy.append(BusyInterval(max(ev.start, start_utc), min(ev.end, end_utc), "outlook", ev.subject, status))
    if len(events) >= MAX_EVENTS:
        warnings.append(f"S-au citit {MAX_EVENTS} evenimente (limită); disponibilitatea poate fi incompletă.")
    return AvailabilityResult(busy=merge_intervals(busy), verified_scope="outlook",
                              note="Disponibilitate verificată în Outlook (calendarul ales)", warnings=warnings)


# ---- sync operations --------------------------------------------------------

@dataclass
class SyncRequest:
    op: str  # create | update | cancel | check | pull
    session_id: str
    workspace_id: str
    store_id: str | None = None
    folder_id: str | None = None
    entry_id: str | None = None
    stored_signature: str | None = None
    fields: AppointmentFields | None = None
    force: bool = False
    around_start: datetime | None = None
    around_end: datetime | None = None


@dataclass
class SyncResult:
    session_id: str
    op: str
    state: str  # saved_locally | failed | conflict | cancelled | ok | deleted
    message: str = ""
    entry_id: str | None = None
    store_id: str | None = None
    folder_id: str | None = None
    signature: str | None = None
    pulled_start: datetime | None = None
    pulled_end: datetime | None = None


def _markers_ok(info: AppointmentInfo, req: SyncRequest) -> bool:
    return info.session_id == req.session_id and info.workspace_id == req.workspace_id


def _result_from(info: AppointmentInfo, req: SyncRequest, state: str = "saved_locally", message: str = "") -> SyncResult:
    return SyncResult(req.session_id, req.op, state, message, info.entry_id, info.store_id, info.folder_id,
                      info.signature(), info.start_utc, info.end_utc)


def execute(backend: OutlookBackend, req: SyncRequest) -> SyncResult:
    """Executa o operatie pentru o sesiune proprie. `Save()` confirma doar salvarea locala in Outlook."""
    try:
        return _execute(backend, req)
    except Exception as exc:  # erorile COM variaza; raportam, nu ascundem
        return SyncResult(req.session_id, req.op, "failed", f"{type(exc).__name__}: {exc}",
                          req.entry_id, req.store_id, req.folder_id)


def _execute(backend: OutlookBackend, req: SyncRequest) -> SyncResult:
    if req.op == "create":
        assert req.fields and req.store_id and req.folder_id
        # Idempotenta: cautam intai dupa UUID-ul sesiunii (retry sau crash intre Save si scrierea JSON).
        existing = backend.find_by_session(req.store_id, req.folder_id, req.session_id, req.workspace_id,
                                           req.around_start or req.fields.start_utc - timedelta(days=1),
                                           req.around_end or req.fields.end_utc + timedelta(days=1))
        if existing is not None:
            expected = signature_of(req.fields.subject, req.fields.start_utc, req.fields.end_utc, req.fields.busy_status)
            if existing.signature() == expected:
                return _result_from(existing, req, message="Eveniment existent regăsit după UUID (fără duplicat).")
            return _result_from(existing, req, "conflict", "Există deja un eveniment cu acest UUID, diferit de plan.")
        info = backend.create(req.store_id, req.folder_id, req.fields)
        return _result_from(info, req, message="Salvat în Outlook (local); sincronizarea Exchange nu este confirmată.")

    if req.op in ("update", "cancel", "check", "pull"):
        info = backend.get(req.entry_id, req.store_id) if req.entry_id and req.store_id else None
        if info is None:
            if req.op == "cancel":
                return SyncResult(req.session_id, req.op, "cancelled", "Evenimentul nu mai exista în Outlook.")
            if req.op == "update" and req.force and req.fields and req.store_id and req.folder_id:
                # Utilizatorul a ales explicit „Aplică planul local”: recreare dupa regasire dupa UUID.
                again = backend.find_by_session(req.store_id, req.folder_id, req.session_id, req.workspace_id,
                                                req.fields.start_utc - timedelta(days=1),
                                                req.fields.end_utc + timedelta(days=1))
                made = again or backend.create(req.store_id, req.folder_id, req.fields)
                return _result_from(made, req, message="Eveniment recreat din planul local.")
            return SyncResult(req.session_id, req.op, "deleted", "Evenimentul a fost șters sau mutat în Outlook.")
        if not _markers_ok(info, req):
            return SyncResult(req.session_id, req.op, "failed",
                              "Evenimentul nu are markerii FocusDesk ai acestei sesiuni; nu este modificat.",
                              info.entry_id, info.store_id, info.folder_id)
        changed = bool(req.stored_signature) and info.signature() != req.stored_signature
        if req.op == "check":
            return _result_from(info, req, "conflict" if changed else "ok",
                                "Modificat în Outlook față de ultima sincronizare." if changed else "")
        if req.op == "pull":
            return _result_from(info, req, "saved_locally", "Preluat din Outlook.")
        if changed and not req.force:
            return _result_from(info, req, "conflict", "Evenimentul a fost modificat în Outlook.")
        if req.op == "cancel":
            backend.delete(info.entry_id, info.store_id)
            return SyncResult(req.session_id, req.op, "cancelled", "Șters în Outlook (în Elemente șterse).")
        assert req.fields
        updated = backend.update(info.entry_id, info.store_id, req.fields)
        return _result_from(updated, req, message="Actualizat în Outlook (local).")
    return SyncResult(req.session_id, req.op, "failed", f"Operație necunoscută: {req.op}")
