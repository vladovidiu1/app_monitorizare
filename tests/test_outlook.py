from __future__ import annotations

import queue
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from focusdesk.domain.models import Kind
from focusdesk.domain.settings import OutlookSettings
from focusdesk.integrations.outlook import (
    AppointmentFields, AppointmentInfo, CalendarInfo, RawEvent, SyncRequest, availability_from_events, execute,
    signature_of,
)
from focusdesk.services.calendar_sync import CalendarSyncService, SyncSummary
from focusdesk.services.sessions import SessionService
from focusdesk.workers.com_worker import ComBlocked, ComTimeout, ComWorker

UTC = timezone.utc
T0 = datetime(2026, 11, 3, 8, 0, tzinfo=UTC)
STORE, FOLDER = "store-1", "folder-1"


class FakeOutlook:
    """Backend in memorie; imita comportamentul relevant (markeri, stergere in Elemente sterse)."""

    def __init__(self) -> None:
        self.items: dict[str, dict] = {}
        self.calls: list[str] = []
        self.thread_names: set[str] = set()
        self.counter = 0
        self.send_called = False
        self.mails: list[dict] = []
        self.calendar_events: list[RawEvent] = []

    def diagnose(self):
        return {"outlook": True}

    def list_calendars(self):
        return [CalendarInfo(STORE, "user@firma.ro", "exchange_primary", FOLDER, "Calendar"),
                CalendarInfo("pst", "Arhiva.pst", "other", "pf", "Calendar")]

    def _info(self, eid: str) -> AppointmentInfo:
        it = self.items[eid]
        return AppointmentInfo(eid, STORE, it["folder"], it["subject"], it["start"], it["end"], it["busy"],
                               it["session_id"], it["workspace_id"])

    def read_events(self, store_id, folder_id, start_utc, end_utc):
        return []

    def read_calendar_events(self, store_id, folder_id, start_utc, end_utc):
        return [event for event in self.calendar_events if event.start < end_utc and event.end > start_utc]

    def find_by_session(self, store_id, folder_id, session_id, workspace_id, around_start, around_end):
        self.calls.append("find")
        for eid, it in self.items.items():
            if (not it["deleted"] and it["session_id"] == session_id and it["workspace_id"] == workspace_id
                    and it["folder"] == folder_id):
                return self._info(eid)
        return None

    def get(self, entry_id, store_id):
        it = self.items.get(entry_id)
        if it is None or it["deleted"]:
            return None
        return self._info(entry_id)

    def create(self, store_id, folder_id, fields: AppointmentFields):
        self.thread_names.add(threading.current_thread().name)
        self.calls.append("create")
        self.counter += 1
        eid = f"E{self.counter}"
        self.items[eid] = dict(folder=folder_id, subject=fields.subject, start=fields.start_utc, end=fields.end_utc,
                               busy=fields.busy_status, session_id=fields.session_id, workspace_id=fields.workspace_id,
                               body=fields.body, reminder=fields.reminder_minutes, deleted=False, attendees=[],
                               online_meeting=False)
        return self._info(eid)

    def update(self, entry_id, store_id, fields):
        self.calls.append("update")
        it = self.items[entry_id]
        it.update(subject=fields.subject, start=fields.start_utc, end=fields.end_utc, body=fields.body)
        return self._info(entry_id)

    def delete(self, entry_id, store_id):
        self.calls.append("delete")
        self.items[entry_id]["deleted"] = True

    def send_mail(self, to, cc, subject, body, *, send):
        self.thread_names.add(threading.current_thread().name)
        self.mails.append(dict(to=to, cc=cc, subject=subject, body=body, send=send))
        return "sent" if send else "displayed"

    # actiuni ale utilizatorului in Outlook
    def user_moves(self, eid, new_start, new_end):
        self.items[eid]["start"], self.items[eid]["end"] = new_start, new_end

    def user_deletes(self, eid):
        self.items[eid]["deleted"] = True


