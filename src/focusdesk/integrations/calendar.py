"""Protocol de calendar si implementarile locale; implementarea Outlook COM este separata."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable

from ..domain.session import SessionRecord, SyncInfo


@dataclass(frozen=True)
class BusyInterval:
    start: datetime  # UTC
    end: datetime  # UTC
    source: str = "local"  # local | outlook | ...
    title: str = ""
    status: str = "busy"  # busy | tentative | oof | working_elsewhere


@dataclass(frozen=True)
class Capabilities:
    """Ce poate face efectiv providerul; UI-ul nu promite mai mult."""

    read_availability: bool = False
    create: bool = False
    update: bool = False
    cancel: bool = False
    auto_sync: bool = False


@dataclass
class AvailabilityResult:
    busy: list[BusyInterval] = field(default_factory=list)
    verified_scope: str = "local"  # "local" | "outlook"
    note: str = "Disponibilitate verificată doar local"
    warnings: list[str] = field(default_factory=list)


@runtime_checkable
class CalendarProvider(Protocol):
    name: str
    label: str
    capabilities: Capabilities

    def get_availability(self, start: datetime, end: datetime) -> AvailabilityResult: ...

    def create_session(self, session: SessionRecord, title: str, description: str) -> SyncInfo: ...

    def update_session(self, session: SessionRecord, title: str, description: str) -> SyncInfo: ...

    def cancel_session(self, session: SessionRecord) -> SyncInfo: ...


class EmailAdapter(Protocol):
    """Adaptor optional, dezactivat implicit, pentru trimiterea unui ICS prin mecanismul de email existent.

    FocusDesk nu include o implementare si nu trimite mesaje automat; configuratia trebuie furnizata
    explicit de utilizator. Trimiterea unui email nu inseamna drept de scriere in calendar.
    """

    def send_ics(self, ics_path: str, recipient: str, subject: str) -> None: ...


class NotSupported(Exception):
    pass


class LocalOnlyProvider:
    name = "local"
    label = "Calendar local"
    capabilities = Capabilities()

    def get_availability(self, start: datetime, end: datetime) -> AvailabilityResult:
        return AvailabilityResult()

    def create_session(self, session: SessionRecord, title: str, description: str) -> SyncInfo:
        raise NotSupported("Calendarul local nu sincronizează cu un calendar extern.")

    def update_session(self, session: SessionRecord, title: str, description: str) -> SyncInfo:
        raise NotSupported("Calendarul local nu sincronizează cu un calendar extern.")

    def cancel_session(self, session: SessionRecord) -> SyncInfo:
        raise NotSupported("Calendarul local nu sincronizează cu un calendar extern.")
