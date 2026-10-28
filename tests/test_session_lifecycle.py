"""Temporary-workspace checks for the unique timer, recovery and explicit corrections."""
from datetime import timedelta
import json
import pytest
from focusdesk.domain.common import utcnow
from focusdesk.domain.models import Kind, Status
from focusdesk.domain.session import SessionRecord
from focusdesk.domain.labels import session_status_text
from focusdesk.errors import ValidationError, ReadOnlyError, ExternalModificationError
from focusdesk.services.timer import TimerService
from focusdesk.services.sessions import SessionService
from focusdesk.services.workspace import Workspace
from focusdesk.services.activity import activity_model, LiveWork

class Clock:
    t=1000.
    def __call__(self):return self.t


def start(ws):
    clock=Clock();node=ws.create_node(Kind.TASK,'Script');timer=TimerService(ws,mono=clock)
    session=timer.start(node.id)
    return timer,session,clock


def test_repeat_start_pause_resume_stop_are_idempotent(ws):
    timer,s,clock=start(ws)
    assert timer.start(s.node_id).id==s.id
    clock.t+=5;timer.tick();timer.pause();timer.pause()
    clock.t+=500;timer.resume();timer.resume();clock.t+=3
    saved=timer.stop(summary='Rezumat')
    assert saved.actual_seconds==8
    assert timer.stop().id==saved.id
    assert len(ws.repo.sessions.ids())==1
    assert len(ws.list_notes(s.node_id))==1


@pytest.mark.parametrize('paused',[False,True])
def test_other_task_never_silently_replaces_current(ws,paused):
    timer,s,clock=start(ws)
    if paused:timer.pause()
    other=ws.create_node(Kind.TASK,'Altul')
    with pytest.raises(ValidationError):timer.start(other.id)
    assert timer.node_id==s.node_id
    assert ws.repo.sessions.ids()=={s.id}


def test_planned_record_reused_and_cannot_be_restarted(ws):
    n=ws.create_node(Kind.TASK,'Rezervat');now=utcnow()+timedelta(hours=1)
    s=SessionService(ws).create(n.id,now,now+timedelta(hours=1))
    timer=TimerService(ws)
    assert timer.state is None
    assert 'Rezervare' in session_status_text(s,timer)
    assert timer.start(n.id,s.id).id==s.id
    timer.pause();assert 'În pauză' in session_status_text(ws.repo.sessions.get(s.id),timer)
    timer.stop()
    with pytest.raises(ValidationError):timer.start(n.id,s.id)
    assert len(ws.repo.sessions.ids())==1


def test_cancel_reservation_cannot_cancel_current_work(ws):
    timer,s,_=start(ws)
    with pytest.raises(ValidationError):SessionService(ws).cancel(s.id)
    assert timer.active


def test_failed_timer_intent_does_not_create_session(ws,monkeypatch):
    n=ws.create_node(Kind.TASK,'N');timer=TimerService(ws)
    monkeypatch.setattr(timer,'_persist',lambda:(_ for _ in ()).throw(OSError('disk')))
    with pytest.raises(OSError):timer.start(n.id)
    assert timer.state is None and not ws.repo.sessions.ids()


def test_failed_start_session_write_recovers_same_id(ws,monkeypatch):
    n=ws.create_node(Kind.TASK,'N');timer=TimerService(ws)
    save=ws.repo.sessions.save
    monkeypatch.setattr(ws.repo.sessions,'save',lambda s:(_ for _ in ()).throw(OSError('disk')))
    with pytest.raises(OSError):timer.start(n.id)
    sid=timer.state.session_id
    assert timer.recovered and timer.path.exists()
    monkeypatch.setattr(ws.repo.sessions,'save',save)
    root=ws.root;ws.close();w=Workspace.open(root)
    try:
        recovered=TimerService(w)
        assert recovered.recovered and w.repo.sessions.ids()=={sid}
        recovered.continue_recovered()
        assert recovered.running and recovered.state.session_id==sid and recovered.seconds==0
        recovered.stop()
    finally:w.close()


