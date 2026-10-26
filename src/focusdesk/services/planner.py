"""Planificator determinist: intervale libere din program, fara suprapuneri, respecta dependente si termene.

Calculeaza determinist intervalele, capacitatea, pauzele si dependentele.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from ..domain.models import CLOSED_STATUSES, PRIORITY_ORDER, Kind, Node, Priority
from ..domain.session import SessionRecord
from ..domain.settings import Settings
from ..integrations.calendar import BusyInterval

Interval = tuple[datetime, datetime]
UTC = timezone.utc


@dataclass
class PlanRequest:
    node_id: str
    minutes: int | None = None  # None -> se foloseste estimarea ramasa a task-ului; lipsa = neestimat


@dataclass
class ProposedSession:
    node_id: str
    start: datetime
    end: datetime

    @property
    def minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)


@dataclass
class Unallocated:
    node_id: str
    minutes_missing: int
    reason: str


@dataclass
class PlanResult:
    sessions: list[ProposedSession] = field(default_factory=list)
    unallocated: list[Unallocated] = field(default_factory=list)
    free_minutes_total: int = 0
    notes: list[str] = field(default_factory=list)

    def allocated_minutes(self, node_id: str) -> int:
        return sum(s.minutes for s in self.sessions if s.node_id == node_id)


# ---- interval arithmetic ----------------------------------------------

def _floor_min(d: datetime) -> datetime:
    return d.replace(second=0, microsecond=0)


def _ceil_min(d: datetime) -> datetime:
    f = _floor_min(d)
    return f if f == d else f + timedelta(minutes=1)


def subtract(intervals: list[Interval], cut: Interval) -> list[Interval]:
    cs, ce = cut
    out: list[Interval] = []
    for a, b in intervals:
        if ce <= a or cs >= b:
            out.append((a, b))
            continue
        if a < cs:
            out.append((a, cs))
        if ce < b:
            out.append((ce, b))
    return out


def minutes_between(a: datetime, b: datetime) -> int:
    return int((b - a).total_seconds() // 60)


def day_work_intervals(settings: Settings, day: date) -> list[Interval]:
    """Program de lucru al unei zile minus pauze, in UTC (ora locala -> UTC pe baza fusului, DST corect)."""
    tz = ZoneInfo(settings.timezone)
    sched = settings.work_hours.get(str(day.weekday()))
    if sched is None or not sched.enabled or day in settings.holidays:
        return []
    start = datetime.combine(day, sched.start_time(), tzinfo=tz).astimezone(UTC)
    end = datetime.combine(day, sched.end_time(), tzinfo=tz).astimezone(UTC)
    if end <= start:
        return []
    intervals: list[Interval] = [(start, end)]
    for br in settings.breaks:
        bs = datetime.combine(day, br.start_time(), tzinfo=tz).astimezone(UTC)
        be = datetime.combine(day, br.end_time(), tzinfo=tz).astimezone(UTC)
        if be > bs:
            intervals = subtract(intervals, (bs, be))
    return intervals


def _end_of_local_day(day: date, tz: ZoneInfo) -> datetime:
    return datetime.combine(day + timedelta(days=1), time(0, 0), tzinfo=tz).astimezone(UTC)


class Planner:
    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self.tz = ZoneInfo(settings.timezone)

    # ---- free time --------------------------------------------------
    def free_intervals(self, start_day: date, end_day: date, busy: list[BusyInterval],
                       local_sessions: list[SessionRecord], now: datetime) -> list[Interval]:
        gap = timedelta(minutes=self.s.gap_minutes)
        out: list[Interval] = []
        day = start_day
        while day <= end_day:
            intervals = day_work_intervals(self.s, day)
            for b in busy:
                if b.source != "local":
                    intervals = subtract(intervals, (_floor_min(b.start), _ceil_min(b.end)))
            for sess in local_sessions:
                if sess.status in ("planned", "active"):
                    intervals = subtract(intervals, (_floor_min(sess.start_at) - gap, _ceil_min(sess.end_at) + gap))
            # nu planificam in trecut
            floor = _ceil_min(now)
            intervals = [(max(a, floor), b) for a, b in intervals if b > floor]
            intervals = self._apply_reserve(intervals)
            out.extend(intervals)
            day += timedelta(days=1)
        out.sort()
        return [(a, b) for a, b in out if b > a]

    def _apply_reserve(self, intervals: list[Interval]) -> list[Interval]:
        """Pastreaza ultimele `daily_reserve_minutes` ale zilei libere pentru urgente."""
        remaining = self.s.daily_reserve_minutes
        trimmed = list(intervals)
        i = len(trimmed) - 1
        while remaining > 0 and i >= 0:
            a, b = trimmed[i]
            length = minutes_between(a, b)
            if length <= remaining:
                remaining -= length
                trimmed.pop(i)
            else:
                trimmed[i] = (a, b - timedelta(minutes=remaining))
                remaining = 0
            i -= 1
        return trimmed

    # ---- planning ---------------------------------------------------
    def plan(self, requests: list[PlanRequest], nodes: dict[str, Node], start_day: date, end_day: date, *,
             busy: list[BusyInterval] | None = None, local_sessions: list[SessionRecord] | None = None,
             now: datetime, unfinished_deps: dict[str, list[str]] | None = None,
             already_planned_minutes: dict[str, int] | None = None) -> PlanResult:
        busy = busy or []
        local_sessions = local_sessions or []
        unfinished_deps = unfinished_deps or {}
        already = already_planned_minutes or {}
        result = PlanResult()
        free = self.free_intervals(start_day, end_day, busy, local_sessions, now)
        result.free_minutes_total = sum(minutes_between(a, b) for a, b in free)
        if not free:
            result.notes.append("Nu există timp liber în program pentru perioada aleasă.")

        selected = {r.node_id: r for r in requests}
        order = self._ordered(requests, nodes, unfinished_deps)
        allocated_end: dict[str, datetime | None] = {}
        fully_done: dict[str, bool] = {}
        period_start = datetime.combine(start_day, time(0, 0), tzinfo=self.tz).astimezone(UTC)
        period_end = _end_of_local_day(end_day, self.tz)

        for nid in order:
            node = nodes[nid]
            req = selected[nid]
            allocated_end[nid] = None
            fully_done[nid] = False
            if node.kind != Kind.TASK or node.status in CLOSED_STATUSES:
                result.unallocated.append(Unallocated(nid, 0, "finalizat/anulat sau nu este task"))
                continue
            need = req.minutes if req.minutes is not None else (
                node.remaining_minutes if node.remaining_minutes is not None else node.estimated_minutes)
            if need is None:
                result.unallocated.append(Unallocated(nid, 0, "neestimat — setează o estimare"))
                continue
            need = max(0, need - already.get(nid, 0))
            if need == 0:
                fully_done[nid] = True
                result.notes.append(f"„{node.title}”: timpul estimat este deja acoperit de sesiuni planificate.")
                continue
            blockers = [d for d in unfinished_deps.get(nid, [])]
            external_blockers = [d for d in blockers if d not in selected]
            if external_blockers:
                names = ", ".join(nodes[d].title if d in nodes else d[:8] for d in external_blockers)
                result.unallocated.append(Unallocated(nid, need, f"blocat de dependențe nefinalizate: {names}"))
                continue
            unmet = [d for d in blockers if not fully_done.get(d)]
            if unmet:
                names = ", ".join(nodes[d].title for d in unmet if d in nodes)
                result.unallocated.append(Unallocated(nid, need, f"blocat: dependența nu este programată complet ({names})"))
                continue
            earliest = period_start
            for d in blockers:
                end_d = allocated_end.get(d)
                if end_d and end_d > earliest:
                    earliest = end_d + timedelta(minutes=self.s.gap_minutes)
            latest = self._deadline(node, period_end)
            if latest <= max(earliest, _ceil_min(now)):
                result.unallocated.append(Unallocated(nid, need, "termen depășit sau înainte de perioada de planificare"))
                continue
            chunks, remaining = self._allocate(free, need, earliest, latest)
            for a, b in chunks:
                result.sessions.append(ProposedSession(nid, a, b))
            if chunks:
                allocated_end[nid] = max(b for _, b in chunks)
            if remaining > 0:
                reason = "capacitate insuficientă"
                if latest < period_end:
                    reason += " înainte de termen"
                result.unallocated.append(Unallocated(nid, remaining, f"{reason} (lipsesc {remaining} min)"))
            else:
                fully_done[nid] = True
        result.sessions.sort(key=lambda p: p.start)
        return result

    def _deadline(self, node: Node, period_end: datetime) -> datetime:
        if node.due_at is not None:
            return min(period_end, node.due_at.astimezone(UTC))
        if node.due_date is not None:
            return min(period_end, _end_of_local_day(node.due_date, self.tz))
        return period_end

    def _ordered(self, requests: list[PlanRequest], nodes: dict[str, Node],
                 deps: dict[str, list[str]]) -> list[str]:
        ids = [r.node_id for r in requests if r.node_id in nodes]
        far = datetime.max.replace(tzinfo=UTC)

        def key(nid: str):
            n = nodes[nid]
            if n.due_at is not None:
                dl = n.due_at.astimezone(UTC)
            elif n.due_date is not None:
                dl = _end_of_local_day(n.due_date, self.tz)
            else:
                dl = far
            return (dl, PRIORITY_ORDER.get(n.priority or Priority.NORMAL, 2), n.title.lower(), nid)

        remaining = set(ids)
        order: list[str] = []
        while remaining:
            ready = [i for i in remaining if not any(d in remaining for d in deps.get(i, []))]
            if not ready:  # ciclu (nu ar trebui sa existe): rupem determinist
                ready = list(remaining)
            nxt = min(ready, key=key)
            order.append(nxt)
            remaining.discard(nxt)
        return order

    def _allocate(self, free: list[Interval], need: int, earliest: datetime, latest: datetime
                  ) -> tuple[list[Interval], int]:
        s = self.s
        chunks: list[Interval] = []
        remaining = need
        gap = timedelta(minutes=s.gap_minutes)
        guard = 0
        while remaining > 0 and guard < 5000:
            guard += 1
            placed = False
            for idx, (a, b) in enumerate(free):
                start = max(a, earliest)
                stop = min(b, latest)
                avail = minutes_between(start, stop)
                if avail <= 0:
                    continue
                need_min = min(s.min_session_minutes, remaining)
                chunk = min(s.max_session_minutes, remaining, avail)
                left = remaining - chunk
                if 0 < left < s.min_session_minutes and chunk - (s.min_session_minutes - left) >= s.min_session_minutes:
                    chunk -= s.min_session_minutes - left
                if chunk < need_min:
                    continue
                end = start + timedelta(minutes=chunk)
                chunks.append((start, end))
                remaining -= chunk
                new_parts: list[Interval] = []
                if start > a:
                    new_parts.append((a, start))
                if end + gap < b:
                    new_parts.append((end + gap, b))
                free[idx:idx + 1] = new_parts
                placed = True
                break
            if not placed:
                break
        return chunks, remaining
