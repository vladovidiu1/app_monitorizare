"""Disposable filesystem regressions for indexes, conflicts and active navigation."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil

import pytest
from focusdesk.domain.models import Kind, Status, HistoryEvent
from focusdesk.domain.session import SessionRecord
from focusdesk.errors import StorageError, ExternalModificationError, ReadOnlyError
from focusdesk.services.workspace import Workspace
from focusdesk.services.queries import Queries
from focusdesk.services.sessions import SessionService
from focusdesk.services.activity import activity_ledger
from focusdesk.storage.atomic import atomic_write_json
from focusdesk.storage.records import checksum
from focusdesk.storage.node_cache import NavigationNode


def session(ws, nid, *, days=1, seconds=900):
    start = datetime.now(timezone.utc)-timedelta(days=days)
    s = SessionRecord(node_id=nid,start_at=start,end_at=start+timedelta(minutes=30),status='done',actual_seconds=seconds,summary='Detalii')
    ws.repo.sessions.save(s)
    return s


def test_selection_uses_only_requested_records(ws, monkeypatch):
    nodes=[ws.create_node(Kind.TASK,f'Task {i}') for i in range(40)]
    for n in nodes: session(ws,n.id)
    ws.repo.sessions.summaries(); ws.repo.history.summaries()
    from focusdesk.storage import records
    original=records.read_json; reads=[]
    def tracked(path,**kw): reads.append(path);return original(path,**kw)
    monkeypatch.setattr(records,'read_json',tracked)
    assert len(SessionService(ws).for_node(nodes[0].id))==1
    assert len(ws.list_history(nodes[0].id))==1
    assert len(reads)<=2
    assert all(str(nodes[1].id) not in str(p) for p in reads)


def test_record_copy_and_failed_write_do_not_change_totals(ws,monkeypatch):
    n=ws.create_node(Kind.TASK,'T');s=session(ws,n.id)
    assert ws.repo.sessions.worked_totals()[n.id]==900
    changed=ws.repo.sessions.get(s.id);changed.actual_seconds=7200
    assert ws.repo.sessions.get(s.id).actual_seconds==900
    def fail(*a,**kw):raise StorageError('Injected failure')
    monkeypatch.setattr('focusdesk.storage.records.atomic_write_json',fail)
    with pytest.raises(StorageError):ws.repo.sessions.save(changed)
    assert ws.repo.sessions.worked_totals()[n.id]==900
    assert ws.repo.sessions.get(s.id).actual_seconds==900


@pytest.mark.parametrize('damage',['delete','corrupt','incomplete','dirty'])
def test_record_index_reconciles_without_data_loss(tmp_path,damage):
    root=tmp_path/'ws';ws=Workspace.open(root,create=True)
    n=ws.create_node(Kind.TASK,'T');s=session(ws,n.id)
    ws.repo.sessions.summaries();ws.close()
    cache=root/'_system/sessions/.cache/index.json'
    if damage=='delete': cache.unlink()
    elif damage=='corrupt':cache.write_text('{broken')
    elif damage=='incomplete':
        data=json.loads(cache.read_text());data['entries']={};data['checksum']=checksum({});cache.write_text(json.dumps(data))
    else: atomic_write_json(cache.parent/'dirty.json',{'dirty':True})
    with_workspace=Workspace.open(root)
    try:
        assert with_workspace.repo.sessions.worked_totals()=={n.id:900}
        assert with_workspace.repo.sessions.get(s.id).summary=='Detalii'
    finally:with_workspace.close()


@pytest.mark.parametrize('damage',['delete','corrupt','incomplete','dirty'])
def test_node_index_reconciles_and_preserves_heavy_fields(tmp_path,damage):
    root=tmp_path/'ws';ws=Workspace.open(root,create=True)
    n=ws.create_node(Kind.TASK,'T',description='Descriere',checklist=[{'text':'Pas','done':False}])
    ws.close();cache=root/'_system/cache/nodes.json'
    if damage=='delete':cache.unlink()
    elif damage=='corrupt':cache.write_text('[]')
    elif damage=='incomplete':
        data=json.loads(cache.read_text());data['nodes']={};data['checksum']=checksum({});cache.write_text(json.dumps(data))
    else:atomic_write_json(cache.parent/'nodes-dirty.json',{'dirty':True})
    ws=Workspace.open(root)
    try:
        assert ws.get(n.id).checklist[0].text=='Pas'
        assert ws.get_description(n.id)=='Descriere'
    finally:ws.close()


def test_reopen_keeps_payloads_lazy_and_never_drops_fields(tmp_path,monkeypatch):
    root=tmp_path/'ws';ws=Workspace.open(root,create=True)
    n=ws.create_node(Kind.TASK,'Închis',description='Conținut',status=Status.DONE,checklist=[{'text':'Important'}],custom_field={'keep':1})
    session(ws,n.id);ws.close()
    ws=Workspace.open(root)
    try:
        cached=ws.get(n.id)
        assert isinstance(cached,NavigationNode) and cached._full is None
        assert n.id not in ws.repo.active_task_ids
        assert Queries(ws).tasks(open_only=True)==[]
        assert cached._full is None
        ws.update_node(n.id,status=Status.TODO)
        assert n.id in ws.repo.active_task_ids
        assert ws.get(n.id).checklist[0].text=='Important'
        assert ws.get(n.id).model_extra['custom_field']=={'keep':1}
        assert ws.get_description(n.id)=='Conținut'
        assert len(SessionService(ws).for_node(n.id))==1
    finally:ws.close()


def test_external_edit_detected_on_reopen_reload_and_write(tmp_path):
    root=tmp_path/'ws';ws=Workspace.open(root,create=True)
    n=ws.create_node(Kind.TASK,'T');s=session(ws,n.id);ws.close()
    path=next((root/'nodes').glob('*/node.json'));data=json.loads(path.read_text());data['title']='Extern';atomic_write_json(path,data)
    ws=Workspace.open(root)
    try:
        assert ws.get(n.id).title=='Extern'
        data['title']='Nou extern';atomic_write_json(path,data)
        with pytest.raises(ExternalModificationError):ws.rename(n.id,'Conflict')
        # Closing must not bless a newer external stamp with old navigation metadata.
        ws.close();ws=Workspace.open(root)
        assert ws.get(n.id).title=='Nou extern'
        record=ws.repo.sessions.get(s.id)
        sp=ws.repo.sessions._path(s.id);d=json.loads(sp.read_text());d['actual_seconds']=1800;atomic_write_json(sp,d)
        with pytest.raises(ExternalModificationError):ws.repo.sessions.save(record)
        ws.reload()
        assert ws.repo.sessions.worked_totals()[n.id]==1800
    finally:ws.close()


def test_read_only_never_writes_cache(tmp_path):
    root=tmp_path/'ws';ws=Workspace.open(root,create=True)
    n=ws.create_node(Kind.TASK,'T');session(ws,n.id);ws.close()
    shutil.rmtree(root/'_system/cache')
    ws=Workspace.open(root,read_only=True)
    before={p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    ws.repo.sessions.worked_totals();ws.list_history(n.id);ws.reload()
    with pytest.raises(ReadOnlyError):session(ws,n.id)
    ws.close()
    after={p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    assert before==after


def test_title_edit_does_not_recalculate_historical_aggregates(ws,monkeypatch):
    n=ws.create_node(Kind.TASK,'T');session(ws,n.id)
    q=Queries(ws);progress=q.progress_map();worked=q.worked_map()
    before=ws.repo.index_path.read_bytes()
    ws.rename(n.id,'Alt titlu')
    assert q.progress_map() is progress
    assert q.worked_map() is worked
    assert ws.repo.index_path.read_bytes()==before


def test_period_totals_equal_full_scan_and_include_closed(ws):
    project=ws.create_node(Kind.PROJECT,'P');a=ws.create_node(Kind.TASK,'A',project.id);b=ws.create_node(Kind.TASK,'B',project.id)
    session(ws,a.id,days=1);session(ws,b.id,days=2,seconds=1800);session(ws,b.id,days=150)
    ws.update_node(b.id,status=Status.DONE)
    data=activity_ledger(ws,30)
    assert data['worked']==2700 and data['planned']==3600
    assert any(s.node_id==b.id for s,n,p in data['sessions'])
    assert activity_ledger(ws,None)['worked']==3600
    ws.move(a.id,None);assert ws.nearest_project(a.id) is None
    ws.trash(a.id);ws.restore(a.id)
    assert activity_ledger(ws,30)['worked']==2700
    ws.repo.sessions.delete(next(s.id for s in SessionService(ws).for_node(b.id) if s.actual_seconds==1800))
    assert activity_ledger(ws,30)['worked']==900


def test_active_context_reopen_and_cache_deletion(ws):
    parent=ws.create_node(Kind.TASK,'P',status=Status.DONE)
    child=ws.create_node(Kind.TASK,'C',parent.id)
    assert parent.id in ws.active_context_ids()
    ws.update_node(child.id,status=Status.DONE)
    assert parent.id not in ws.active_context_ids()
    ws.update_node(child.id,status=Status.TODO)
    assert {parent.id,child.id}<=ws.active_context_ids()
    ws.archive(child.id);assert Queries(ws).tasks(open_only=True)==[]
    ws.unarchive(child.id);assert child.id in {n.id for n in Queries(ws).tasks(open_only=True)}


def test_hidden_tabs_do_not_read_ledgers_and_drafts_survive(ui,monkeypatch):
    from focusdesk.ui.tab_journal import JournalTab
    calls=[]
    original=JournalTab.load
    monkeypatch.setattr(JournalTab,'load',lambda self,node:(calls.append(node.id),original(self,node))[1])
    other=ui.ws.create_node(Kind.TASK,'Alt task');ui.select_node(other.id)
    assert calls==[]
    details=ui.inspector.tab_by_title('Detalii');details.editor.text.insert('end-1c','Ciornă')
    ui.refresh_all();ui.root.update()
    assert 'Ciornă' in details.editor.get() and calls==[]
    ui.inspector.show_tab('Activitate');ui.root.update()
    assert calls==[other.id]


def test_incremental_rows_keep_widget_selection_and_page_order(ui):
    from focusdesk.ui.tree_rows import sync_rows
    from tkinter import ttk
    tv=ttk.Treeview(ui.root,columns=('value',))
    rows=[('',f'row{i}',dict(text=f'{i:04d}',values=(str(i),))) for i in range(450)]
    sync_rows(tv,rows,batch=50)
    assert len(tv.get_children())==50
    while tv._rows_job:ui.root.update()
    tv.selection_set('row200');tv.item('row200',open=True)
    sync_rows(tv,[('',iid,dict(text='nou' if iid=='row200' else opts['text'],values=opts['values'])) for _,iid,opts in rows],batch=50)
    while tv._rows_job:ui.root.update()
    assert tv.selection()==('row200',)
    assert tv.item('row200','open')
    assert tv.get_children()==tuple(f'row{i}' for i in range(450))


def test_f5_keeps_draft_and_external_conflict(ui,monkeypatch):
    nid=ui.selected_id
    details=ui.inspector.tab_by_title('Detalii')
    details.editor.text.insert('end-1c','Ciornă locală')
    ui.root.update()
    description=ui.ws.node_dir(nid)/'description.md'
    description.write_text('Modificare externă',encoding='utf-8')
    ui.reload_preserving_context();ui.root.update()
    ui.reload_preserving_context();ui.root.update()
    assert 'Ciornă locală' in details.editor.get()
    with pytest.raises(ExternalModificationError):ui.ws.set_description(nid,details.editor.get())
    assert description.read_text()=='Modificare externă'
    details.revert()


def test_interrupted_record_write_marker_rebuilds(tmp_path,monkeypatch):
    root=tmp_path/'ws';ws=Workspace.open(root,create=True)
    n=ws.create_node(Kind.TASK,'T');s=session(ws,n.id)
    ws.repo.sessions.summaries();ws.repo.sessions.flush()
    changed=ws.repo.sessions.get(s.id);changed.actual_seconds=1800
    ws.repo.sessions.save(changed)
    assert ws.repo.sessions.marker.exists()
    # Simulate a crash: release only the process lock, without cache checkpointing.
    ws.repo.lock.release()
    fresh=Workspace.open(root)
    try:assert fresh.repo.sessions.worked_totals()[n.id]==1800
    finally:fresh.close()


def test_new_deleted_external_records_reconcile_on_reload(ws):
    n=ws.create_node(Kind.TASK,'T');s=session(ws,n.id)
    assert ws.repo.sessions.worked_totals()[n.id]==900
    ws.repo.sessions._path(s.id).unlink()
    start=datetime.now(timezone.utc)-timedelta(days=1)
    new=SessionRecord(node_id=n.id,start_at=start,end_at=start+timedelta(minutes=30),actual_seconds=60,status='done')
    atomic_write_json(ws.repo.sessions._path(new.id),new.model_dump(mode='json'))
    ws.reload()
    assert ws.repo.sessions.worked_totals()[n.id]==60


def test_new_workspace_records_are_indexed_as_written_without_full_rescan(ws,monkeypatch):
    nodes=[ws.create_node(Kind.TASK,f'T{i}') for i in range(10)]
    for n in nodes:session(ws,n.id)
    def forbidden(*a,**kw):raise AssertionError('No full record rescan during selection')
    monkeypatch.setattr('focusdesk.storage.records.read_json',forbidden)
    assert len(SessionService(ws).for_node(nodes[0].id))==1
    assert len(ws.list_history(nodes[0].id))==1


def test_interval_index_includes_sessions_spanning_period(ws):
    n=ws.create_node(Kind.TASK,'T')
    start=datetime.now(timezone.utc)
    s=SessionRecord(node_id=n.id,start_at=start-timedelta(days=2),end_at=start+timedelta(days=2),status='planned')
    ws.repo.sessions.save(s)
    assert [record.id for record in SessionService(ws).between(start,start+timedelta(hours=1))]==[s.id]
    assert SessionService(ws).between(start+timedelta(days=3),start+timedelta(days=4))==[]


def test_description_search_refreshes_after_reload(ws):
    import os
    n=ws.create_node(Kind.TASK,'T',description='conținut vechi')
    q=Queries(ws);assert q.search('vechi')[0].id==n.id
    path=ws.node_dir(n.id)/'description.md';stamp=path.stat()
    path.write_text('conținut nou!!',encoding='utf-8')
    os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
    ws.reload()
    assert q.search('nou!!')[0].id==n.id
    assert q.search('vechi')==[]