@pytest.mark.parametrize('stage',['session','node','note','history','clear'])
def test_interrupted_finish_retry_or_restart_no_duplicate(ws,monkeypatch,stage):
    timer,s,clock=start(ws);clock.t+=7;timer.tick()
    if stage=='session':target,attr=ws.repo.sessions,'save'
    elif stage=='node':target,attr=ws,'update_node'
    elif stage=='note':target,attr=ws.repo.notes_store(s.node_id),'save'
    elif stage=='history':target,attr=ws.repo.history,'save'
    else:target,attr=timer,'_clear_file'
    original=getattr(target,attr)
    monkeypatch.setattr(target,attr,lambda *a,**k:(_ for _ in ()).throw(OSError('interrupted')))
    with pytest.raises(OSError):timer.stop(summary='Un singur rezumat',next_action='Pas următor')
    assert timer.state.finalization and timer.path.exists()
    monkeypatch.setattr(target,attr,original)
    root=ws.root;ws.close();w=Workspace.open(root)
    try:
        recovered=TimerService(w)
        assert recovered.recovered and recovered.state.finalization
        out=recovered.stop()
        assert out.id==s.id and out.actual_seconds==7
        assert len(w.list_notes(s.node_id))==1
        events=[e for e in w.list_history(s.node_id) if e.type=='session_stopped']
        assert len(events)==1 and not recovered.path.exists()
        assert w.get(s.node_id).next_action=='Pas următor'
    finally:w.close()


def test_restart_offline_gap_not_work_and_pause_survives(ws):
    timer,s,clock=start(ws);clock.t+=8;timer.tick();timer.pause()
    root=ws.root;ws.close();w=Workspace.open(root)
    try:
        t=TimerService(w,mono=clock);clock.t+=86400
        assert t.recovered and not t.active and t.state.state=='paused'
        t.tick();assert t.seconds==8
        t.continue_recovered();t.tick();assert t.seconds==8
    finally:w.close()


def test_sleep_gap_and_day_boundary_not_counted(ws):
    timer,s,clock=start(ws);clock.t+=3;timer.tick();clock.t+=86400;timer.tick()
    assert timer.seconds==3 and not timer.running and timer.pending_gap==86400
    timer.resume();assert timer.seconds==3


def test_timer_external_conflict_and_failed_pause_not_success(ws,monkeypatch):
    timer,s,clock=start(ws)
    raw=timer.path.read_bytes();timer.path.write_bytes(raw+b' ')
    with pytest.raises(ExternalModificationError):timer.pause()
    assert timer.running


def test_two_services_cannot_start_two_timers(ws):
    first=TimerService(ws);second=TimerService(ws)
    a=ws.create_node(Kind.TASK,'A');b=ws.create_node(Kind.TASK,'B')
    first.start(a.id)
    with pytest.raises(ValidationError):second.start(b.id)
    assert len(ws.repo.sessions.ids())==1


def test_second_instance_readonly_cannot_change_timer(ws):
    timer,s,_=start(ws);raw=timer.path.read_bytes()
    other=Workspace.open(ws.root,read_only=True)
    try:
        t=TimerService(other)
        for op in (lambda:t.start(s.node_id),t.pause,t.resume,t.stop,t.discard,t.continue_recovered):
            with pytest.raises(ReadOnlyError):op()
        assert timer.path.read_bytes()==raw
    finally:other.close()


def completed(ws):
    n=ws.create_node(Kind.TASK,'T');now=utcnow()
    s=SessionRecord(node_id=n.id,start_at=now-timedelta(hours=2),end_at=now-timedelta(hours=1),status='done',
        started_actual_at=now-timedelta(hours=2),stopped_actual_at=now-timedelta(hours=1),actual_seconds=1200)
    ws.repo.sessions.save(s);return s