@pytest.fixture
def setup(ws):
    t, = [ws.create_node(Kind.TASK, "Raport lunar", next_action="Pasul 1")]
    ws.settings.outlook = OutlookSettings(enabled=True, calendar_store_id=STORE, calendar_folder_id=FOLDER,
                                          reminder_minutes=10)
    sessions = SessionService(ws)
    start = datetime.now(UTC) + timedelta(days=2)
    s = sessions.create(t.id, start, start + timedelta(hours=1), reserve_calendar=True)
    return ws, t, sessions, s, CalendarSyncService(ws, sessions), FakeOutlook()


def run_all(svc, backend, ids=None):
    summary = SyncSummary()
    planned = svc.prepare(ids)
    for p in planned:
        svc.apply(p, execute(backend, p.request), summary)
    return planned, summary


def test_create_event_is_personal_busy_with_markers(setup):
    ws, t, sessions, s, svc, be = setup
    planned, summary = run_all(svc, be)
    assert summary.created == 1 and len(planned) == 1
    ev = next(iter(be.items.values()))
    assert ev["subject"] == "[FocusDesk] Lucru — Raport lunar"
    assert ev["busy"] == 2 and ev["reminder"] == 10
    assert ev["attendees"] == [] and not ev["online_meeting"] and not be.send_called
    assert ev["session_id"] == s.id and ev["workspace_id"] == ws.id
    assert s.id in ev["body"] and t.id in ev["body"] and "Pasul 1" in ev["body"]
    assert str(ws.root) not in ev["body"]
    saved = ws.repo.sessions.get(s.id)
    assert saved.sync.state == "saved_locally" and saved.sync.entry_id == "E1"
    assert saved.sync.store_id == STORE and saved.sync.calendar_folder_id == FOLDER
    assert saved.sync.last_synced_at is not None and saved.sync.signature
    assert ws.repo.operations.list_all()[0].state == "done"


def test_retry_does_not_duplicate_even_after_crash_between_save_and_json(setup):
    ws, t, sessions, s, svc, be = setup
    planned = svc.prepare()
    execute(be, planned[0].request)  # evenimentul exista in Outlook, dar rezultatul nu s-a scris (crash)
    assert len(be.items) == 1
    # sesiunea locala este tot "pending"; operatia ramasa pending se marcheaza esuata la repornire
    assert svc.recover_interrupted() == 1
    assert ws.repo.sessions.get(s.id).sync.state == "pending"
    planned2, summary = run_all(svc, be)
    assert len(be.items) == 1  # niciun duplicat
    assert ws.repo.sessions.get(s.id).sync.state == "saved_locally"
    # inca o rulare nu mai are nimic de facut
    assert svc.prepare() == []


def test_update_after_local_time_change(setup):
    ws, t, sessions, s, svc, be = setup
    run_all(svc, be)
    new_start = s.start_at + timedelta(hours=3)
    sessions.update(s.id, start=new_start, end=new_start + timedelta(hours=1))
    assert ws.repo.sessions.get(s.id).sync.state == "pending"
    _, summary = run_all(svc, be)
    assert summary.updated == 1
    assert next(iter(be.items.values()))["start"] == new_start
    assert len(be.items) == 1


def test_event_moved_in_outlook_is_a_conflict_not_overwritten(setup):
    ws, t, sessions, s, svc, be = setup
    run_all(svc, be)
    moved = s.start_at + timedelta(days=1)
    be.user_moves("E1", moved, moved + timedelta(hours=1))
    sessions.update(s.id, start=s.start_at + timedelta(hours=1), end=s.start_at + timedelta(hours=2))
    _, summary = run_all(svc, be)
    assert summary.conflicts == 1 and summary.updated == 0
    assert be.items["E1"]["start"] == moved  # nu s-a suprascris
    assert ws.repo.sessions.get(s.id).sync.state == "conflict"
    # un conflict nu se reincearca singur
    assert svc.prepare() == []


