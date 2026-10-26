from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import pytest
from icalendar import Calendar

from focusdesk.domain.models import Kind, Priority, Status
from focusdesk.domain.session import SessionRecord
from focusdesk.domain.settings import BreakSlot, DaySchedule, Settings
from focusdesk.domain.timeutil import AmbiguousLocalTime, local_to_utc, utc_to_local
from focusdesk.errors import ValidationError
from focusdesk.integrations.calendar import AvailabilityResult, BusyInterval, LocalOnlyProvider
from focusdesk.integrations.ics import IcsItem, IcsExportProvider, build_ics, stable_uid
from focusdesk.services.planner import Planner, PlanRequest, day_work_intervals, minutes_between
from focusdesk.services.planning import PlanningService
from focusdesk.services.recurrence import RecurrenceService
from focusdesk.services.sessions import BlockedByDependencies, OverlapError, SessionService

UTC = timezone.utc
NOW = datetime(2026, 11, 1, 0, 0, tzinfo=UTC)
MONDAY = date(2026, 11, 2)


def settings(**kw) -> Settings:
    return Settings(**kw)


def overlaps(sessions) -> bool:
    ss = sorted(sessions, key=lambda s: s.start)
    return any(a.end > b.start for a, b in zip(ss, ss[1:]))


@pytest.fixture
def nodes_ws(ws):
    return ws


def make_nodes(ws, *specs):
    out = []
    for title, kw in specs:
        out.append(ws.create_node(Kind.TASK, title, **kw))
    return out


def plan(ws, requests, start=MONDAY, end=MONDAY, busy=None, now=NOW, sets: Settings | None = None):
    if sets is not None:
        ws.settings = sets
    svc = PlanningService(ws, SessionService(ws))
    return svc.plan(requests, start, end, AvailabilityResult(busy=busy or []), now=now)


def test_work_intervals_respect_breaks_and_weekends():
    s = settings()
    iv = day_work_intervals(s, MONDAY)
    assert sum(minutes_between(a, b) for a, b in iv) == 8 * 60 + 30 - 30
    assert day_work_intervals(s, date(2026, 11, 7)) == []  # sambata
    s.holidays = [MONDAY]
    assert day_work_intervals(s, MONDAY) == []


def test_planner_simple_no_overlap_and_within_hours(ws):
    t1, t2 = make_nodes(ws, ("A", dict(estimated_minutes=180, remaining_minutes=180)),
                        ("B", dict(estimated_minutes=60, remaining_minutes=60)))
    res = plan(ws, [PlanRequest(t1.id), PlanRequest(t2.id)])
    assert not res.unallocated
    assert res.allocated_minutes(t1.id) == 180 and res.allocated_minutes(t2.id) == 60
    assert not overlaps(res.sessions)
    for p in res.sessions:
        start = utc_to_local(p.start, "Europe/Bucharest")
        end = utc_to_local(p.end, "Europe/Bucharest")
        assert time(9, 0) <= start.time() and end.time() <= time(17, 30)
        assert not (start.time() < time(13, 0) and end.time() > time(12, 30))  # nu in pauza
        assert p.minutes <= 120


def test_planner_gap_between_sessions_and_reserve(ws):
    t, = make_nodes(ws, ("A", dict(estimated_minutes=600, remaining_minutes=600)))
    res = plan(ws, [PlanRequest(t.id)])
    ss = sorted(res.sessions, key=lambda p: p.start)
    for a, b in zip(ss, ss[1:]):
        assert (b.start - a.end) >= timedelta(minutes=10)
    # rezerva de 60 min la sfarsitul zilei ramane libera
    last_end = utc_to_local(ss[-1].end, "Europe/Bucharest")
    assert last_end.time() <= time(16, 30)
    assert res.unallocated and "capacitate insuficientă" in res.unallocated[0].reason
    assert res.unallocated[0].minutes_missing == 600 - res.allocated_minutes(t.id)