def test_correction_audit_aggregates_and_no_live_double_count(ws):
    s=completed(ws);svc=SessionService(ws)
    before=activity_model(ws).report();assert before.worked==1200
    out=svc.correct_time(s.id,1800,reason='Am omis pauza')
    assert out.corrections[0]['before']['seconds']==1200
    assert out.corrections[0]['after']['seconds']==1800
    assert out.corrections[0]['reason']=='Am omis pauza'
    assert ws.repo.sessions.worked_for_node(s.node_id)==1800
    report=activity_model(ws).report(live=LiveWork(s.id,s.node_id,1800,s.started_actual_at))
    assert report.worked==1800 and report.live==0
    assert sum(x['worked'] for x in report.days.values())==1800
    assert sum(x['worked'] for x in report.projects.values())==1800
    svc.correct_time(s.id,1800)
    assert len(ws.repo.sessions.get(s.id).corrections)==1


@pytest.mark.parametrize('seconds',[-1,1.5,True,4000])
def test_invalid_corrections_preserve_authoritative_data(ws,seconds):
    s=completed(ws);original=ws.repo.sessions.get(s.id)
    with pytest.raises(ValidationError):SessionService(ws).correct_time(s.id,seconds)
    assert ws.repo.sessions.get(s.id)==original


def test_diagnostics_do_not_repair_orphans_or_overlaps(ws):
    s=completed(ws);other=s.model_copy(deep=True)
    from focusdesk.domain.common import new_id
    other.id=new_id();ws.repo.sessions.save(other)
    orphan=other.model_copy(deep=True);orphan.id=new_id();orphan.status='active';ws.repo.sessions.save(orphan)
    svc=SessionService(ws);result=svc.diagnostics()
    assert result['orphan_active']==[orphan.id]
    assert len(result['overlapping_work'])==1
    assert ws.repo.sessions.get(orphan.id).status=='active'
    t=TimerService(ws);t.recover_session(orphan.id)
    assert t.recovered and t.seconds==orphan.actual_seconds
    assert not svc.diagnostics(orphan.id)['orphan_active']


@pytest.mark.parametrize('paused',[False,True])
def test_cancel_finish_restores_original_pause_state(ui,monkeypatch,paused):
    from focusdesk.ui import app as module
    ui.timer.start(ui.selected_id)
    if paused:ui.timer.pause()
    monkeypatch.setattr(module.StopSessionDialog,'run',lambda self:(self.destroy(),None)[1])
    assert not ui.stop_session()
    assert ui.timer.running is not paused


@pytest.mark.parametrize('paused',[False,True])
def test_switch_task_cancel_or_save_failure_never_starts_new(ui,monkeypatch,paused):
    from focusdesk.ui import app as module
    first=ui.selected_id;other=ui.ws.create_node(Kind.TASK,'Alt task')
    ui.timer.start(first)
    if paused:ui.timer.pause()
    monkeypatch.setattr(ui,'confirm_leave',lambda:True)
    monkeypatch.setattr(module,'ask_choice',lambda *a,**k:'finish')
    monkeypatch.setattr(module.StopSessionDialog,'run',lambda self:(self.destroy(),None)[1])
    ui.start_session(other.id)
    assert ui.timer.node_id==first and len(ui.ws.repo.sessions.ids())==1
    monkeypatch.setattr(module.StopSessionDialog,'run',lambda self:(self.destroy(),{})[1])
    save=ui.ws.repo.sessions.save
    monkeypatch.setattr(ui.ws.repo.sessions,'save',lambda *a,**k:(_ for _ in ()).throw(OSError('full disk')))
    monkeypatch.setattr(module,'show_error',lambda *a,**k:None)
    ui.start_session(other.id)
    assert ui.timer.node_id==first and ui.timer.state.finalization
    monkeypatch.setattr(ui.ws.repo.sessions,'save',save)
    ui.timer.stop()


def test_repeat_modal_start_and_indicator_focus_mode(ui,monkeypatch):
    nid=ui.selected_id
    monkeypatch.setattr(ui,'confirm_leave',lambda:True)
    def options(node):
        ui.start_session(nid) # event arriving while start dialog is open
        return None
    monkeypatch.setattr(ui,'_ask_session_open_options',options)
    ui.start_session(nid);ui.start_session(nid)
    assert len(ui.ws.repo.sessions.ids())==1
    ui.root.deiconify();ui.open_task_space(nid);ui.root.update()
    ui.task_space.toggle_focus();ui.timer_indicator.update_state();ui.root.update()
    assert ui.timer_indicator.winfo_ismapped()
    assert 'În lucru' in ui.timer_indicator.label.cget('text')


