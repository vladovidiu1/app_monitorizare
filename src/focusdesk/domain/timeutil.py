"""Conversii intre ora locala (cu fus orar) si UTC, cu tratarea schimbarii orei."""

from __future__ import annotations

from ..i18n import tr

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo


class AmbiguousLocalTime(ValueError):
    """Ora locala este ambigua (toamna) sau inexistenta (primavara)."""


def local_to_utc(day: date, at: time, tz_name: str, *, ambiguous: str = "error") -> datetime:
    """`ambiguous`: 'error' refuza; 'first' foloseste prima aparitie a orei ambigue."""
    tz = ZoneInfo(tz_name)
    naive = datetime.combine(day, at)
    first = naive.replace(tzinfo=tz, fold=0)
    second = naive.replace(tzinfo=tz, fold=1)
    utc_first = first.astimezone(timezone.utc)
    utc_second = second.astimezone(timezone.utc)
    if utc_first != utc_second and ambiguous == "error":
        raise AmbiguousLocalTime(tr('domain.timeutil.ora_din_este_ambigua_la_schimbarea_orei', at=at, day=day))
    if utc_first.astimezone(tz).replace(tzinfo=None) != naive:
        raise AmbiguousLocalTime(tr('domain.timeutil.ora_din_nu_exista_schimbarea_orei', at=at, day=day))
    return utc_first


def utc_to_local(value: datetime, tz_name: str) -> datetime:
    return value.astimezone(ZoneInfo(tz_name))


def local_day_bounds_utc(day: date, tz_name: str) -> tuple[datetime, datetime]:
    """Inceputul si sfarsitul zilei locale, in UTC (o zi cu DST poate avea 23 sau 25 de ore)."""
    from datetime import timedelta

    tz = ZoneInfo(tz_name)
    start = datetime.combine(day, time(0, 0), tzinfo=tz)
    end = datetime.combine(day + timedelta(days=1), time(0, 0), tzinfo=tz)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)
