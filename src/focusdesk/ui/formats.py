"""Parsare si formatare pentru campuri introduse de utilizator (fara dependente Tk)."""

from __future__ import annotations

from ..i18n import tr, date_text

import re
from datetime import date, time, timedelta

from ..domain.timeutil import AmbiguousLocalTime, local_to_utc, utc_to_local  # noqa: F401

_WORDS = {"azi": 0, "astazi": 0, "astăzi": 0, "maine": 1, "mâine": 1, "poimaine": 2, "poimâine": 2, "today":0, "tomorrow":1, "heute":0, "morgen":1, "aujourd’hui":0, "aujourd'hui":0, "demain":1, "hoy":0, "mañana":1}


def parse_date(text: str, today: date | None = None) -> date | None:
    """Accepta YYYY-MM-DD, DD.MM.YYYY, DD/MM/YYYY, azi/mâine. Gol -> None; invalid -> ValueError."""
    t = text.strip().lower()
    if not t:
        return None
    today = today or date.today()
    if t in _WORDS:
        return today + timedelta(days=_WORDS[t])
    m = re.fullmatch(r"\+(\d{1,3})", t)
    if m:
        return today + timedelta(days=int(m.group(1)))
    for pattern, order in ((r"(\d{4})-(\d{1,2})-(\d{1,2})", "ymd"), (r"(\d{1,2})[./](\d{1,2})[./](\d{4})", "dmy")):
        m = re.fullmatch(pattern, t)
        if m:
            a, b, c = (int(g) for g in m.groups())
            try:
                return date(a, b, c) if order == "ymd" else date(c, b, a)
            except ValueError as exc:
                raise ValueError(tr('ui.formats.data_invalida', text=text)) from exc
    raise ValueError(tr('ui.formats.format_de_data_necunoscut_foloseste_zz_ll_aaaa', text=text))


def format_date(d: date | None) -> str:
    return date_text(d)


def parse_time(text: str) -> time | None:
    t = text.strip()
    if not t:
        return None
    m = re.fullmatch(r"(\d{1,2})[:.](\d{2})", t)
    if not m:
        raise ValueError(tr('ui.formats.ora_invalida_foloseste_hh_mm', text=text))
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:
        raise ValueError(tr('ui.formats.ora_invalida', text=text))
    return time(h, mi)


def parse_duration(text: str) -> int | None:
    """'90', '1h30', '1:30', '2h', '45m', '1,5h' -> minute. Gol -> None."""
    t = text.strip().lower().replace(",", ".")
    if not t:
        return None
    m = re.fullmatch(r"(\d+):(\d{1,2})", t)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    m = re.fullmatch(r"(?:(\d+(?:\.\d+)?)\s*(?:hours?|ore|ora|h))?\s*(?:(\d+)\s*(?:min|m)?)?", t)
    if m and (m.group(1) or m.group(2)):
        if m.group(1) is None:
            return int(m.group(2))
        hours = float(m.group(1))
        return int(round(hours * 60)) + (int(m.group(2)) if m.group(2) else 0)
    if re.fullmatch(r"\d+", t):
        return int(t)
    raise ValueError(tr('ui.formats.durata_invalida_ex_90_1h30_2h', text=text))


def duration_to_text(minutes: int | None) -> str:
    if minutes is None:
        return ""
    h, m = divmod(minutes, 60)
    if h and m:
        return f"{h}h{m:02d}"
    if h:
        return f"{h}h"
    return f"{m}m"


def parse_tags(text: str) -> list[str]:
    return list(dict.fromkeys(t.strip() for t in re.split(r"[,;]", text) if t.strip()))