def test_workspace_switch_cancel_keeps_current(ui,monkeypatch):
    from focusdesk.ui import app as module
    ui.timer.start(ui.selected_id)
    original=ui.ws
    monkeypatch.setattr(ui,'confirm_leave',lambda:True)
    monkeypatch.setattr(module,'ask_choice',lambda *a,**k:'cancel')
    assert not ui._release_current()
    assert ui.ws is original and ui.timer.active


def test_start_reserved_save_failure_recovers_original_reservation(ws,monkeypatch):
    n=ws.create_node(Kind.TASK,'Programat');now=utcnow()+timedelta(hours=1)
    s=SessionService(ws).create(n.id,now,now+timedelta(hours=1));timer=TimerService(ws)
    original=ws.repo.sessions.save
    monkeypatch.setattr(ws.repo.sessions,'save',lambda *a:(_ for _ in ()).throw(OSError('disk')))
    with pytest.raises(OSError):timer.start(n.id,s.id)
    monkeypatch.setattr(ws.repo.sessions,'save',original)
    root=ws.root;ws.close();w=Workspace.open(root)
    try:
        recovered=TimerService(w)
        assert recovered.recovered and w.repo.sessions.get(s.id).status=='active'
        assert w.repo.sessions.ids()=={s.id}
        recovered.continue_recovered();recovered.stop()
    finally:w.close()


def test_live_saved_export_and_reservation_totals_remain_distinct(ws):
    import csv,io
    from focusdesk.services.activity import csv_text
    timer,s,clock=start(ws);clock.t+=10;timer.tick()
    report=activity_model(ws).report(live=LiveWork(s.id,s.node_id,10,s.started_actual_at))
    assert report.planned==0 and report.worked==0 and report.live==10
    timer.stop()
    report=activity_model(ws).report(live=LiveWork(s.id,s.node_id,10,s.started_actual_at))
    assert report.planned==0 and report.worked==10 and report.live==0
    rows=list(csv.DictReader(io.StringIO(csv_text(report).lstrip('\ufeff')),delimiter=';'))
    assert sum(int(r['Lucrat înregistrat (secunde)']) for r in rows if r['Tip']=='Sesiune')==10
    assert sum(int(r['Live nesalvat (secunde)']) for r in rows if r['Tip']=='Sesiune')==0


def test_explicit_recovery_end_and_offline_discard_keeps_heartbeat(ws):
    timer,s,clock=start(ws);clock.t+=4;timer.tick();timer.pause()
    root=ws.root;ws.close();w=Workspace.open(root)
    try:
        recovered=TimerService(w)
        # A real saved heartbeat end (not now) is preserved.
        end=recovered.state.heartbeat_at
        out=recovered.finalize_recovered(recovered.seconds,stopped_at=end)
        assert out.stopped_actual_at==end
        assert out.actual_seconds<=4
    finally:w.close()


def test_dst_and_midnight_corrections_follow_actual_start_day(ws):
    from datetime import datetime,timezone,date
    from focusdesk.services.activity import ActivityFilters
    from focusdesk.ui.session_ui import parse_local_stamp
    from focusdesk.domain.timeutil import AmbiguousLocalTime
    with pytest.raises(AmbiguousLocalTime):parse_local_stamp('2025-10-26T03:30:00','Europe/Bucharest')
    with pytest.raises(AmbiguousLocalTime):parse_local_stamp('2025-03-30T03:30:00','Europe/Bucharest')
    a=parse_local_stamp('2025-10-26T03:30:00+03:00','Europe/Bucharest')
    b=parse_local_stamp('2025-10-26T03:30:00+02:00','Europe/Bucharest')
    n=ws.create_node(Kind.TASK,'DST')
    s=SessionRecord(node_id=n.id,start_at=a,end_at=b,started_actual_at=a,stopped_actual_at=b,status='done',actual_seconds=1800)
    ws.repo.sessions.save(s);SessionService(ws).correct_time(s.id,3600)
    assert activity_model(ws).report(ActivityFilters(date(2025,10,26),date(2025,10,26))).worked==3600
    assert activity_model(ws).report(ActivityFilters(date(2025,10,27),date(2025,10,27))).worked==0
    start=datetime(2025,10,27,21,30,tzinfo=timezone.utc);end=start+timedelta(hours=1)
    midnight=s.model_copy(deep=True)
    from focusdesk.domain.common import new_id
    midnight.id=new_id();midnight.set_interval(start,end);midnight.started_actual_at=start;midnight.stopped_actual_at=end
    midnight.actual_seconds=1200;ws.repo.sessions.save(midnight)
    SessionService(ws).correct_time(midnight.id,1800)
    assert activity_model(ws).report(ActivityFilters(date(2025,10,27),date(2025,10,27))).worked==1800
    assert activity_model(ws).report(ActivityFilters(date(2025,10,28),date(2025,10,28))).worked==0


