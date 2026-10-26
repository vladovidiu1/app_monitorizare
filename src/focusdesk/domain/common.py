"""Primitive comune pentru timp, identificatori si tipuri Pydantic."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Annotated

from pydantic import AfterValidator, PlainSerializer


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def fmt_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("data/ora trebuie sa contina fus orar (UTC)")
    return value.astimezone(timezone.utc)


UtcDateTime = Annotated[
    datetime,
    AfterValidator(_require_aware),
    PlainSerializer(fmt_utc, return_type=str),
]


def new_id() -> str:
    return str(uuid.uuid4())


def short_id(node_id: str) -> str:
    return uuid.UUID(node_id).hex[:8]


def is_uuid(value: str) -> bool:
    try:
        return str(uuid.UUID(value)) == value.lower()
    except (ValueError, AttributeError, TypeError):
        return False


def today_local(tz_name: str = "Europe/Bucharest") -> date:
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo(tz_name)).date()
