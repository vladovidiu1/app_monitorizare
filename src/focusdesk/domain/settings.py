"""Setari ale workspace-ului (`_system/settings.json`)."""

from __future__ import annotations

from datetime import date, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .models import SCHEMA_VERSION


class _Base(BaseModel):
    model_config = ConfigDict(extra="allow", validate_assignment=True)


def _parse_hhmm(value: str) -> time:
    h, m = value.split(":")
    return time(int(h), int(m))


class DaySchedule(_Base):
    enabled: bool = True
    start: str = "09:00"
    end: str = "17:30"

    @field_validator("start", "end")
    @classmethod
    def _hhmm(cls, v: str) -> str:
        _parse_hhmm(v)
        return v

    @model_validator(mode="after")
    def _order(self) -> "DaySchedule":
        if self.enabled and _parse_hhmm(self.start) >= _parse_hhmm(self.end):
            raise ValueError("ora de inceput trebuie sa fie inainte de sfarsit")
        return self

    def start_time(self) -> time:
        return _parse_hhmm(self.start)

    def end_time(self) -> time:
        return _parse_hhmm(self.end)


class BreakSlot(_Base):
    start: str = "12:30"
    end: str = "13:00"

    @field_validator("start", "end")
    @classmethod
    def _hhmm(cls, v: str) -> str:
        _parse_hhmm(v)
        return v

    def start_time(self) -> time:
        return _parse_hhmm(self.start)

    def end_time(self) -> time:
        return _parse_hhmm(self.end)


def _default_week() -> dict[str, DaySchedule]:
    week = {str(i): DaySchedule() for i in range(5)}
    week["5"] = DaySchedule(enabled=False)
    week["6"] = DaySchedule(enabled=False)
    return week


class CheckpointSettings(_Base):
    enabled_daily: bool = False
    daily_time: str = "17:00"
    on_session_end: bool = True
    retention: int = 10
    max_total_mb: int = 500
    max_file_mb: int = 50
    exclude_names: list[str] = Field(
        default_factory=lambda: [
            ".git", ".venv", "venv", "__pycache__", "node_modules", "build", "dist",
            "snapshots", "backups", ".env", "*.pem", "*.key", "*.pfx", "id_rsa*",
            "credentials*", "*.secret", "*.kdbx",
        ]
    )

    @field_validator("daily_time")
    @classmethod
    def _hhmm(cls, v: str) -> str:
        _parse_hhmm(v)
        return v


class OutlookSettings(_Base):
    enabled: bool = False
    calendar_store_id: str | None = None
    calendar_folder_id: str | None = None
    calendar_name: str | None = None
    reminder_minutes: int = 15
    include_details: bool = False
    tentative_policy: Literal["busy", "free"] = "busy"
    working_elsewhere_policy: Literal["busy", "free"] = "free"
    category: str | None = None


class BackupSettings(_Base):
    retention: int = 7
    external_dir: str | None = None
    include_files: bool = False
    daily: bool = True


class Settings(_Base):
    schema_version: int = SCHEMA_VERSION
    timezone: str = "Europe/Bucharest"
    work_hours: dict[str, DaySchedule] = Field(default_factory=_default_week)
    breaks: list[BreakSlot] = Field(default_factory=lambda: [BreakSlot()])
    holidays: list[date] = Field(default_factory=list)
    min_session_minutes: int = 30
    max_session_minutes: int = 120
    gap_minutes: int = 10
    daily_reserve_minutes: int = 60
    backup: BackupSettings = Field(default_factory=BackupSettings)
    checkpoints: CheckpointSettings = Field(default_factory=CheckpointSettings)
    outlook: OutlookSettings = Field(default_factory=OutlookSettings)
    vscode_path: str | None = None
    ics_email_adapter_enabled: bool = False
    inbox_default_parent: str | None = None
    max_today_priorities: int = 3

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        from zoneinfo import ZoneInfo

        try:
            ZoneInfo(v)
        except Exception as exc:  # ZoneInfoNotFoundError, ModuleNotFoundError, ValueError...
            raise ValueError(f"Fus orar necunoscut: {v!r}") from exc
        return v

    @model_validator(mode="after")
    def _limits(self) -> "Settings":
        if self.min_session_minutes <= 0 or self.max_session_minutes < self.min_session_minutes:
            raise ValueError("durata minima/maxima a sesiunii este invalida")
        if self.gap_minutes < 0 or self.daily_reserve_minutes < 0:
            raise ValueError("pauza si rezerva nu pot fi negative")
        return self
