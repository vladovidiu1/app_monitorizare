"""Meeting imports and local notes use disposable workspaces and a read-only fake backend."""
from datetime import datetime,timedelta,date,timezone
from dataclasses import replace
from pathlib import Path
from uuid import UUID,uuid5
import json
import pytest
from focusdesk.domain.common import utcnow,new_id
from focusdesk.domain.models import Kind,Status
from focusdesk.domain.meeting import MeetingSource
from focusdesk.integrations.meetings import CalendarMeeting,MeetingBatch
from focusdesk.services.workspace import Workspace
from focusdesk.services.activity import activity_model
from focusdesk.services.backup import create_backup,restore_backup_to_folder
from focusdesk.errors import ValidationError,ReadOnlyError,ExternalModificationError,NotFoundError

NOW=datetime(2026,10,28,12,tzinfo=timezone.utc)
FIRST=NOW-timedelta(days=14);LAST=NOW+timedelta(days=60)

@pytest.fixture
def meetings(ws):
    ws.meetings.configure('store','calendar','Calendar de test')
    return ws.meetings


def event(uid='event-1',**changes):
    e=CalendarMeeting(uid=uid,start=NOW,end=NOW+timedelta(hours=1),title='Ședință proiect',entry_id='entry',location='Sala 2',organizer='Ana')
    return replace(e,**changes)


def imported(svc,e=None):
    svc.import_batch('store','calendar',MeetingBatch([e or event()]),FIRST,LAST)
    return svc.store.summaries()[0]['id']


def test_import_repeat_change_title_time_preserves_local_id_notes_and_actions(meetings):
    mid=imported(meetings)
    meetings.save_notes(mid,'Decizie\n    indentare și diacritice')
    a=meetings.save_action(mid,text='Actualizare script',responsible='Alt coleg')
    moved=event(title='Titlu modificat',start=NOW+timedelta(hours=2),end=NOW+timedelta(hours=3),entry_id='new-entry')
    for _ in range(2):meetings.import_batch('store','calendar',MeetingBatch([moved]),FIRST,LAST)
    assert [r['id'] for r in meetings.store.summaries()]==[mid]
    assert meetings.store.source(mid).title=='Titlu modificat'
    assert meetings.store.notes(mid)=='Decizie\n    indentare și diacritice'
    assert meetings.store.local(mid).actions[0]==a
    assert not meetings.ws.nodes and not meetings.ws.repo.sessions.ids()


def test_occurrences_and_moved_exception_have_stable_original_slot(meetings):
    a=event(occurrence_key='2026-10-28T12:00:00+00:00')
    b=event(occurrence_key='2026-10-29T12:00:00+00:00',start=NOW+timedelta(days=1),end=NOW+timedelta(days=1,hours=1))
    meetings.import_batch('store','calendar',MeetingBatch([a,b]),FIRST,LAST)
    ids={s.occurrence_key:s.id for s in (meetings.store.source(r['id']) for r in meetings.store.summaries())}
    moved=replace(a,start=a.start+timedelta(hours=3),end=a.end+timedelta(hours=3),entry_id='exception-entry')
    meetings.import_batch('store','calendar',MeetingBatch([moved,b]),FIRST,LAST)
    assert len(meetings.store.summaries())==2
    assert meetings.store.source(ids[a.occurrence_key]).start_at==moved.start
    assert ids[a.occurrence_key]!=ids[b.occurrence_key]


def test_cancel_partial_absence_and_failure_never_delete_notes(meetings):
    mid=imported(meetings);meetings.save_notes(mid,'Notițe permanente')
    meetings.import_batch('store','calendar',MeetingBatch([],complete=False,warnings=['parțial']),FIRST,LAST)
    assert meetings.store.source(mid).state=='present'
    meetings.record_import(error='COM timeout')
    assert meetings.store.notes(mid)=='Notițe permanente'
    meetings.import_batch('store','calendar',MeetingBatch([]),FIRST,LAST)
    assert meetings.store.source(mid).state=='not_seen'
    meetings.import_batch('store','calendar',MeetingBatch([event(cancelled=True)]),FIRST,LAST)
    assert meetings.store.source(mid).state=='cancelled'
    assert meetings.store.notes(mid)=='Notițe permanente'