def test_planner_unestimated_is_reported_not_invented(ws):
    t, = make_nodes(ws, ("Fara estimare", {}))
    res = plan(ws, [PlanRequest(t.id)])
    assert res.sessions == []
    assert "neestimat" in res.unallocated[0].reason


def test_planner_explicit_minutes_override_for_unestimated(ws):
    t, = make_nodes(ws, ("Fara estimare", {}))
    res = plan(ws, [PlanRequest(t.id, minutes=45)])
    assert res.allocated_minutes(t.id) == 45


def test_planner_blocked_by_unfinished_dependency(ws):
    a, b = make_nodes(ws, ("Dep", dict(estimated_minutes=60)), ("Dependent", dict(estimated_minutes=60)))
    ws.add_dependency(b.id, a.id)
    res = plan(ws, [PlanRequest(b.id)])
    assert res.sessions == []
    assert "blocat" in res.unallocated[0].reason


def test_planner_orders_dependent_after_dependency(ws):
    a, b = make_nodes(ws, ("Dep", dict(estimated_minutes=60, priority=Priority.LOW)),
                      ("Dependent", dict(estimated_minutes=60, priority=Priority.URGENT)))
    ws.add_dependency(b.id, a.id)
    res = plan(ws, [PlanRequest(a.id), PlanRequest(b.id)])
    first_b = min(p.start for p in res.sessions if p.node_id == b.id)
    last_a = max(p.end for p in res.sessions if p.node_id == a.id)
    assert first_b >= last_a + timedelta(minutes=10)


def test_planner_dependency_not_fully_scheduled_blocks_dependent(ws):
    a, b = make_nodes(ws, ("Dep", dict(estimated_minutes=5000)), ("Dependent", dict(estimated_minutes=30)))
    ws.add_dependency(b.id, a.id)
    res = plan(ws, [PlanRequest(a.id), PlanRequest(b.id)])
    reasons = {u.node_id: u.reason for u in res.unallocated}
    assert "blocat" in reasons[b.id]
    assert res.allocated_minutes(b.id) == 0


def test_planner_respects_deadline_and_orders_by_it(ws):
    late, early = make_nodes(
        ws, ("Mai tarziu", dict(estimated_minutes=60, due_date=date(2026, 11, 6))),
        ("Mai devreme", dict(estimated_minutes=60, due_date=MONDAY)))
    res = plan(ws, [PlanRequest(late.id), PlanRequest(early.id)], end=date(2026, 11, 6))
    first = min(res.sessions, key=lambda p: p.start)
    assert first.node_id == early.id
    # termen = luni: nu se programeaza dupa luni
    for p in res.sessions:
        if p.node_id == early.id:
            assert utc_to_local(p.end, "Europe/Bucharest").date() <= MONDAY


def test_planner_deadline_in_past_reported(ws):
    t, = make_nodes(ws, ("Intarziat", dict(estimated_minutes=60, due_date=date(2026, 10, 1))))
    res = plan(ws, [PlanRequest(t.id)])
    assert "termen" in res.unallocated[0].reason


def test_planner_avoids_busy_external_events(ws):
    t, = make_nodes(ws, ("A", dict(estimated_minutes=120)))
    busy = [BusyInterval(datetime(2026, 11, 2, 7, 0, tzinfo=UTC), datetime(2026, 11, 2, 9, 0, tzinfo=UTC), "outlook")]
    res = plan(ws, [PlanRequest(t.id)], busy=busy)
    assert res.sessions[0].start >= datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
    assert not any(p.start < busy[0].end and p.end > busy[0].start for p in res.sessions)
    assert any("doar local" in n for n in plan(ws, [PlanRequest(t.id)]).notes)


