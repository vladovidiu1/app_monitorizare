"""Independent later requirements, shared code and recoverable creation on temporary data."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from uuid import UUID,uuid5
import pytest

from focusdesk.domain.common import new_id
from focusdesk.domain.models import Kind,Status,Priority,SourceWorkspace
from focusdesk.domain.session import SessionRecord
from focusdesk.errors import ValidationError,CycleError,StorageError,ReadOnlyError,ExternalModificationError
from focusdesk.services.workspace import Workspace
from focusdesk.services.files import FileService
from focusdesk.services.checkpoints import CheckpointService
from focusdesk.services.activity import activity_model,ActivityFilters
from focusdesk.services.backup import create_backup,restore_backup_to_folder
from focusdesk.storage.atomic import read_json,atomic_write_json


def done_source(ws,parent=None):
    node=ws.create_node(Kind.TASK,'Script inițial',parent,description='Descriere inițială',estimated_minutes=80,
        checklist=[{'text':'Pas vechi','done':True}],priority=Priority.HIGH)
    ws.update_node(node.id,status=Status.DONE)
    start=datetime.now(timezone.utc)-timedelta(days=2)
    ws.repo.sessions.save(SessionRecord(node_id=node.id,start_at=start,end_at=start+timedelta(hours=1),actual_seconds=900,status='done'))
    return ws.get(node.id)


def new(ws,source,**kw):
    return ws.create_followup(source.id,title=kw.pop('title','Cerință nouă'),request_id=kw.pop('request_id',new_id()),**kw)


def test_reopen_preserves_payload_work_and_completion_evidence(ws):
    source=done_source(ws);before=ws.get_description(source.id);history=ws.list_history(source.id)
    reopened=ws.reopen_task(source.id,'Corecție la cerința inițială')
    assert reopened.status==Status.TODO and reopened.completed_at is None
    assert reopened.id in ws.repo.active_task_ids
    assert reopened.checklist[0].done and reopened.estimated_minutes==80
    assert ws.get_description(source.id)==before
    assert ws.followups.own_seconds(source.id)==900
    assert {e.id for e in history}<={e.id for e in ws.list_history(source.id)}
    assert any(e.type=='reopened' and 'Corecție' in e.data['reason'] for e in ws.list_history(source.id))
    assert source.id in activity_model(ws).report(ActivityFilters()).completed_ids
    assert not ws.repo.recurrences.list_all()


def test_new_task_is_sibling_independent_and_does_not_reopen_source(ws):
    project=ws.create_node(Kind.PROJECT,'P');source=done_source(ws,project.id)
    snapshot=source.model_dump(mode='json');description=ws.get_description(source.id)
    node=new(ws,source,description='Solicitare nouă')
    assert node.id!=source.id and node.status==Status.TODO and node.parent_id==project.id
    assert node.continuation_of==source.id and not node.depends_on_ids and not node.related_node_ids
    assert node.estimated_minutes is None and node.remaining_minutes is None
    assert node.completed_at is None and node.pinned_today is None and node.review_at is None
    assert not node.checklist and not node.attachments and node.recurrence_template_id is None
    assert ws.get(source.id).model_dump(mode='json')==snapshot
    assert ws.get_description(source.id)==description and ws.get_description(node.id)=='Solicitare nouă'
    assert node.id in ws.repo.active_task_ids and ws.followups.own_seconds(node.id)==0
    assert ws.repo.sessions.select(node_ids={node.id})==[]
    assert [n.id for n in ws.followups.children(source.id)]==[node.id]
    assert all(e.type not in ('status_changed','session_stopped') for e in ws.list_history(node.id))
    assert not ws.repo.recurrences.list_all()


def test_explicit_copy_only_description_and_unchecked_checklist(ws):
    source=done_source(ws)
    node=new(ws,source,description='Update nou',copy_description=True,copy_checklist=True)
    assert ws.get_description(node.id)=='Descriere inițială\n\nUpdate nou'
    assert node.checklist[0].text=='Pas vechi' and not node.checklist[0].done
    assert node.priority==Priority.NORMAL and node.estimated_minutes is None


def test_typed_relation_cycles_and_initial_task_navigation(ws):
    a=done_source(ws);b=new(ws,a);c=new(ws,b)
    assert ws.followups.lineage(c.id)==[c.id,b.id,a.id]
    assert ws.followups.family_ids(a.id)=={a.id,b.id,c.id}
    with pytest.raises(CycleError):ws.update_node(a.id,continuation_of=c.id)
    with pytest.raises(CycleError):ws.update_node(c.id,continuation_of=c.id)
    folder=ws.create_node(Kind.FOLDER,'F')
    with pytest.raises(ValidationError):ws.update_node(c.id,continuation_of=folder.id)


def test_common_managed_code_no_copy_and_distinct_checkpoints(ws):
    source=done_source(ws);files=FileService(ws)
    files.set_code_folder(source.id,'files/code',mode='managed')
    code=files.usable_source_dir(source.id);(code/'script.py').write_text('print(1)')
    old=CheckpointService(ws).create(source.id,force=True)
    node=new(ws,source,code_access='shared')
    resolved=files.effective_source(node.id)
    assert resolved.path==code and resolved.owner_id==node.id and resolved.code_owner_id==source.id
    assert list((ws.node_dir(node.id)/'files').iterdir())==[]
    service=CheckpointService(ws)
    assert service.list_for_node(node.id)==[]
    fresh=service.create(node.id,force=True)
    assert fresh.owner_node_id==node.id and fresh.node_id==node.id
    assert {m.id for m in service.list_for_node(source.id)}=={old.id}
    assert {m.id for m in service.list_for_node(node.id)}=={fresh.id}
    assert {source.id,node.id}<=set(files.shared_users(node.id))


def test_not_preselected_code_does_not_inherit_parent_source(ws):
    project=ws.create_node(Kind.PROJECT,'P');FileService(ws).set_code_folder(project.id,'files/project-code',mode='managed')
    source=done_source(ws,project.id)
    without=new(ws,source)
    shared=new(ws,source,code_access='shared')
    files=FileService(ws)
    assert files.effective_source(without.id) is None
    assert files.effective_source(shared.id).path==files.effective_source(source.id).path
    assert files.effective_source(shared.id).owner_id==shared.id


def test_missing_code_retains_reference_and_can_choose_other_folder(ws,tmp_path):
    source=done_source(ws);files=FileService(ws);files.set_code_folder(source.id,'files/missing',mode='managed')
    files.usable_source_dir(source.id).rmdir()
    node=new(ws,source,code_access='shared')
    assert files.usable_source_dir(node.id) is None and node.continuation_of==source.id
    folder=tmp_path/'replacement';folder.mkdir()
    files.set_code_folder(node.id,folder)
    assert files.usable_source_dir(node.id)==folder
    assert ws.get_description(node.id)==''


def test_archived_source_allowed_but_archived_destination_requires_choice(ws):
    project=ws.create_node(Kind.PROJECT,'P');source=done_source(ws,project.id)
    ws.archive(source.id)
    node=new(ws,source)
    assert ws.get(source.id).archived_at and node.archived_at is None
    ws.archive(project.id)
    with pytest.raises(ValidationError,match='arhivat'):new(ws,source)
    outside=new(ws,source,parent_id=None)
    assert outside.parent_id is None and ws.get(source.id).archived_at


def test_trash_restore_typed_references_and_code_owner(ws):
    source=done_source(ws);files=FileService(ws);files.set_code_folder(source.id,'files/code',mode='managed')
    node=new(ws,source,code_access='shared');tail=new(ws,node,code_access='shared')
    ws.trash(source.id)
    assert node.id in ws.nodes and ws.get(node.id).continuation_of==source.id
    assert files.usable_source_dir(node.id) is None
    ws.restore(source.id)
    assert files.usable_source_dir(node.id)==files.usable_source_dir(source.id)
    ws.trash(node.id);assert tail.id in ws.nodes and tail.continuation_of==node.id
    ws.restore(node.id)
    assert ws.followups.lineage(tail.id)==[tail.id,node.id,source.id]


def test_idempotent_double_click_does_not_duplicate_node_events_or_recreate_trash(ws):
    source=done_source(ws);request=new_id()
    a=new(ws,source,request_id=request);count=len(ws.nodes);events=len(ws.list_history())
    b=new(ws,source,request_id=request)
    assert a.id==b.id and len(ws.nodes)==count and len(ws.list_history())==events
    with pytest.raises(ValidationError):new(ws,source,title='Alt titlu',request_id=request)
    ws.trash(a.id)
    with pytest.raises(ValidationError,match='coș'):new(ws,source,request_id=request)
    assert len(ws.nodes)==count-1


@pytest.mark.parametrize('failure',['before_node','after_node','between_events','before_receipt'])
def test_retry_and_restart_recover_creation_without_duplicates(tmp_path,monkeypatch,failure):
    root=tmp_path/'ws';ws=Workspace.open(root,create=True);source=done_source(ws);request=new_id()
    original_create=ws.repo.create_node;original_history=ws.repo.history.save;original_operations=ws.repo.operations.save
    counter=[0]
    def create(*a,**kw):
        if failure=='before_node':raise StorageError('injected before node')
        original_create(*a,**kw)
        if failure=='after_node':raise StorageError('injected after node')
    def history(event):
        counter[0]+=1
        if failure=='between_events' and counter[0]==2:raise StorageError('injected between events')
        return original_history(event)
    def operations(op):
        if failure=='before_receipt' and op.type=='followup_create' and op.state=='done':raise StorageError('injected receipt')
        return original_operations(op)
    monkeypatch.setattr(ws.repo,'create_node',create);monkeypatch.setattr(ws.repo.history,'save',history);monkeypatch.setattr(ws.repo.operations,'save',operations)
    with pytest.raises(StorageError):new(ws,source,description='Ciornă recuperabilă',request_id=request)
    ws.repo.lock.release() # simulate crash, not a graceful cache checkpoint
    fresh=Workspace.open(root)
    try:
        node=new(fresh,source,description='Ciornă recuperabilă',request_id=request)
        assert len(fresh.nodes)==2 and fresh.get(source.id).status==Status.DONE
        assert fresh.get_description(node.id)=='Ciornă recuperabilă'
        assert fresh.repo.operations.get(request).state=='done'
        assert len([e for e in fresh.list_history(node.id) if e.type=='created'])==1
        assert len([e for e in fresh.list_history(source.id) if e.type=='followup_created'])==1
    finally:fresh.close()


def test_partial_authoritative_node_json_is_recovered(tmp_path,monkeypatch):
    root=tmp_path/'ws';ws=Workspace.open(root,create=True);source=done_source(ws);request=new_id()
    import focusdesk.storage.repository as repository
    original=repository.atomic_write_text
    def fail(path,*a,**kw):
        if path.name=='description.md':raise StorageError('crash before description')
        return original(path,*a,**kw)
    monkeypatch.setattr(repository,'atomic_write_text',fail)
    with pytest.raises(StorageError):new(ws,source,description='Text după crash',request_id=request)
    ws.repo.lock.release();monkeypatch.setattr(repository,'atomic_write_text',original)
    fresh=Workspace.open(root)
    try:
        node=new(fresh,source,description='Text după crash',request_id=request)
        assert fresh.get_description(node.id)=='Text după crash' and len(fresh.nodes)==2
    finally:fresh.close()


def test_correction_before_any_authoritative_node_written_keeps_same_request(ws,monkeypatch):
    source=done_source(ws);request=new_id();original=ws.repo.create_node
    monkeypatch.setattr(ws.repo,'create_node',lambda *a,**kw:(_ for _ in ()).throw(StorageError('before create')))
    with pytest.raises(StorageError):new(ws,source,request_id=request)
    monkeypatch.setattr(ws.repo,'create_node',original)
    node=new(ws,source,title='Titlu corectat',request_id=request)
    assert node.id==str(uuid5(UUID(request),'requirement')) and len(ws.nodes)==2


def test_read_only_and_external_modification(ws):
    source=done_source(ws);ws.repo.read_only=True
    with pytest.raises(ReadOnlyError):new(ws,source)
    with pytest.raises(ReadOnlyError):ws.reopen_task(source.id)
    ws.repo.read_only=False
    path=ws.node_dir(source.id)/'node.json';data=read_json(path)[0];data['title']='Extern';atomic_write_json(path,data)
    with pytest.raises(ExternalModificationError):new(ws,source)


def test_backup_restore_preserves_shared_managed_code_and_chain(ws,tmp_path):
    source=done_source(ws);files=FileService(ws);files.set_code_folder(source.id,'files/code',mode='managed')
    (files.usable_source_dir(source.id)/'script.py').write_text('print("original")')
    node=new(ws,source,code_access='shared',description='Update')
    backup=create_backup(ws,full=True)
    root=restore_backup_to_folder(backup.path,tmp_path/'restored')
    restored=Workspace.open(root)
    try:
        assert restored.get(node.id).continuation_of==source.id
        path=FileService(restored).usable_source_dir(node.id)
        assert path==FileService(restored).usable_source_dir(source.id)
        assert path.is_relative_to(root) and (path/'script.py').read_text()=='print("original")'
        assert restored.get(source.id).status==Status.DONE
    finally:restored.close()


def test_family_time_does_not_double_count_dashboard(ws):
    source=done_source(ws);node=new(ws,source);tail=new(ws,node)
    start=datetime.now(timezone.utc)-timedelta(hours=2)
    for item,seconds in ((node,300),(tail,600)):
        ws.repo.sessions.save(SessionRecord(node_id=item.id,start_at=start,end_at=start+timedelta(hours=1),actual_seconds=seconds,status='done'))
    assert ws.followups.own_seconds(source.id)==900 and ws.followups.own_seconds(node.id)==300
    ids=ws.followups.family_ids(tail.id);totals=ws.repo.sessions.worked_totals()
    assert sum(totals.get(n,0) for n in ids)==1800
    assert activity_model(ws).report(ActivityFilters()).worked==1800


def test_read_only_does_not_finish_pending_operation(tmp_path,monkeypatch):
    root=tmp_path/'ws';ws=Workspace.open(root,create=True);source=done_source(ws);request=new_id()
    monkeypatch.setattr(ws.repo,'create_node',lambda *a,**kw:(_ for _ in ()).throw(StorageError('before create')))
    with pytest.raises(StorageError):new(ws,source,request_id=request)
    before={p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file() and p.name!='workspace.lock'}
    readonly=Workspace.open(root,read_only=True)
    try:assert readonly.repo.operations.get(request).state=='pending' and len(readonly.nodes)==1
    finally:readonly.close()
    after={p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file() and p.name!='workspace.lock'}
    assert before==after
    ws.repo.lock.release()


def test_recovery_does_not_overwrite_external_description(tmp_path,monkeypatch):
    root=tmp_path/'ws';ws=Workspace.open(root,create=True);source=done_source(ws);request=new_id()
    original=ws.repo.operations.save
    def fail(op):
        if op.type=='followup_create' and op.state=='done':raise StorageError('crash')
        return original(op)
    monkeypatch.setattr(ws.repo.operations,'save',fail)
    with pytest.raises(StorageError):new(ws,source,description='Original request',request_id=request)
    nid=str(uuid5(UUID(request),'requirement'));path=ws.node_dir(nid)/'description.md';path.write_text('Editare externă')
    ws.repo.lock.release();fresh=Workspace.open(root)
    try:
        assert fresh.get_description(nid)=='Editare externă'
        assert fresh.repo.operations.get(request).state=='pending'
        assert any('modificată extern' in m for m in fresh.recovery_messages)
    finally:fresh.close()


def test_recovery_before_first_node_json(tmp_path,monkeypatch):
    root=tmp_path/'ws';ws=Workspace.open(root,create=True);source=done_source(ws);request=new_id()
    import focusdesk.storage.repository as repository
    original=repository.atomic_write_json
    def fail(path,*a,**kw):
        if path.name=='node.json':raise StorageError('before node JSON')
        return original(path,*a,**kw)
    monkeypatch.setattr(repository,'atomic_write_json',fail)
    with pytest.raises(StorageError):new(ws,source,description='Cerere',request_id=request)
    ws.repo.lock.release();monkeypatch.setattr(repository,'atomic_write_json',original)
    fresh=Workspace.open(root)
    try:
        node=new(fresh,source,description='Cerere',request_id=request)
        assert len(fresh.nodes)==2 and fresh.get_description(node.id)=='Cerere'
    finally:fresh.close()


def test_external_relation_cycle_reported_on_reload(ws):
    a=done_source(ws);b=new(ws,a)
    path=ws.node_dir(a.id)/'node.json';data=read_json(path)[0];data['continuation_of']=b.id;atomic_write_json(path,data)
    ws.reload()
    assert any(issue.code=='continuation_cycle' for issue in ws.issues)
    with pytest.raises(CycleError):ws.followups.lineage(b.id)


def test_dialog_draft_error_success_and_context_navigation(ui,monkeypatch):
    from focusdesk.ui.colleagues_ui import ColleagueField
    source=ui.ws.get(ui.selected_id);ui.ws.update_node(source.id,status=Status.DONE);ui.root.update()
    dialog=ui.add_followup(source.id);ui.root.update()
    assert isinstance(dialog.requester,ColleagueField)
    dialog.title_var.set('Update nou');dialog.description.insert('1.0','Cerință păstrată la eroare')
    dialog.code_access.set('folder');dialog.code_folder.set('/not-a-real-folder')
    request=dialog.request_id
    assert dialog.create() is None and dialog.description.get('1.0','end-1c')=='Cerință păstrată la eroare'
    assert dialog.request_id==request and dialog.winfo_exists()
    dialog.code_access.set('none');dialog.code_folder.set('');created=dialog.create();ui.root.update()
    assert created and ui.ws.get(source.id).status==Status.DONE
    assert created.id in ui.ws.repo.active_task_ids
    assert ui.inspector.followup_context.children_menu.index('end')>=1
    assert 'Update nou' in ui.inspector.followup_context.children_menu.entrycget(0,'label')
    assert dialog.create().id==created.id
    dialog.open_created();ui.root.update()
    assert ui.selected_id==created.id
    assert 'Continuare a:' in ui.inspector.followup_context.source_btn.cget('text')
    ui.inspector.followup_context.source_btn.invoke();ui.root.update()
    assert ui.selected_id==source.id


def test_dialog_requires_destination_when_parent_archived(ui):
    project=ui.ws.create_node(Kind.PROJECT,'Proiect vechi')
    source=ui.ws.create_node(Kind.TASK,'Script',project.id,status=Status.DONE)
    ui.ws.archive(project.id)
    dialog=ui.add_followup(source.id);dialog.title_var.set('Update')
    assert dialog.dest.get() not in dialog.destinations and dialog.create() is None
    dialog.dest.set('Rădăcina workspace-ului')
    created=dialog.create();assert created.parent_id is None and ui.ws.get(project.id).archived_at
    dialog.close()


def test_task_space_chain_and_common_code_labels(ui):
    source=ui.ws.get(ui.selected_id);files=ui.files;files.set_code_folder(source.id,'files/code',mode='managed')
    b=new(ui.ws,source,code_access='shared');c=new(ui.ws,b,code_access='shared')
    ui.refresh_all();assert ui.open_task_space(c.id);ui.root.update()
    context=ui.task_space.followup_context
    assert 'Task inițial:' in context.root_btn.cget('text')
    context.show_total();assert 'Total lanț' in context.total_lbl.cget('text')
    tab=ui.inspector.tab_by_title('Fișiere');tab.load(ui.ws.get(c.id))
    assert 'Folder de cod comun' in tab.code_note.cget('text')
    context.root_btn.invoke();ui.root.update();assert ui.task_space.node_id==source.id


def test_optional_reopen_reason_dialog(ui):
    source=ui.ws.get(ui.selected_id);ui.ws.update_node(source.id,status=Status.DONE);ui.root.update()
    dialog=ui.reopen_with_reason(source.id);dialog.reason.insert('1.0','Corecție cerință inițială');dialog.apply();ui.root.update()
    assert ui.ws.get(source.id).status==Status.TODO
    assert any(e.type=='reopened' and e.data['reason']=='Corecție cerință inițială' for e in ui.ws.list_history(source.id))


def test_saved_checkpoints_available_when_common_live_code_owner_trashed(ws):
    source=done_source(ws);files=FileService(ws);files.set_code_folder(source.id,'files/code',mode='managed')
    (files.usable_source_dir(source.id)/'code.py').write_text('print(1)')
    node=new(ws,source,code_access='shared');checkpoint=CheckpointService(ws).create(node.id,force=True)
    ws.trash(source.id)
    assert files.usable_source_dir(node.id) is None
    assert [m.id for m in CheckpointService(ws).list_for_node(node.id)]==[checkpoint.id]


def test_template_instantiation_does_not_invent_followup_links(ws):
    source=done_source(ws);node=new(ws,source)
    template=ws.templates.capture(node.id,'Șablon')
    instance=ws.create_from_template(template,title='Task din șablon',request_id=new_id())
    assert instance.continuation_of is None and instance.creation_operation_id is None
    assert [item.id for item in ws.followups.children(source.id)]==[node.id]