def test_workspace_handoff_explicitly_saves_paused_timer(ui,monkeypatch):
    from focusdesk.ui import app as module
    nid=ui.selected_id;ui.timer.start(nid);root=ui.ws.root
    monkeypatch.setattr(ui,'confirm_leave',lambda:True)
    monkeypatch.setattr(module,'ask_choice',lambda *a,**k:'keep')
    assert ui._release_current()
    assert ui.ws is None and ui.timer is None
    saved=json.loads((root/'_system'/'timer.json').read_text())
    assert saved['state']=='paused' and saved['node_id']==nid
    assert ui.open_workspace(root)
    assert ui.timer.recovered
    ui.timer.discard()


def test_second_readonly_instance_can_close_without_touching_timer(ui,monkeypatch):
    from focusdesk.ui import app as module
    original=ui.ws;ui.timer.start(ui.selected_id);timerfile=ui.timer.path;raw=timerfile.read_bytes()
    # Same UI release path with a readonly workspace must never stop/clear its timer.
    original.repo.read_only=True
    monkeypatch.setattr(ui,'confirm_leave',lambda:True)
    monkeypatch.setattr(module,'ask_choice',lambda *a,**k:pytest.fail('readonly must not prompt a mutation'))
    assert ui._release_current() and timerfile.read_bytes()==raw


def test_other_task_start_button_uses_switch_flow(ui,monkeypatch):
    from focusdesk.ui.common import SessionButton
    first=ui.selected_id;other=ui.ws.create_node(Kind.TASK,'Alt task')
    ui.timer.start(first);ui.timer.pause()
    button=SessionButton(ui.root,ui,lambda:other.id);button.update_state()
    assert not button.instate(['disabled']) and button._mode=='start'
    called=[];monkeypatch.setattr(ui,'start_session',lambda nid:called.append(nid))
    button.invoke();assert called==[other.id]
    button.destroy();ui.session_buttons.remove(button)


def test_retry_failed_start_without_restart_recovers_draft(ws,monkeypatch):
    n=ws.create_node(Kind.TASK,'N');timer=TimerService(ws)
    save=ws.repo.sessions.save
    monkeypatch.setattr(ws.repo.sessions,'save',lambda s:(_ for _ in ()).throw(OSError('disk')))
    with pytest.raises(OSError):timer.start(n.id)
    sid=timer.state.session_id
    monkeypatch.setattr(ws.repo.sessions,'save',save)
    timer.continue_recovered()
    assert timer.running and ws.repo.sessions.get(sid).status=='active'
    timer.stop();assert ws.repo.sessions.ids()=={sid}


def test_chosen_continue_or_cancel_preserves_other_timer(ui,monkeypatch):
    from focusdesk.ui import app as module
    first=ui.selected_id;other=ui.ws.create_node(Kind.TASK,'Alt task')
    ui.timer.start(first);ui.timer.pause()
    monkeypatch.setattr(ui,'confirm_leave',lambda:True)
    monkeypatch.setattr(module,'ask_choice',lambda *a,**k:'cancel')
    ui.start_session(other.id);assert not ui.timer.running and ui.timer.node_id==first
    monkeypatch.setattr(module,'ask_choice',lambda *a,**k:'continue')
    ui.start_session(other.id);assert ui.timer.running and ui.timer.node_id==first