def test_focusdesk_marker_excluded_but_same_title_personal_event_allowed(meetings):
    meetings.import_batch('store','calendar',MeetingBatch([event('own',session_id=new_id()),event('personal',title='[FocusDesk] Lucru — Script')]),FIRST,LAST)
    rows=meetings.store.summaries();assert len(rows)==1
    assert meetings.store.source(rows[0]['id']).event_uid=='personal'


def test_source_change_rejects_delayed_import(meetings):
    meetings.configure('store','other','Alt calendar')
    with pytest.raises(ValidationError):meetings.import_batch('store','calendar',MeetingBatch([event()]),FIRST,LAST)
    assert not meetings.store.summaries()


def test_all_day_dst_and_unrelated_window_not_marked_absent(meetings):
    e=event(all_day=True,start=datetime(2026,10,24,21,tzinfo=timezone.utc),end=datetime(2026,10,25,22,tzinfo=timezone.utc),timezone='GTB Standard Time')
    mid=imported(meetings,e);source=meetings.store.source(mid)
    assert source.all_day and (source.end_at-source.start_at).total_seconds()==25*3600
    meetings.import_batch('store','calendar',MeetingBatch([]),NOW+timedelta(days=30),LAST)
    assert meetings.store.source(mid).state=='present'


@pytest.mark.parametrize('kind',[Kind.TASK,Kind.PROJECT])
def test_action_conversion_independent_and_bidirectional_without_work(meetings,kind):
    mid=imported(meetings);meetings.save_notes(mid,'Tot textul original rămâne aici')
    action=meetings.save_action(mid,text='Investigare',responsible='Colega',state='todo',due_date=date(2026,11,2))
    request=new_id();params=dict(request_id=request,title='Cerință confirmată',description='Numai fragmentul ales',kind=kind,action_id=action.id)
    node=meetings.create_node(mid,**params)
    assert node.meeting_ids==[mid] and node.status==Status.TODO and node.estimated_minutes is None
    assert meetings.ws.get_description(node.id)=='Numai fragmentul ales'
    assert meetings.store.local(mid).actions[0].node_id==node.id
    assert meetings.store.local(mid).actions[0].state=='converted'
    assert meetings.create_node(mid,**params).id==node.id
    assert meetings.create_node(mid,**dict(params,request_id=new_id())).id==node.id
    assert meetings.list(mode='all',node_id=node.id)[1]==1
    assert meetings.store.notes(mid)=='Tot textul original rămâne aici'
    assert not meetings.ws.repo.sessions.ids() and activity_model(meetings.ws).report().worked==0


def test_new_requirement_uses_existing_relation_and_shared_code(meetings,tmp_path):
    from focusdesk.domain.models import SourceWorkspace
    from focusdesk.services.files import FileService
    code=tmp_path/'code';code.mkdir();(code/'script.py').write_text('print(1)')
    source=meetings.ws.create_node(Kind.TASK,'Script existent',source_workspace=SourceWorkspace(mode='external',path=str(code)))
    meetings.ws.update_node(source.id,status=Status.DONE)
    mid=imported(meetings);action=meetings.save_action(mid,text='Update nou')
    request=new_id();params=dict(request_id=request,title='Update după ședință',description='Fragment',action_id=action.id,followup_source=source.id,code_access='shared')
    node=meetings.create_node(mid,**params)
    assert node.continuation_of==source.id and node.meeting_ids==[mid]
    assert meetings.ws.get(source.id).status==Status.DONE
    assert FileService(meetings.ws).effective_source(node.id).path==code
    assert meetings.create_node(mid,**params).id==node.id
    assert len(meetings.ws.nodes)==2 and not meetings.ws.repo.sessions.ids()