def test_conflict_resolution_apply_local_plan(setup):
    ws, t, sessions, s, svc, be = setup
    run_all(svc, be)
    be.user_moves("E1", s.start_at + timedelta(days=1), s.start_at + timedelta(days=1, hours=1))
    sessions.update(s.id, start=s.start_at + timedelta(hours=1), end=s.start_at + timedelta(hours=2))
    run_all(svc, be)
    local = ws.repo.sessions.get(s.id)
    p = svc.request_for_conflict(s.id, "local")
    svc.apply(p, execute(be, p.request))
    assert be.items["E1"]["start"] == local.start_at
    assert ws.repo.sessions.get(s.id).sync.state == "saved_locally"


def test_conflict_resolution_pull_from_outlook(setup):
    ws, t, sessions, s, svc, be = setup
    run_all(svc, be)
    moved = s.start_at + timedelta(days=1)
    be.user_moves("E1", moved, moved + timedelta(hours=2))
    sessions.update(s.id, start=s.start_at + timedelta(hours=1), end=s.start_at + timedelta(hours=2))
    run_all(svc, be)
    p = svc.request_for_conflict(s.id, "pull")
    svc.apply(p, execute(be, p.request))
    got = ws.repo.sessions.get(s.id)
    assert got.start_at == moved and got.end_at == moved + timedelta(hours=2)
    assert got.sync.state == "saved_locally"


def test_conflict_resolution_detach(setup):
    ws, t, sessions, s, svc, be = setup
    run_all(svc, be)
    be.user_moves("E1", s.start_at + timedelta(days=1), s.start_at + timedelta(days=1, hours=1))
    sessions.update(s.id, start=s.start_at + timedelta(hours=1), end=s.start_at + timedelta(hours=2))
    run_all(svc, be)
    svc.detach(s.id)
    got = ws.repo.sessions.get(s.id)
    assert got.sync.state == "detached" and not got.reserve_calendar
    assert svc.prepare() == []
    assert len(be.items) == 1


def test_deleted_in_outlook_is_not_recreated_automatically(setup):
    ws, t, sessions, s, svc, be = setup
    run_all(svc, be)
    be.user_deletes("E1")
    sessions.update(s.id, start=s.start_at + timedelta(hours=1), end=s.start_at + timedelta(hours=2))
    _, summary = run_all(svc, be)
    assert summary.conflicts == 1
    assert be.calls.count("create") == 1  # nu s-a recreat
    assert ws.repo.sessions.get(s.id).sync.state == "conflict"
    # alegere explicita: aplica planul local -> recreare
    p = svc.request_for_conflict(s.id, "local")
    svc.apply(p, execute(be, p.request))
    assert be.calls.count("create") == 2
    assert ws.repo.sessions.get(s.id).sync.state == "saved_locally"


def test_pull_when_deleted_cancels_local_session(setup):
    ws, t, sessions, s, svc, be = setup
    run_all(svc, be)
    be.user_deletes("E1")
    p = svc.request_for_conflict(s.id, "pull")
    svc.apply(p, execute(be, p.request))
    got = ws.repo.sessions.get(s.id)
    assert got.status == "cancelled" and got.sync.state == "detached"


def test_cancel_removes_only_own_event(setup):
    ws, t, sessions, s, svc, be = setup
    run_all(svc, be)
    sessions.cancel(s.id)
    _, summary = run_all(svc, be)
    assert summary.cancelled == 1
    assert be.items["E1"]["deleted"]
    assert ws.repo.sessions.get(s.id).sync.state == "cancelled"