def test_planner_avoids_existing_local_sessions(ws):
    t1, t2 = make_nodes(ws, ("A", dict(estimated_minutes=60)), ("B", dict(estimated_minutes=60)))
    svc = SessionService(ws)
    existing = svc.create(t1.id, datetime(2026, 11, 3, 7, 0, tzinfo=UTC), datetime(2026, 11, 3, 8, 0, tzinfo=UTC))
    res = plan(ws, [PlanRequest(t2.id)], start=date(2026, 11, 3), end=date(2026, 11, 3))
    for p in res.sessions:
        assert p.end + timedelta(minutes=10) <= existing.start_at or p.start >= existing.end_at + timedelta(minutes=10)


def test_planner_does_not_double_plan_already_planned_time(ws):
    t, = make_nodes(ws, ("A", dict(estimated_minutes=60)))
    SessionService(ws).create(t.id, datetime(2026, 11, 3, 7, 0, tzinfo=UTC), datetime(2026, 11, 3, 8, 0, tzinfo=UTC))
    res = plan(ws, [PlanRequest(t.id)], start=date(2026, 11, 3), end=date(2026, 11, 4))
    assert res.sessions == []


@pytest.mark.parametrize("day,expected", [(date(2026, 3, 29), 180), (date(2026, 10, 25), 300), (date(2026, 11, 1), 240)])
def test_dst_changes_work_capacity(day, expected):
    s = settings(work_hours={str(day.weekday()): DaySchedule(enabled=True, start="01:00", end="05:00")},
                 breaks=[], daily_reserve_minutes=0)
    assert sum(minutes_between(a, b) for a, b in day_work_intervals(s, day)) == expected


def test_planner_dst_week_no_overlap(ws):
    sets = settings(daily_reserve_minutes=0)
    t, = make_nodes(ws, ("Mult", dict(estimated_minutes=1500)))
    res = plan(ws, [PlanRequest(t.id)], start=date(2026, 3, 23), end=date(2026, 3, 31),
               now=datetime(2026, 3, 20, tzinfo=UTC), sets=sets)
    assert not overlaps(res.sessions)
    assert res.allocated_minutes(t.id) == 1500


def test_local_time_conversion_rejects_nonexistent_and_ambiguous():
    with pytest.raises(AmbiguousLocalTime):
        local_to_utc(date(2026, 3, 29), time(3, 30), "Europe/Bucharest")  # nu exista
    with pytest.raises(AmbiguousLocalTime):
        local_to_utc(date(2026, 10, 25), time(3, 30), "Europe/Bucharest")  # ambigua
    assert local_to_utc(date(2026, 10, 25), time(3, 30), "Europe/Bucharest", ambiguous="first") == datetime(
        2026, 10, 25, 0, 30, tzinfo=UTC)
    assert local_to_utc(date(2026, 11, 2), time(9, 0), "Europe/Bucharest") == datetime(2026, 11, 2, 7, 0, tzinfo=UTC)


def test_date_only_due_stays_a_date(ws):
    from focusdesk.services.queries import Queries

    t, = make_nodes(ws, ("T", dict(due_date=date(2026, 11, 2))))
    raw = ws.get(t.id).model_dump(mode="json")
    assert raw["due_date"] == "2026-11-02" and raw["due_at"] is None
    assert Queries(ws).due_day(ws.get(t.id)) == date(2026, 11, 2)


def test_apply_revalidates_and_creates_sessions(ws):
    a, b = make_nodes(ws, ("A", dict(estimated_minutes=60)), ("B", dict(estimated_minutes=60)))
    svc = PlanningService(ws, SessionService(ws))
    res = svc.plan([PlanRequest(a.id), PlanRequest(b.id)], MONDAY, MONDAY, now=NOW)
    ws.update_node(b.id, status=Status.DONE)  # s-a schimbat intre generare si aplicare
    out = svc.apply(res.sessions)
    assert {s.node_id for s in out.created} == {a.id}
    assert out.failed and "finalizat" in out.failed[0][1]
    again = svc.apply([p for p in res.sessions if p.node_id == a.id])
    assert again.failed and "suprapune" in again.failed[0][1]