@pytest.mark.parametrize('stage',['node','history','link','receipt'])
def test_interruption_recovery_without_duplicate_node_or_action(meetings,monkeypatch,stage):
    mid=imported(meetings);action=meetings.save_action(mid,text='Acțiune')
    request=new_id();params=dict(request_id=request,title='Task din întâlnire',action_id=action.id)
    repo=meetings.ws.repo
    if stage=='node':obj,attr=repo,'create_node'
    elif stage=='history':obj,attr=repo.history,'save'
    elif stage=='link':obj,attr=meetings.store,'save_local'
    else:obj,attr=repo.operations,'save'
    original=getattr(obj,attr)
    def fail(*args,**kwargs):
        if stage=='receipt' and not (args[0].type=='meeting_convert' and args[0].state=='done'):return original(*args,**kwargs)
        raise OSError('întrerupere')
    monkeypatch.setattr(obj,attr,fail)
    with pytest.raises(OSError):meetings.create_node(mid,**params)
    monkeypatch.setattr(obj,attr,original)
    root=meetings.ws.root;meetings.ws.close();w=Workspace.open(root)
    try:
        assert len(w.nodes)==1
        node=next(iter(w.nodes.values()));assert node.meeting_ids==[mid]
        assert w.meetings.store.local(mid).actions[0].node_id==node.id
        assert w.meetings.create_node(mid,**params).id==node.id
        assert len(w.nodes)==1
        assert w.repo.operations.get(request).state=='done'
    finally:w.close()


def test_existing_link_idempotent_recovery_and_trash_reference(meetings,monkeypatch):
    mid=imported(meetings);n=meetings.ws.create_node(Kind.TASK,'Task')
    save=meetings.store.save_local
    monkeypatch.setattr(meetings.store,'save_local',lambda *a:(_ for _ in ()).throw(OSError('disk')))
    with pytest.raises(OSError):meetings.link(mid,n.id)
    monkeypatch.setattr(meetings.store,'save_local',save)
    assert meetings.recover()
    meetings.link(mid,n.id);assert meetings.ws.get(n.id).meeting_ids==[mid]
    assert meetings.store.local(mid).linked_node_ids==[n.id]


def test_action_edit_uses_validation_not_auto_personal_task(meetings):
    mid=imported(meetings)
    a=meetings.save_action(mid,text='De discutat',responsible='Altă persoană')
    a=meetings.save_action(mid,text='Închis fără task',state='closed',action_id=a.id)
    assert a.state=='closed' and not meetings.ws.nodes
    with pytest.raises(Exception):meetings.save_action(mid,text='   ')
    assert meetings.store.summaries()[0]['unconverted']==0


def test_note_conflict_and_failed_write_preserve_cache_and_original(meetings,monkeypatch):
    mid=imported(meetings);meetings.save_notes(mid,'Original')
    assert meetings.store.notes(mid)=='Original'
    path=meetings.store.path(mid,'notes.md');path.write_text('Extern',encoding='utf-8')
    with pytest.raises(ExternalModificationError):meetings.save_notes(mid,'Ciornă')
    assert path.read_text()=='Extern'
    assert meetings.store.notes(mid)=='Extern'
    from focusdesk.storage import meetings as module
    write=module.atomic_write_text
    monkeypatch.setattr(module,'atomic_write_text',lambda *a,**k:(_ for _ in ()).throw(OSError('disk')))
    with pytest.raises(OSError):meetings.save_notes(mid,'Nesalvat')
    assert path.read_text()=='Extern'
    monkeypatch.setattr(module,'atomic_write_text',write)
    meetings.save_notes(mid,'Reîncercat');assert path.read_text()=='Reîncercat'


def test_readonly_offline_manual_and_backup_restore(meetings,tmp_path):
    mid=imported(meetings);meetings.save_notes(mid,'Notițe importante')
    a=meetings.save_action(mid,text='Task');node=meetings.create_node(mid,request_id=new_id(),title='Task',action_id=a.id)
    backup=create_backup(meetings.ws,full=False)
    restored=restore_backup_to_folder(backup.path,tmp_path/'restore');w=Workspace.open(restored)
    try:
        assert w.meetings.store.notes(mid)=='Notițe importante'
        assert w.nodes[node.id].meeting_ids==[mid]
        assert w.meetings.store.local(mid).actions[0].node_id==node.id
    finally:w.close()
    readonly=Workspace.open(meetings.ws.root,read_only=True)
    try:
        svc=readonly.meetings
        assert svc.store.notes(mid)=='Notițe importante'
        for fn in [lambda:svc.save_notes(mid,'Nu'),lambda:svc.manual(title='Nu',start=NOW,end=NOW+timedelta(hours=1)),lambda:svc.configure('x','y','z'),lambda:svc.create_node(mid,request_id=new_id(),title='Nu')]:
            with pytest.raises(ReadOnlyError):fn()
    finally:readonly.close()


