"""Sesiuni de lucru, sincronizare calendar, operatii si sabloane recurente."""

from __future__ import annotations

from datetime import date, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .common import UtcDateTime, is_uuid, new_id, utcnow
from .models import SCHEMA_VERSION, Priority


class _Base(BaseModel):
    model_config = ConfigDict(extra="allow", validate_assignment=True)


SyncState = Literal["none", "pending", "saved_locally", "failed", "conflict", "exported", "detached", "cancelled"]


class SyncInfo(_Base):
    """Obiect de sincronizare, separat de sesiune."""

    provider: str = "none"
    state: SyncState = "none"
    entry_id: str | None = None
    store_id: str | None = None
    calendar_folder_id: str | None = None
    last_synced_at: UtcDateTime | None = None
    signature: str | None = None
    error: str | None = None
    sequence: int = 0
    exported_at: UtcDateTime | None = None
    ics_uid: str | None = None


class SessionRecord(_Base):
    schema_version: int = SCHEMA_VERSION
    id: str = Field(default_factory=new_id)
    node_id: str
    workspace_id: str | None = None
    start_at: UtcDateTime
    end_at: UtcDateTime
    tz: str = "Europe/Bucharest"
    status: Literal["planned", "active", "done", "cancelled", "missed"] = "planned"
    origin: Literal["manual", "assisted", "timer"] = "manual"
    note: str | None = None
    reserve_calendar: bool = False
    actual_seconds: int = 0
    started_actual_at: UtcDateTime | None = None
    stopped_actual_at: UtcDateTime | None = None
    summary: str | None = None
    created_at: UtcDateTime = Field(default_factory=utcnow)
    sync: SyncInfo = Field(default_factory=SyncInfo)

    @field_validator("id", "node_id")
    @classmethod
    def _uuid(cls, v: str) -> str:
        if not is_uuid(v):
            raise ValueError("UUID invalid")
        return v

    @model_validator(mode="after")
    def _interval(self) -> "SessionRecord":
        if self.end_at <= self.start_at:
            raise ValueError("sfarsitul sesiunii trebuie sa fie dupa inceput")
        return self

    @property
    def planned_minutes(self) -> int:
        return int((self.end_at - self.start_at).total_seconds() // 60)

    def set_interval(self, start, end) -> None:
        """Seteaza ambele capete deodata (validate_assignment ar refuza o stare intermediara invalida)."""
        if end <= start:
            raise ValueError("sfarsitul sesiunii trebuie sa fie dupa inceput")
        self.__dict__["start_at"] = start.astimezone(timezone.utc)
        self.__dict__["end_at"] = end.astimezone(timezone.utc)


class OperationRecord(_Base):
    """Jurnal de operatii recuperabile (mutari, calendar extern, restaurari)."""

    schema_version: int = SCHEMA_VERSION
    id: str = Field(default_factory=new_id)
    type: str
    state: Literal["pending", "done", "failed", "rolled_back"] = "pending"
    created_at: UtcDateTime = Field(default_factory=utcnow)
    updated_at: UtcDateTime = Field(default_factory=utcnow)
    data: dict = Field(default_factory=dict)
    steps_done: list[str] = Field(default_factory=list)
    error: str | None = None


class RecurrenceTemplate(_Base):
    """Sablon recurent; instantele sunt task-uri independente cu cheia (template_id, data)."""

    schema_version: int = SCHEMA_VERSION
    id: str = Field(default_factory=new_id)
    title: str
    parent_id: str | None = None
    frequency: Literal["daily", "weekly", "workdays"] = "daily"
    weekdays: list[int] = Field(default_factory=list)
    start_date: date
    end_date: date | None = None
    priority: Priority = Priority.NORMAL
    estimated_minutes: int | None = None
    next_action: str | None = None
    tags: list[str] = Field(default_factory=list)
    generated_dates: list[date] = Field(default_factory=list)
    skipped_dates: list[date] = Field(default_factory=list)
    active: bool = True

    @model_validator(mode="after")
    def _check(self) -> "RecurrenceTemplate":
        if self.frequency == "weekly" and not self.weekdays:
            raise ValueError("o regula saptamanala are nevoie de cel putin o zi")
        if any(d < 0 or d > 6 for d in self.weekdays):
            raise ValueError("zilele saptamanii sunt 0-6")
        return self

    def occurs_on(self, day: date) -> bool:
        if day < self.start_date or (self.end_date and day > self.end_date):
            return False
        if self.frequency == "daily":
            return True
        if self.frequency == "workdays":
            return day.weekday() < 5
        return day.weekday() in self.weekdays