# ---------------- sessions ----------------

def test_session_overlap_and_dependency_rules(ws):
    a, b = make_nodes(ws, ("A", {}), ("B", {}))
    ss = SessionService(ws)
    start = datetime.now(UTC) + timedelta(days=1)
    s1 = ss.create(a.id, start, start + timedelta(hours=1))
    with pytest.raises(OverlapError):
        ss.create(b.id, start + timedelta(minutes=30), start + timedelta(hours=2))
    ss.create(b.id, start + timedelta(minutes=30), start + timedelta(hours=2), allow_overlap=True)
    ws.add_dependency(b.id, a.id)
    later = start + timedelta(days=2)
    with pytest.raises(BlockedByDependencies):
        ss.create(b.id, later, later + timedelta(hours=1))
    ss.create(b.id, later, later + timedelta(hours=1), override_dependencies=True)
    with pytest.raises(ValidationError):
        ss.create(a.id, start - timedelta(days=3), start - timedelta(days=3) + timedelta(hours=1))
    ss.cancel(s1.id)
    assert ws.repo.sessions.get(s1.id).status == "cancelled"


def test_missed_sessions_marked(ws):
    t, = make_nodes(ws, ("A", {}))
    start = datetime.now(UTC) - timedelta(hours=3)
    s = SessionRecord(node_id=t.id, start_at=start, end_at=start + timedelta(hours=1))
    ws.repo.sessions.save(s)
    assert SessionService(ws).mark_missed() == 1
    assert ws.repo.sessions.get(s.id).status == "missed"


def test_calendar_description_has_no_local_paths_by_default(ws):
    t, = make_nodes(ws, ("A", dict(next_action="pasul 1")))
    ws.set_description(t.id, "detalii secrete " * 5)
    ss = SessionService(ws)
    start = datetime.now(UTC) + timedelta(days=1)
    s = ss.create(t.id, start, start + timedelta(hours=1))
    d = ss.description_for(ws.get(t.id), s)
    assert t.id in d and s.id in d and "pasul 1" in d
    assert str(ws.root) not in d and "detalii secrete" not in d
    assert "detalii secrete" in ss.description_for(ws.get(t.id), s, include_details=True)
    assert ss.title_for(ws.get(t.id)) == "[FocusDesk] Lucru — A"


def test_local_provider_reports_scope_honestly():
    p = LocalOnlyProvider()
    av = p.get_availability(NOW, NOW + timedelta(days=1))
    assert av.verified_scope == "local" and "doar local" in av.note
    assert not p.capabilities.read_availability and not p.capabilities.create


# ---------------- ICS ----------------

def _session(ws, node, start, dur=60):
    return SessionRecord(node_id=node.id, workspace_id=ws.id, start_at=start, end_at=start + timedelta(minutes=dur))


def test_ics_is_parseable_utc_stable_uid_and_opaque(ws):
    t, = make_nodes(ws, ("Titlu cu virgulă, punct și virgulă; și ăîșț", {}))
    start = datetime(2026, 11, 3, 7, 0, tzinfo=UTC)
    s = _session(ws, t, start)
    long_desc = "Linia 1\nLinia 2, cu virgulă; și ; " + "x" * 200
    data = build_ics([IcsItem(s, "[FocusDesk] Lucru — " + t.title, long_desc, sequence=2)], ws.id, now=NOW)
    assert b"\r\n" in data
    for line in data.split(b"\r\n"):
        assert len(line) <= 75 + 1 or line.startswith(b" ")  # line folding
    cal = Calendar.from_ical(data)
    ev = list(cal.walk("VEVENT"))[0]
    assert str(ev["uid"]) == stable_uid(ws.id, s.id)
    assert ev["dtstart"].dt == start and ev["dtstart"].dt.utcoffset() == timedelta(0)
    assert ev["dtend"].dt == start + timedelta(hours=1)
    assert str(ev["transp"]) == "OPAQUE"
    assert str(ev["X-MICROSOFT-CDO-BUSYSTATUS"]) == "BUSY"
    assert int(ev["sequence"]) == 2
    assert str(ev["summary"]).endswith("și ăîșț")
    assert str(ev["description"]) == long_desc
    assert stable_uid(ws.id, s.id) == stable_uid(ws.id, s.id)
    assert stable_uid(ws.id, s.id) != stable_uid("alt-ws", s.id)