def test_successful_switch_finishes_with_summary_then_starts_other(ui,monkeypatch):
    from focusdesk.ui import app as module
    first=ui.selected_id;other=ui.ws.create_node(Kind.TASK,'Actualizare nouă')
    old=ui.timer.start(first)
    monkeypatch.setattr(ui,'confirm_leave',lambda:True)
    monkeypatch.setattr(module,'ask_choice',lambda *a,**k:'finish')
    monkeypatch.setattr(module.StopSessionDialog,'run',lambda self:(self.destroy(),dict(summary='Progres salvat'))[1])
    monkeypatch.setattr(ui,'_ask_session_open_options',lambda n:None)
    ui.start_session(other.id)
    assert ui.timer.node_id==other.id and ui.timer.running
    assert ui.ws.repo.sessions.get(old.id).status=='done'
    assert [n.text for n in ui.ws.list_notes(first)]==['Progres salvat']
    assert len(ui.ws.repo.sessions.select(statuses={'active'}))==1


def test_failed_correction_does_not_change_values_or_audit(ws,monkeypatch):
    s=completed(ws);original=ws.repo.sessions.get(s.id)
    monkeypatch.setattr(ws.repo.sessions,'save',lambda *a:(_ for _ in ()).throw(OSError('disk')))
    with pytest.raises(OSError):SessionService(ws).correct_time(s.id,1800,reason='Test')
    assert ws.repo.sessions.get(s.id)==original


def test_recovery_stop_does_not_overwrite_external_time_edit(ws,monkeypatch):
    timer,s,clock=start(ws)
    original=timer._clear_file
    monkeypatch.setattr(timer,'_clear_file',lambda:(_ for _ in ()).throw(OSError('disk')))
    with pytest.raises(OSError):timer.stop()
    monkeypatch.setattr(timer,'_clear_file',original)
    saved=ws.repo.sessions.get(s.id);saved.actual_seconds=100;ws.repo.sessions.save(saved)
    with pytest.raises(ExternalModificationError):timer.stop()
    assert ws.repo.sessions.get(s.id).actual_seconds==100 and timer.state


def test_pause_button_double_click_does_not_immediately_resume(ui,monkeypatch):
    from types import SimpleNamespace
    import focusdesk.ui.app as module
    gesture_time=[100.0]
    monkeypatch.setattr(module,'time',SimpleNamespace(monotonic=lambda:gesture_time[0]))
    ui.timer.start(ui.selected_id)
    ui.toggle_pause();ui.toggle_pause()
    assert not ui.timer.running
    gesture_time[0]+=1
    ui.toggle_pause();assert ui.timer.running


def test_corrupt_timer_is_reported_and_never_overwritten(ws):
    path=ws.repo.system_dir/'timer.json';path.write_text('{invalid',encoding='utf-8')
    timer=TimerService(ws);n=ws.create_node(Kind.TASK,'T')
    assert timer.recovery_error and timer.state is None
    with pytest.raises(ValidationError):timer.start(n.id)
    assert path.read_text()=='{invalid'


def test_correction_same_instants_in_other_timezone_is_noop(ws):
    from zoneinfo import ZoneInfo
    s=completed(ws);zone=ZoneInfo('Europe/Bucharest')
    out=SessionService(ws).correct_time(s.id,s.actual_seconds,
        started_at=s.started_actual_at.astimezone(zone),stopped_at=s.stopped_actual_at.astimezone(zone))
    assert not out.corrections
    assert ws.repo.sessions.get(s.id)==s


def test_stale_correction_dialog_does_not_overwrite_external_change(ws):
    s=completed(ws);stale=s.model_copy(deep=True)
    updated=s.model_copy(deep=True);updated.summary='Modificare externă';ws.repo.sessions.save(updated)
    with pytest.raises(ExternalModificationError):
        SessionService(ws).correct_time(s.id,1800,expected=stale)
    assert ws.repo.sessions.get(s.id)==updated