def test_large_history_index_no_markdown_reads_and_global_filter_before_page(meetings,monkeypatch):
    from focusdesk.storage.meetings import MeetingStore
    for i in range(180):
        source=MeetingSource(title=f'Ședință {i:03}',start_at=NOW+timedelta(days=i),end_at=NOW+timedelta(days=i,hours=1))
        meetings.store.save_source(source);meetings.save_notes(source.id,f'Notiță {i}')
    meetings.store.summaries();meetings.store.flush()
    from pathlib import Path
    old_read=Path.read_bytes
    def guarded(path):
        if path.name=='notes.md':pytest.fail('Nu se citesc toate notițele în liste/index')
        return old_read(path)
    monkeypatch.setattr(Path,'read_bytes',guarded)
    meetings.store=MeetingStore(meetings.ws.repo)
    rows,count=meetings.list(mode='all',text='Ședință 17',limit=3)
    assert count==10 and [r['title'] for r in rows]==['Ședință 170','Ședință 171','Ședință 172']
    meetings.store.cache.unlink();meetings.store.invalidate()
    assert meetings.list(mode='notes',limit=5)[1]==180


def test_corrupt_metadata_integrity_report_and_cache_rebuild(meetings):
    mid=imported(meetings);meetings.save_notes(mid,'Păstrează')
    meetings.store.flush();meetings.store.cache.write_text('{bad')
    meetings.store.invalidate();assert meetings.store.summaries()[0]['id']==mid
    meetings.store.path(mid,'source.json').write_text('{bad')
    root=meetings.ws.root;meetings.ws.close();w=Workspace.open(root)
    try:
        assert any(i.code=='meeting_corrupt' for i in w.issues)
        assert (w.repo.system_dir/'meetings'/mid/'notes.md').read_text()=='Păstrează'
    finally:w.close()


def test_notes_ui_autosave_cancel_error_and_readonly(ui,monkeypatch):
    p=ui.calendar_page.meetings;s=ui.ws.meetings.manual(title='Notițe',start=utcnow(),end=utcnow()+timedelta(hours=1))
    assert ui.open_meeting(s.id);ui.root.update()
    assert not ui.timer.state
    p.notes.insert('end','Notițe scrise aici');ui.root.update()
    assert p.dirty and p._save_job
    assert p.save() and ui.ws.meetings.store.notes(s.id)=='Notițe scrise aici'
    p.notes.insert('end',' · ciornă');ui.root.update()
    save=ui.ws.meetings.save_notes
    monkeypatch.setattr(ui.ws.meetings,'save_notes',lambda *a:(_ for _ in ()).throw(OSError('disk')))
    assert not p.save() and p.dirty and 'Salvarea a eșuat' in p.save_state.cget('text')
    assert p.notes.get('1.0','end-1c').endswith('ciornă')
    monkeypatch.setattr('focusdesk.ui.meetings.ask_choice',lambda *a,**k:'stay')
    p.back();assert p.mid==s.id and p.dirty
    monkeypatch.setattr(ui.ws.meetings,'save_notes',save)
    assert p.save();p.back();assert p.mid is None


def test_meeting_ui_list_state_back_and_no_notes_reads_on_refresh(ui,monkeypatch):
    svc=ui.ws.meetings;s=svc.manual(title='Caz pentru căutare',start=utcnow(),end=utcnow()+timedelta(hours=1))
    ui.show_view('calendar');p=ui.calendar_page.meetings
    ui.calendar_page.nb.select(p);ui.root.update();p.query.set('Caz');p.filter_changed();p.tv.selection_set(s.id)
    p.open(s.id);ui.root.update();p.notes.insert('end','Ciornă');ui.root.update()
    assert p.save();p.back();ui.root.update()
    assert p.query.get()=='Caz' and p.tv.selection()==(s.id,)
    monkeypatch.setattr(svc.store,'notes',lambda *a:pytest.fail('Refreshul listei nu citește notes.md'))
    p.refresh();assert p.tv.exists(s.id)

class FakeCollection:
    def __init__(self,items):self.items=items;self.index=0;self.calls=[];self.IncludeRecurrences=False
    def Sort(self,key):self.calls.append(('sort',key))
    def Restrict(self,query):self.calls.append(('restrict',query));return self
    def GetFirst(self):self.index=0;return self.items[0] if self.items else None
    def GetNext(self):self.index+=1;return self.items[self.index] if self.index<len(self.items) else None