def test_ics_cancel_variant_and_export_label(ws, tmp_path):
    t, = make_nodes(ws, ("A", {}))
    s = _session(ws, t, datetime(2026, 11, 3, 7, 0, tzinfo=UTC))
    data = build_ics([IcsItem(s, "x", "", sequence=3, cancelled=True)], ws.id)
    ev = list(Calendar.from_ical(data).walk("VEVENT"))[0]
    assert str(ev["status"]) == "CANCELLED" and int(ev["sequence"]) == 3
    out = IcsExportProvider.export_to_file([IcsItem(s, "x", "")], ws.id, tmp_path / "s.ics")
    assert out.exists()
    assert not IcsExportProvider.capabilities.auto_sync and not IcsExportProvider.capabilities.create
    from focusdesk.integrations.ics import EXPORT_STATE_TEXT

    assert "necesită import" in EXPORT_STATE_TEXT


# ---------------- recurrence ----------------

def test_recurrence_generates_without_duplicates(ws):
    svc = RecurrenceService(ws)
    start = date(2026, 11, 2)
    t = svc.create(title="Raport zilnic", frequency="workdays", start_date=start)
    n1 = svc.generate(t.id, date(2026, 11, 3))
    assert n1 is not None and n1.occurrence_date == date(2026, 11, 3) and n1.recurrence_template_id == t.id
    assert svc.generate(t.id, date(2026, 11, 3)) is None
    assert len([n for n in ws.nodes.values() if n.recurrence_template_id == t.id]) == 1
    with pytest.raises(ValidationError):
        svc.generate(t.id, date(2026, 11, 7))  # sambata
    # sablonul reincarcat de pe disc pastreaza cheia
    ws.reload()
    assert RecurrenceService(ws).generate(t.id, date(2026, 11, 3)) is None


def test_recurrence_missed_instances_are_listed_not_generated(ws):
    svc = RecurrenceService(ws)
    t = svc.create(title="Zilnic", frequency="daily", start_date=date(2026, 9, 1))
    today = date(2026, 11, 3)
    today_pending, missed = svc.pending(t, today)
    assert today_pending
    assert len(missed) == 60  # limitat la 60 de zile, nu sute de task-uri
    assert not [n for n in ws.nodes.values() if n.recurrence_template_id]
    created, missed_map = svc.generate_today_all(today)
    assert len(created) == 1 and created[0].occurrence_date == today
    assert len(missed_map[t.id]) == 60
    svc.skip(t.id, missed[:10])
    _, missed2 = svc.pending(ws.repo.recurrences.get(t.id), today)
    assert len(missed2) == 50
    svc.generate(t.id, missed[20])
    _, missed3 = svc.pending(ws.repo.recurrences.get(t.id), today)
    assert len(missed3) == 49


def test_weekly_recurrence_rule(ws):
    svc = RecurrenceService(ws)
    t = svc.create(title="Marti si joi", frequency="weekly", weekdays=[1, 3], start_date=date(2026, 11, 1))
    assert t.occurs_on(date(2026, 11, 3)) and t.occurs_on(date(2026, 11, 5))
    assert not t.occurs_on(date(2026, 11, 4))
    with pytest.raises(ValidationError):
        svc.create(title="x", frequency="weekly", weekdays=[], start_date=date(2026, 11, 1))