def test_foreign_or_unmarked_events_are_never_touched(setup):
    ws, t, sessions, s, svc, be = setup
    run_all(svc, be)
    # evenimentul din Outlook pierde markerii (ex. copiat de utilizator) sau apartine altui workspace
    be.items["E1"]["workspace_id"] = "alt-workspace"
    sessions.update(s.id, start=s.start_at + timedelta(hours=1), end=s.start_at + timedelta(hours=2))
    _, summary = run_all(svc, be)
    assert summary.failed == 1
    assert "markerii" in ws.repo.sessions.get(s.id).sync.error
    assert be.calls.count("update") == 0 and be.calls.count("delete") == 0
    # eveniment strain fara markeri, cu EntryID cunoscut
    be.items["X"] = dict(folder=FOLDER, subject="Intalnire client", start=T0, end=T0 + timedelta(hours=1), busy=2,
                         session_id=None, workspace_id=None, body="", reminder=0, deleted=False, attendees=["a"],
                         online_meeting=True)
    res = execute(be, SyncRequest(op="cancel", session_id="s-x", workspace_id=ws.id, store_id=STORE, entry_id="X"))
    assert res.state == "failed" and not be.items["X"]["deleted"]


def test_failed_operation_stays_visible_and_is_retried(setup):
    ws, t, sessions, s, svc, be = setup
    planned = svc.prepare()
    svc.apply(planned[0], execute(be, planned[0].request).__class__(s.id, "create", "failed", "RPC indisponibil"))
    assert ws.repo.sessions.get(s.id).sync.state == "failed"
    assert [o.state for o in svc.failed_operations()] == ["failed"]
    _, summary = run_all(svc, be)
    assert summary.created == 1 and len(be.items) == 1


def test_partial_failure_is_reported_not_all_success(ws):
    t = ws.create_node(Kind.TASK, "T")
    ws.settings.outlook = OutlookSettings(enabled=True, calendar_store_id=STORE, calendar_folder_id=FOLDER)
    sessions = SessionService(ws)
    svc = CalendarSyncService(ws, sessions)
    be = FakeOutlook()
    base = datetime.now(UTC) + timedelta(days=2)
    ids = [sessions.create(t.id, base + timedelta(hours=2 * i), base + timedelta(hours=2 * i + 1), reserve_calendar=True).id
           for i in range(3)]
    orig = be.create
    n = {"c": 0}

    def flaky(*a, **k):
        n["c"] += 1
        if n["c"] == 2:
            raise RuntimeError("operatia a fost respinsa")
        return orig(*a, **k)

    be.create = flaky  # type: ignore[assignment]
    _, summary = run_all(svc, be)
    assert summary.created == 2 and summary.failed == 1
    states = sorted(ws.repo.sessions.get(i).sync.state for i in ids)
    assert states == ["failed", "saved_locally", "saved_locally"]


def test_availability_policies_and_all_day_events():
    def ev(h1, h2, status, all_day=False):
        return RawEvent(T0 + timedelta(hours=h1), T0 + timedelta(hours=h2), status, all_day)

    events = [ev(0, 2, "busy"), ev(1, 3, "busy"), ev(4, 5, "tentative"), ev(6, 7, "working_elsewhere"),
              ev(8, 9, "free"), ev(10, 11, "oof")]
    s = OutlookSettings(tentative_policy="busy", working_elsewhere_policy="free")
    av = availability_from_events(events, s, T0 - timedelta(hours=1), T0 + timedelta(hours=24))
    spans = [(b.start - T0, b.end - T0) for b in av.busy]
    assert spans == [(timedelta(0), timedelta(hours=3)), (timedelta(hours=4), timedelta(hours=5)),
                     (timedelta(hours=10), timedelta(hours=11))]
    assert av.verified_scope == "outlook"
    s2 = OutlookSettings(tentative_policy="free", working_elsewhere_policy="busy")
    spans2 = [(b.start - T0, b.end - T0) for b in availability_from_events(
        events, s2, T0 - timedelta(hours=1), T0 + timedelta(hours=24)).busy]
    assert (timedelta(hours=4), timedelta(hours=5)) not in spans2
    assert (timedelta(hours=6), timedelta(hours=7)) in spans2
    # evenimente in afara intervalului sunt taiate/ignorate
    av3 = availability_from_events([ev(-10, 1, "busy")], s, T0, T0 + timedelta(hours=5))
    assert av3.busy[0].start == T0 and av3.busy[0].end == T0 + timedelta(hours=1)