class FakeAppointment:
    def __init__(self,*,start=NOW,end=None,recurrence=0,original=None,cancelled=False,uid='series'):
        self.StartUTC=start;self.EndUTC=end or start+timedelta(hours=1);self.RecurrenceState=recurrence
        self.EntryID='entry-'+str(start);self.GlobalAppointmentID=uid;self.Subject='Fără corp importat'
        self.Location='Sala';self.Organizer='Organizator';self.AllDayEvent=False;self.MeetingStatus=5 if cancelled else 0
        self.original=original;self.PropertyAccessor=self
    def GetProperty(self,key):
        if key.endswith('82280040') and self.original is not None:return self.original
        if key.endswith('8245001F'):return 'https://example.test/meeting'
        raise AttributeError('unavailable property')
    def __getattr__(self,key):
        if key in ('Body','HTMLBody','Recipients','Attachments'):pytest.fail('Nu se citesc corpuri, participanți sau atașamente')
        raise AttributeError(key)

class FakeReadBackend:
    def __init__(self,items):
        from types import SimpleNamespace
        self.collection=FakeCollection(items);self.folder=SimpleNamespace(Items=self.collection)
    def _folder(self,store,folder):assert (store,folder)==('store','calendar');return self.folder
    def _prop(self,item,name):return None
    def create(self,*args):pytest.fail('Importul nu scrie în Outlook')
    update=delete=send_mail=create


def test_concrete_com_metadata_reader_original_slot_and_no_body(monkeypatch):
    from focusdesk.integrations.meetings import read_outlook_meetings
    regular=FakeAppointment(recurrence=2)
    exception=FakeAppointment(start=NOW+timedelta(days=1,hours=2),recurrence=3,original=NOW+timedelta(days=1),cancelled=True)
    fake=FakeReadBackend([regular,exception])
    batch=read_outlook_meetings(fake,'store','calendar',FIRST,LAST)
    assert batch.complete and len(batch.events)==2
    assert batch.events[0].uid==batch.events[1].uid=='series'
    assert batch.events[0].occurrence_key==NOW.isoformat()
    assert batch.events[1].occurrence_key==(NOW+timedelta(days=1)).isoformat()
    assert batch.events[1].cancelled
    assert batch.events[1].join_url=='https://example.test/meeting'
    assert [c[0] for c in fake.collection.calls]==['sort','restrict']


def test_exception_without_stable_original_slot_is_partial_not_duplicate():
    from focusdesk.integrations.meetings import read_outlook_meetings
    fake=FakeReadBackend([FakeAppointment(recurrence=3)])
    batch=read_outlook_meetings(fake,'store','calendar',FIRST,LAST)
    assert not batch.complete and not batch.events and batch.warnings


def test_restrict_failure_does_not_fallback_to_whole_calendar():
    from focusdesk.integrations.meetings import read_outlook_meetings
    fake=FakeReadBackend([])
    fake.collection.Restrict=lambda q:(_ for _ in ()).throw(RuntimeError('Restrict failed'))
    with pytest.raises(RuntimeError):read_outlook_meetings(fake,'store','calendar',FIRST,LAST)
    assert fake.collection.index==0


class HoldingWorker:
    def shutdown(self):pass
    def __init__(self):self.jobs=[]
    def submit(self,fn,done,error,**kwargs):self.jobs.append((fn,done,error));return None


def test_ui_import_deduplicated_and_stale_source_ignored(ui,monkeypatch):
    p=ui.calendar_page.meetings;ui.show_view('calendar');ui.calendar_page.nb.select(p);ui.root.update()
    ui.ws.meetings.configure('store','calendar','Sursă explicită')
    worker=HoldingWorker();monkeypatch.setattr(ui.outlook,'worker',worker)
    monkeypatch.setattr('focusdesk.ui.meetings.ask_choice',lambda *a,**k:'import')
    p.import_meetings();p.import_meetings();assert len(worker.jobs)==1
    ui.ws.meetings.configure('store','other','Altă sursă')
    worker.jobs[0][1](MeetingBatch([event()]))
    assert not ui.ws.meetings.store.summaries() and p._import_job is None


