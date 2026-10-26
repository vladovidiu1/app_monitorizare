"""Export iCalendar (.ics): UID stabil, UTC, TRANSP:OPAQUE. Exportul nu este import si nu este sincronizare."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from icalendar import Calendar, Event

from ..domain.common import utcnow
from ..domain.session import SessionRecord
from ..storage.atomic import atomic_write_bytes
from .calendar import AvailabilityResult, Capabilities, NotSupported

PRODID = "-//FocusDesk//Sesiuni de lucru//RO"
EXPORT_STATE_TEXT = "Exportat — necesită import în calendar"


def stable_uid(workspace_id: str, session_id: str) -> str:
    return f"{uuid.uuid5(uuid.NAMESPACE_URL, f'focusdesk:{workspace_id}:{session_id}')}@focusdesk.local"


@dataclass
class IcsItem:
    session: SessionRecord
    title: str
    description: str
    sequence: int = 0
    cancelled: bool = False


def build_ics(items: list[IcsItem], workspace_id: str, *, now: datetime | None = None) -> bytes:
    cal = Calendar()
    cal.add("prodid", PRODID)
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    stamp = (now or utcnow()).astimezone(timezone.utc)
    for it in items:
        s = it.session
        ev = Event()
        ev.add("uid", stable_uid(workspace_id, s.id))
        ev.add("dtstamp", stamp)
        ev.add("dtstart", s.start_at.astimezone(timezone.utc))
        ev.add("dtend", s.end_at.astimezone(timezone.utc))
        ev.add("sequence", it.sequence)
        ev.add("summary", it.title)
        if it.description:
            ev.add("description", it.description)
        ev.add("status", "CANCELLED" if it.cancelled else "CONFIRMED")
        ev.add("transp", "OPAQUE")
        ev.add("X-MICROSOFT-CDO-BUSYSTATUS", "BUSY")
        ev.add("X-MICROSOFT-CDO-INTENDEDSTATUS", "BUSY")
        cal.add_component(ev)
    return cal.to_ical()


class IcsExportProvider:
    """Nu citeste disponibilitatea si nu creeaza evenimente; produce doar fisiere .ics de importat manual."""

    name = "ics"
    label = "Export ICS"
    capabilities = Capabilities()

    def get_availability(self, start: datetime, end: datetime) -> AvailabilityResult:
        return AvailabilityResult()

    def create_session(self, *a, **k):
        raise NotSupported("Exportul ICS nu creează evenimente automat; importă fișierul în calendar.")

    update_session = create_session
    cancel_session = create_session

    @staticmethod
    def export_to_file(items: list[IcsItem], workspace_id: str, path: Path) -> Path:
        atomic_write_bytes(Path(path), build_ics(items, workspace_id))
        return Path(path)