def test_signature_is_stable_across_second_and_tz_representation():
    a = signature_of("x", datetime(2026, 1, 1, 10, 0, 30, tzinfo=UTC), datetime(2026, 1, 1, 11, 0, tzinfo=UTC), 2)
    b = signature_of("x", datetime(2026, 1, 1, 12, 0, 5, tzinfo=timezone(timedelta(hours=2))),
                     datetime(2026, 1, 1, 13, 0, tzinfo=timezone(timedelta(hours=2))), 2)
    assert a == b


# ---------------- ComWorker ----------------

class QueueBridge:
    def __init__(self) -> None:
        self.q: queue.Queue = queue.Queue()

    def post(self, fn):
        self.q.put(fn)

    def schedule(self, ms, fn):
        t = threading.Timer(ms / 1000, lambda: self.q.put(fn))
        t.daemon = True
        t.start()

    def pump(self, timeout=3.0):
        fn = self.q.get(timeout=timeout)
        fn()


def test_com_worker_runs_in_dedicated_thread_with_primitive_results():
    br = QueueBridge()
    be = FakeOutlook()
    w = ComWorker(br, lambda: be, use_com=False)
    out = []
    w.submit(lambda b: (threading.current_thread().name, b.list_calendars()[0].name), out.append, out.append,
             timeout_s=5)
    br.pump()
    assert out[0][0] == "focusdesk-com" and out[0][1] == "Calendar"
    assert threading.current_thread().name != "focusdesk-com"
    w.shutdown()


def test_com_worker_timeout_ignores_late_result_and_blocks_new_calls():
    br = QueueBridge()
    w = ComWorker(br, FakeOutlook, use_com=False)
    results, errors = [], []
    gate = threading.Event()

    def slow(_b):
        gate.wait(5)
        return "tarziu"

    w.submit(slow, results.append, errors.append, timeout_s=0.2)
    br.pump()  # timeout livrat
    assert isinstance(errors[0], ComTimeout) and not results
    assert w.blocked
    errs2 = []
    w.submit(lambda b: 1, results.append, errs2.append, timeout_s=1)
    assert isinstance(errs2[0], ComBlocked)
    gate.set()
    time.sleep(0.3)
    assert not w.blocked
    assert results == []  # rezultatul tardiv nu a fost aplicat
    w.submit(lambda b: "ok", results.append, errors.append, timeout_s=3)
    # coada poate contine timeout-ul vechi (ignorat) inaintea rezultatului nou
    deadline = time.time() + 3
    while not results and time.time() < deadline:
        try:
            br.pump(0.5)
        except queue.Empty:
            pass
    assert results == ["ok"]
    w.shutdown()


def test_com_date_roundtrip_ignores_pywin32_timezone_label():
    from zoneinfo import ZoneInfo

    from focusdesk.integrations.outlook_com import to_com_date, to_local_naive, to_utc

    x = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
    com = to_com_date(x)
    # Ora de perete trimisa lui Outlook este cea locala (ex. 15:00), nu cea UTC.
    assert com.tzinfo is UTC and com.replace(tzinfo=None) == to_local_naive(x)
    labelled = com.replace(tzinfo=ZoneInfo("Europe/London"))  # pywin32 eticheteaza cu "GMT Standard Time"
    assert to_utc(labelled) == x


def test_diagnostic_hint_for_new_outlook():
    from focusdesk.integrations.outlook_com import NEW_OUTLOOK_HINT

    assert "New Outlook" in NEW_OUTLOOK_HINT and ".ics" in NEW_OUTLOOK_HINT