def test_ui_late_import_never_applied_to_new_workspace(ui,tmp_path,monkeypatch):
    p=ui.calendar_page.meetings;ui.show_view('calendar');ui.calendar_page.nb.select(p);ui.root.update()
    ui.ws.meetings.configure('store','calendar','Sursă')
    worker=HoldingWorker();monkeypatch.setattr(ui.outlook,'worker',worker)
    monkeypatch.setattr('focusdesk.ui.meetings.ask_choice',lambda *a,**k:'import')
    p.import_meetings();assert len(worker.jobs)==1
    assert ui.open_workspace(tmp_path/'different',create=True)
    worker.jobs[0][1](MeetingBatch([event()]))
    assert not ui.ws.meetings.store.summaries()


def test_readonly_note_editor_and_ctrl_s_does_not_save_task_metadata(ui):
    svc=ui.ws.meetings;s=svc.manual(title='Offline',start=utcnow(),end=utcnow()+timedelta(hours=1))
    ui.open_meeting(s.id);p=ui.calendar_page.meetings;ui.root.update()
    p.notes.insert('end','Text');ui.root.update();ui.save_current()
    assert svc.store.notes(s.id)=='Text'
    ui.ws.repo.read_only=True
    try:
        p.open(s.id);ui.root.update();assert p.notes.cget('state')=='disabled'
        assert p.actions_menu.instate(['disabled'])
    finally:ui.ws.repo.read_only=False


def test_meeting_to_task_and_context_navigation(ui,monkeypatch):
    from focusdesk.ui.meetings import MeetingNodeDialog
    svc=ui.ws.meetings;s=svc.manual(title='Decizii',start=utcnow(),end=utcnow()+timedelta(hours=1))
    action=svc.save_action(s.id,text='Fragment pentru task')
    dialog=MeetingNodeDialog(ui.root,ui,s.id,text=action.text,action=action)
    dialog.title_var.set('Task confirmat');node=dialog.collect();dialog.destroy()
    assert node and ui.ws.get_description(node.id)=='Fragment pentru task'
    ui.root.deiconify();ui.select_node(node.id,reveal=True);ui.root.update()
    assert ui.inspector.meeting_links.winfo_ismapped()
    ui.inspector.meeting_links.menu.invoke(0);ui.root.update()
    assert ui.calendar_page.meetings.mid==s.id
    assert not ui.timer.state


def test_pending_action_reserved_across_new_dialog_request(meetings,monkeypatch):
    mid=imported(meetings);a=meetings.save_action(mid,text='O singură creare')
    original=meetings.store.save_local
    monkeypatch.setattr(meetings.store,'save_local',lambda *a:(_ for _ in ()).throw(OSError('disk')))
    with pytest.raises(OSError):meetings.create_node(mid,request_id=new_id(),title='Un singur task',action_id=a.id)
    assert len(meetings.ws.nodes)==1
    monkeypatch.setattr(meetings.store,'save_local',original)
    with pytest.raises(ValidationError):meetings.create_node(mid,request_id=new_id(),title='Alte date',action_id=a.id)
    created=meetings.create_node(mid,request_id=new_id(),title='Un singur task',action_id=a.id)
    assert len(meetings.ws.nodes)==1 and meetings.store.local(mid).actions[0].node_id==created.id


def test_stale_action_dialog_refuses_overwrite(meetings):
    mid=imported(meetings);old=meetings.save_action(mid,text='Inițial')
    changed=meetings.save_action(mid,text='Schimbare externă',action_id=old.id)
    with pytest.raises(ExternalModificationError):meetings.save_action(mid,text='Ciornă veche',action_id=old.id,expected=old)
    assert meetings.store.local(mid).actions[0]==changed


def test_all_day_keeps_calendar_dates_even_in_another_workspace_timezone(meetings):
    e=event(all_day=True,all_day_start=date(2026,10,25),all_day_end=date(2026,10,26),start=datetime(2026,10,24,21,tzinfo=timezone.utc),end=datetime(2026,10,25,22,tzinfo=timezone.utc))
    mid=imported(meetings,e)
    assert meetings.store.source(mid).all_day_start==date(2026,10,25)
    assert meetings.store.summaries()[0]['all_day_end']=='2026-10-26'


