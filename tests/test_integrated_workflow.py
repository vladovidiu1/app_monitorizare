"""A daily workflow across all stages, using only temporary local data and fake clocks/calendar."""
import csv
import io
import shutil
import time
from dataclasses import replace
from datetime import timedelta

from focusdesk.domain.common import utcnow,new_id
from focusdesk.domain.models import Kind,Status,SourceWorkspace
from focusdesk.integrations.meetings import CalendarMeeting,MeetingBatch
from focusdesk.services.activity import activity_model,csv_text
from focusdesk.services.backup import create_backup,restore_backup_to_folder
from focusdesk.services.files import FileService
from focusdesk.services.workspace import Workspace


def test_daily_workflow_all_stages_and_reconstruction(ui,tmp_path,monkeypatch):
    import focusdesk.ui.app as ui_module
    import focusdesk.services.timer as timer_module
    ws=ui.ws;root=ws.root
    settings=ws.settings.model_copy(deep=True);settings.checkpoints.on_session_end=False;ws.update_settings(settings)
    project=ws.create_node(Kind.PROJECT,'Proiect integrat')
    source=ws.create_node(Kind.TASK,'Script pentru raportul zilnic',project.id,
        source_workspace=SourceWorkspace(mode='managed',path='files/code'))
    code=ws.node_dir(source.id)/'files'/'code';code.mkdir(parents=True);(code/'report.py').write_text("print('șț')\n")
    ui.select_node(source.id,reveal=True);ui.root.deiconify();ui.root.update()
    tab=ui.inspector.tab_by_title('Detalii')
    guide=tab.editor.open_guide();guide.goal.insert('1.0','Raport corect, păstrat offline')
    guide.steps[0].text.insert('1.0','Validează intrarea');guide.steps[1].text.insert('1.0','Generează rezultatul')
    assert guide.apply();ui.root.update();description=tab.editor.get()
    assert tab.is_dirty();ui.save_current();assert ws.get_description(source.id)==description
    assert ui.open_task_space(source.id);ui.root.update()
    assert ui.task_space.editor.get()==description
    tab.expand_description();expanded=tab.expanded;ui.root.update()
    expanded.editor.replace('end-1c','end-1c','\nCiornă temporară')
    assert tab.editor.get()==ui.task_space.editor.get()
    expanded.cancel();ui.root.update()
    assert tab.editor.get()==description and not tab.is_dirty()
    ui.task_space.back();ui.root.update()

    now=utcnow();reservation=ui.sessions.create(source.id,now+timedelta(hours=1),now+timedelta(hours=1,minutes=30))
    assert ui.timer.state is None
    class Clock:
        seconds=1000.
        wall=now
        def __call__(self):return self.seconds
        def advance(self,seconds):
            for _ in range(seconds//5):
                self.seconds+=5;self.wall+=timedelta(seconds=5);ui.timer.tick()
    clock=Clock();ui.timer._mono=clock;monkeypatch.setattr(timer_module,'utcnow',lambda:clock.wall)
    ui.timer.start(source.id,reservation.id);ui.timer.start(source.id,reservation.id)
    assert ws.repo.sessions.ids()=={reservation.id}
    clock.advance(60);ui.timer.pause();ui.timer.pause()
    other=ws.create_node(Kind.TASK,'Altă activitate',project.id)
    monkeypatch.setattr(ui_module,'ask_choice',lambda *a,**k:'cancel')
    ui.start_session(other.id);assert ui.timer.node_id==source.id and not ui.timer.running
    monkeypatch.setattr(ui_module,'ask_choice',lambda *a,**k:'finish')
    monkeypatch.setattr(ui_module.StopSessionDialog,'run',lambda self:(self.destroy(),dict(summary='Validare terminată'))[1])
    monkeypatch.setattr(ui,'_ask_session_open_options',lambda node:None)
    ui.start_session(other.id)
    assert ui.timer.node_id==other.id and ui.timer.running
    assert ws.repo.sessions.get(reservation.id).actual_seconds==60
    clock.advance(10);ui.timer.pause();ui.timer._persist()
    sid=ui.timer.state.session_id
    # Abrupt shutdown: no UI handover/stop, timer file is intentionally left for recovery.
    ws.close();ui.ws=None;ui.timer=None
    ui._post_open_checks=lambda:None
    assert ui.open_workspace(root)
    ws=ui.ws;ui.timer._mono=clock
    assert ui.timer.recovered and ui.timer.seconds==10
    clock.seconds+=86400;clock.wall+=timedelta(days=1)
    ui.timer.continue_recovered();assert ui.timer.seconds==10
    ui.timer.stop();assert len(ws.repo.sessions.ids())==2

    ui.sessions.correct_time(reservation.id,45,reason='Corecție verificată')
    data=activity_model(ws).report()
    assert data.worked==55 and data.planned==1800 and data.live==0
    assert sum(d['worked'] for d in data.days.values())==55
    assert sum(p['worked'] for p in data.projects.values())==55
    exported=list(csv.DictReader(io.StringIO(csv_text(data).lstrip('\ufeff')),delimiter=';'))
    assert sum(int(r['Lucrat înregistrat (secunde)']) for r in exported if r['Tip']=='Sesiune')==55
    assert ws.repo.sessions.get(sid).actual_seconds==10

    ws.update_node(source.id,status=Status.DONE)
    assert source.id not in {n.id for n in ui.q.tasks(open_only=True)}
    assert source.id in {n.id for n in ui.q.search('Script pentru raportul')}
    ui.quick_tasks('done');ui.root.update();assert ui.tasklist.tv.exists(source.id)
    ws.reopen_task(source.id,reason='Continuarea cerinței inițiale')
    assert source.id in {n.id for n in ui.q.tasks(open_only=True)}
    ws.update_node(source.id,status=Status.DONE)
    followup=ws.create_followup(source.id,title='Update nou după trei luni',description='Cerință independentă',request_id=new_id(),code_access='shared')
    assert ws.get(source.id).status==Status.DONE and followup.status==Status.TODO
    assert followup.parent_id==project.id and followup.continuation_of==source.id
    assert ws.repo.sessions.worked_for_node(followup.id)==0
    assert FileService(ws).effective_source(followup.id).path==code
    assert FileService(ws).checkpoint_owner(followup.id)==followup.id
    assert len([e for e in ws.list_history(source.id) if e.type=='status_changed' and e.data.get('to')=='done'])==2

    svc=ws.meetings;svc.configure('fake-store','fake-calendar','Calendar de test')
    event=CalendarMeeting(uid='weekly',occurrence_key=now.isoformat(),title='Revizie raport',start=now,end=now+timedelta(hours=1))
    bounds=(now-timedelta(days=14),now+timedelta(days=60))
    svc.import_batch('fake-store','fake-calendar',MeetingBatch([event]),*bounds)
    svc.import_batch('fake-store','fake-calendar',MeetingBatch([event]),*bounds)
    mid=svc.store.summaries()[0]['id'];assert ui.open_meeting(mid);ui.root.update()
    page=ui.calendar_page.meetings;page.notes.insert('1.0','Decizie: un update explicit.\nContext liber, care rămâne în notițe.');ui.root.update()
    deadline=time.monotonic()+3
    while page.dirty and time.monotonic()<deadline:ui.root.update();time.sleep(.01)
    assert not page.dirty and 'Salvat' in page.save_state.cget('text')
    text=svc.store.notes(mid)
    svc.import_batch('fake-store','fake-calendar',MeetingBatch([replace(event,title='Revizie reprogramată',start=now+timedelta(hours=2),end=now+timedelta(hours=3))]),*bounds)
    assert len(svc.store.summaries())==1 and svc.store.notes(mid)==text
    action=svc.save_action(mid,text='Verificare suplimentară',responsible='Colega',state='todo')
    request=new_id();save_local=svc.store.save_local
    monkeypatch.setattr(svc.store,'save_local',lambda *a:(_ for _ in ()).throw(OSError('întrerupere la legare')))
    import pytest
    with pytest.raises(OSError):svc.create_node(mid,request_id=request,title='Task din acțiune',action_id=action.id,description=action.text)
    count=len(ws.nodes);monkeypatch.setattr(svc.store,'save_local',save_local)
    node=svc.create_node(mid,request_id=request,title='Task din acțiune',action_id=action.id,description=action.text)
    assert len(ws.nodes)==count and node.meeting_ids==[mid]
    assert svc.create_node(mid,request_id=request,title='Task din acțiune',action_id=action.id,description=action.text).id==node.id
    page.render_actions();page.actions.selection_set(action.id);page.open_link();ui.root.update()
    assert ui.selected_id==node.id
    ui.inspector.meeting_links.menu.invoke(0);ui.root.update();assert page.mid==mid
    assert ui.timer.state is None and activity_model(ws).report().worked==55

    page.back();ws.close();ui.ws=None;ui.timer=None
    for folder in list(root.rglob('.cache')):
        if folder.is_dir():shutil.rmtree(folder)
    if (root/'_system/cache').exists():shutil.rmtree(root/'_system/cache')
    (root/'_system/index.json').unlink(missing_ok=True)
    assert ui.open_workspace(root);ws=ui.ws
    assert ws.get_description(source.id)==description and ws.meetings.store.notes(mid)==text
    assert activity_model(ws).report().worked==55
    assert ws.get(followup.id).continuation_of==source.id
    backup=create_backup(ws,full=True)
    restored=restore_backup_to_folder(backup.path,tmp_path/'restored-integrated')
    w=Workspace.open(restored)
    try:
        assert activity_model(w).report().worked==55 and len(w.repo.sessions.ids())==2
        assert w.get_description(source.id)==description
        assert w.nodes[followup.id].continuation_of==source.id
        assert (FileService(w).effective_source(followup.id).path/'report.py').read_text()=="print('șț')\n"
        assert w.meetings.store.notes(mid)==text
        assert w.meetings.store.local(mid).actions[0].node_id==node.id
        assert w.nodes[node.id].meeting_ids==[mid]
        assert not w.meetings.integrity(include_notes=True)
    finally:w.close()


def test_hidden_task_selection_event_does_not_restore_inspector_over_activity(ui):
    nid=ui.selected_id
    ui.show_view('tasks');ui.root.update()
    ui.tasklist.tv.selection_set(nid) # Tk delivers this after the route switch below
    ui.show_view('activity');ui.root.update()
    assert ui.current_view=='activity' and ui.selected_id is None
    assert str(ui.inspector) not in ui.paned.panes()


def test_meeting_footer_accessible_at_minimum_window(ui):
    ui.root.deiconify();ui.root.geometry('1100x700')
    ui.show_view('calendar');page=ui.calendar_page.meetings
    ui.calendar_page.nb.select(page);ui.root.update()
    assert page.more.winfo_ismapped()
    assert page.more.winfo_rooty()+page.more.winfo_height()<=ui.root.winfo_rooty()+ui.root.winfo_height()


def test_workspace_lock_is_retained_until_local_worker_finishes(ui):
    import threading
    started=threading.Event();finish=threading.Event();original=ui.ws;callbacks=[]
    def work(token):started.set();finish.wait(3);return 'saved'
    def completed(value):
        assert not ui._release_current(), 'UI metadata callback still owns the workspace'
        callbacks.append(value)
    job=ui.run_job(work,completed,name='local-write')
    try:
        assert started.wait(1)
        assert not ui._release_current() and ui.ws is original
        assert 'Workspace păstrat' in ui.status.message.cget('text')
        finish.set();deadline=time.monotonic()+3
        while not job.done and time.monotonic()<deadline:ui.root.update();time.sleep(.01)
        assert job.done and callbacks==['saved']
        assert ui._release_current() and ui.ws is None
    finally:finish.set()


def test_workspace_handover_rechecks_checkpoint_started_by_session_stop(ui,monkeypatch):
    import threading
    import focusdesk.ui.app as module
    finish=threading.Event();original=ui.ws
    ui.timer.start(ui.selected_id)
    def stop():
        ui.timer.stop()
        ui.run_job(lambda token:finish.wait(3),name='checkpoint-at-stop')
        return True
    monkeypatch.setattr(ui,'stop_session',stop)
    monkeypatch.setattr(module,'ask_choice',lambda *a,**k:'stop')
    try:
        assert not ui._release_current() and ui.ws is original and ui.timer.state is None
        finish.set();deadline=time.monotonic()+3
        while ui._pending_workspace_jobs() and time.monotonic()<deadline:ui.root.update();time.sleep(.01)
        assert ui._release_current()
    finally:finish.set()