def test_partial_warnings_persist_and_manual_retry_validates(meetings):
    meetings.import_batch('store','calendar',MeetingBatch([],complete=False,warnings=['Un element indisponibil']),FIRST,LAST)
    config=meetings.config();assert not config['complete'] and config['last_warnings']==['Un element indisponibil']
    oid=new_id();one=meetings.manual(title='Offline',start=NOW,end=NOW+timedelta(hours=1),request_id=oid)
    assert meetings.manual(title='Offline',start=NOW,end=NOW+timedelta(hours=1),request_id=oid).id==one.id
    with pytest.raises(ValidationError):meetings.manual(title='Alt titlu',start=NOW,end=NOW+timedelta(hours=1),request_id=oid)


def test_explicit_integrity_reads_notes_and_reports_invalid_text(meetings):
    mid=imported(meetings);meetings.store.path(mid,'notes.md').write_bytes(b'\xff')
    assert not meetings.integrity(include_notes=False)
    issues=meetings.integrity(include_notes=True)
    assert len(issues)==1 and mid in issues[0][0]


def test_ui_outlook_error_retains_offline_notes_and_unblocks_retry(ui,monkeypatch):
    p=ui.calendar_page.meetings;ui.show_view('calendar');ui.calendar_page.nb.select(p);ui.root.update()
    svc=ui.ws.meetings;svc.configure('store','calendar','Calendar')
    s=svc.manual(title='Date offline',start=utcnow(),end=utcnow()+timedelta(hours=1));svc.save_notes(s.id,'Păstrează')
    worker=HoldingWorker();monkeypatch.setattr(ui.outlook,'worker',worker)
    monkeypatch.setattr('focusdesk.ui.meetings.ask_choice',lambda *a,**k:'import')
    p.import_meetings();worker.jobs[0][2](RuntimeError('Outlook Classic indisponibil'))
    assert p._import_job is None and svc.config()['last_error']=='Outlook Classic indisponibil'
    assert svc.store.notes(s.id)=='Păstrează'
    p.import_meetings();assert len(worker.jobs)==2
    svc.configure('store','other','Altă sursă');worker.jobs[1][2](RuntimeError('întârziat'))
    assert p._import_job is None and not svc.config().get('last_error')


def test_integrity_and_content_search_do_not_change_open_note_conflict_baseline(meetings):
    mid=imported(meetings);meetings.save_notes(mid,'Text văzut în editor');meetings.store.notes(mid)
    meetings.store.path(mid,'notes.md').write_text('Modificare externă',encoding='utf-8')
    assert meetings.search_notes('externă')==[mid]
    assert not meetings.integrity(include_notes=True)
    with pytest.raises(ExternalModificationError):meetings.save_notes(mid,'Ciornă din vechiul text')


def test_import_com_worker_runs_off_tk_and_applies_on_tk(ui,monkeypatch):
    import threading,time
    from focusdesk.workers.com_worker import ComWorker
    p=ui.calendar_page.meetings;ui.show_view('calendar');ui.calendar_page.nb.select(p);ui.root.update()
    ui.ws.meetings.configure('store','calendar','Calendar fals')
    main=threading.get_ident();reader_threads=[];writer_threads=[]
    from focusdesk.integrations.meetings import read_outlook_meetings
    class Backend(FakeReadBackend):
        def read_meetings(self,*args):
            reader_threads.append(threading.get_ident());return read_outlook_meetings(self,*args)
    now=utcnow()
    worker=ComWorker(ui.bridge,lambda:Backend([FakeAppointment(start=now)]),use_com=False)
    monkeypatch.setattr(ui.outlook,'worker',worker)
    save=ui.ws.meetings.store.save_source
    def checked(record):writer_threads.append(threading.get_ident());return save(record)
    monkeypatch.setattr(ui.ws.meetings.store,'save_source',checked)
    monkeypatch.setattr('focusdesk.ui.meetings.ask_choice',lambda *a,**k:'import')
    p.import_meetings();deadline=time.monotonic()+3
    while p._import_job and time.monotonic()<deadline:
        ui.root.update();time.sleep(.01)
    assert not p._import_job and reader_threads and all(t!=main for t in reader_threads)
    assert writer_threads and all(t==main for t in writer_threads)
    assert len(ui.ws.meetings.store.summaries())==1


def test_converted_task_trash_restore_keeps_meeting_notes_and_reference(meetings):
    mid=imported(meetings);meetings.save_notes(mid,'Notițe')
    action=meetings.save_action(mid,text='Acțiune');request=new_id()
    node=meetings.create_node(mid,request_id=request,title='Task',action_id=action.id)
    meetings.ws.trash(node.id)
    assert meetings.store.local(mid).actions[0].node_id==node.id
    with pytest.raises(NotFoundError):meetings.create_node(mid,request_id=request,title='Task',action_id=action.id)
    assert meetings.store.notes(mid)=='Notițe'
    meetings.ws.restore(node.id)
    assert meetings.ws.get(node.id).meeting_ids==[mid]
    assert meetings.create_node(mid,request_id=request,title='Task',action_id=action.id).id==node.id


def test_warm_index_loads_metadata_index_without_source_or_notes_payloads(meetings,monkeypatch):
    from focusdesk.storage.meetings import MeetingStore
    mid=imported(meetings);meetings.save_notes(mid,'Text mare\n'*500);meetings.store.flush()
    old_read=Path.read_bytes;read_names=[]
    def observed(path):read_names.append(path.name);return old_read(path)
    monkeypatch.setattr(Path,'read_bytes',observed)
    store=MeetingStore(meetings.ws.repo)
    assert store.summaries()[0]['has_notes']
    assert 'index.json' in read_names
    assert not {'source.json','local.json','notes.md'} & set(read_names)


def test_new_requirement_link_interruption_recovers_same_task(meetings,monkeypatch):
    source=meetings.ws.create_node(Kind.TASK,'Script finalizat');meetings.ws.update_node(source.id,status=Status.DONE)
    mid=imported(meetings);action=meetings.save_action(mid,text='Cerință nouă')
    original=meetings.store.save_local
    monkeypatch.setattr(meetings.store,'save_local',lambda *a:(_ for _ in ()).throw(OSError('disk')))
    request=new_id();params=dict(request_id=request,title='Update independent',action_id=action.id,followup_source=source.id)
    with pytest.raises(OSError):meetings.create_node(mid,**params)
    monkeypatch.setattr(meetings.store,'save_local',original)
    root=meetings.ws.root;meetings.ws.close();ws=Workspace.open(root)
    try:
        assert len(ws.nodes)==2 and ws.get(source.id).status==Status.DONE
        node=ws.meetings.create_node(mid,**params)
        assert node.continuation_of==source.id and node.meeting_ids==[mid]
        assert ws.meetings.store.local(mid).actions[0].node_id==node.id
    finally:ws.close()


def test_progressive_import_can_stop_between_atomic_batches_without_loss(meetings):
    events=[event(f'event-{i}') for i in range(24)]
    iterator=meetings.iter_import_batch('store','calendar',MeetingBatch(events),FIRST,LAST)
    progress=next(iterator)
    assert progress['applied']==8 and len(meetings.store.summaries())==8
    assert meetings._importing and not meetings.config().get('last_update')
    iterator.close();assert not meetings._importing
    meetings.import_batch('store','calendar',MeetingBatch(events),FIRST,LAST)
    assert len(meetings.store.summaries())==24


def test_workspace_switch_stops_partial_local_apply_before_lock_release(ui,tmp_path,monkeypatch):
    p=ui.calendar_page.meetings;ui.show_view('calendar');ui.calendar_page.nb.select(p);ui.root.update()
    ui.ws.meetings.configure('store','calendar','Sursă')
    worker=HoldingWorker();monkeypatch.setattr(ui.outlook,'worker',worker)
    monkeypatch.setattr('focusdesk.ui.meetings.ask_choice',lambda *a,**k:'import')
    p.import_meetings();worker.jobs[0][1](MeetingBatch([event(f'event-{i}') for i in range(24)]))
    next(p._apply_iter) # simulate exactly one persisted chunk before the user's navigation event
    old_root=ui.ws.root
    assert len(ui.ws.meetings.store.summaries())==8
    assert ui.open_workspace(tmp_path/'new-workspace',create=True)
    ui.root.update()
    assert not ui.ws.meetings.store.summaries()
    old=Workspace.open(old_root)
    try:
        assert len(old.meetings.store.summaries())==8
        assert 'întreruptă' in old.meetings.config()['last_error']
    finally:old.close()
