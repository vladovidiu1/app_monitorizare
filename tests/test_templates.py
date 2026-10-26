from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime,timedelta,timezone
from focusdesk.domain.session import SessionRecord
import pytest
from focusdesk.domain.common import new_id
from focusdesk.domain.models import Kind, Status, Priority
from focusdesk.domain.templates import StructureTemplate,TemplateItem,MAX_TEMPLATE_BYTES
from focusdesk.errors import ValidationError,StorageError,ReadOnlyError,ExternalModificationError
from focusdesk.services.templates import parse_template,digest
from focusdesk.services.workspace import Workspace
from focusdesk.services.backup import create_backup,restore_backup_to_folder


def sample():
    return StructureTemplate(name='Test',variables=['nume'],items=[
        TemplateItem(key='root',kind=Kind.PROJECT,title='{{nume}}',description='**{{nume}}**\n```python\nx = {"a": 1}\n{{necunoscut}}\n{{nume}}\n```'),
        TemplateItem(key='first',parent='root',title='Pregătire',checklist=['Pas unu'],estimated_minutes=30),
        TemplateItem(key='second',parent='first',title='Detaliu {{nume}}',depends_on=['last'],related=['root']),
        TemplateItem(key='last',parent='root',title='Validare')])

def options(**extra):return dict(title='Proiect {{nume}}',values={'nume':'Nou'},request_id=new_id(),**extra)

def test_multilevel_capture_create_and_excluded_metadata(ws):
    external=ws.create_node(Kind.TASK,'Outside')
    root=ws.create_node(Kind.PROJECT,'Source',description='# Date sursă')
    a=ws.create_node(Kind.TASK,'A',root.id,status=Status.DONE,estimated_minutes=60,remaining_minutes=5,
                     priority=Priority.HIGH,tags=['SAP'],next_action='Verifică',requested_by={'name':'Colegul Privat','code':'secret'},
                     checklist=[{'text':'Verificare','done':True}],due_date='2026-10-29',pinned_today='2026-10-26',
                     related_node_ids=[external.id],outlook_sync={'private':'secret'},
                     source_workspace={'path':'C:/private-code','mode':'external'},
                     attachments=[{'name':'secret.txt','mode':'managed','path':'files/secret.txt'}])
    b=ws.create_node(Kind.TASK,'B',a.id,depends_on_ids=[a.id],related_node_ids=[root.id,external.id])
    ws.add_note(a.id,'Notă privată')
    (ws.node_dir(a.id)/'files'/'secret.txt').write_text('secret')
    (ws.node_dir(a.id)/'snapshots'/'private.json').write_text('{"secret": true}')
    now=datetime.now(timezone.utc)
    worked=SessionRecord(node_id=a.id,start_at=now-timedelta(hours=1),end_at=now,status='done',actual_seconds=1800)
    ws.repo.sessions.save(worked)
    before={p.relative_to(ws.root):p.read_bytes() for p in ws.repo.nodes_dir.rglob('*') if p.is_file()}
    template=ws.templates.capture(root.id,'Structură');saved=ws.save_template(template)
    assert before=={p.relative_to(ws.root):p.read_bytes() for p in ws.repo.nodes_dir.rglob('*') if p.is_file()}
    raw=saved.model_dump_json()
    for forbidden in (root.id,a.id,b.id,external.id,'Colegul Privat','secret','Notă privată','due_date','outlook_sync','pinned_today','remaining_minutes'):
        assert forbidden not in raw
    fresh=ws.create_from_template(saved,title='Nou',request_id=new_id())
    ids=ws.subtree_ids(fresh.id);assert len(ids)==3 and not set(ids)&{root.id,a.id,b.id}
    ca=next(n for n in ws.nodes.values() if n.parent_id==fresh.id)
    cb=next(n for n in ws.nodes.values() if n.parent_id==ca.id)
    assert cb.depends_on_ids==[ca.id] and cb.related_node_ids==[fresh.id]
    assert ca.status==Status.TODO and ca.priority==Priority.HIGH and ca.estimated_minutes==60 and ca.remaining_minutes==60
    assert ca.next_action=='Verifică' and not ca.checklist[0].done
    assert ca.requested_by is None and ca.due_date is None and ca.pinned_today is None
    assert ws.list_notes(ca.id)==[] and not list((ws.node_dir(ca.id)/'files').iterdir())
    assert not ca.attachments and ca.source_workspace is None
    assert not list((ws.node_dir(ca.id)/'snapshots').iterdir())
    assert [(record.id,record.node_id,record.actual_seconds) for record in ws.repo.sessions.list_all()]==[(worked.id,a.id,1800)]


def test_variables_markdown_code_and_preview_do_not_write(ws):
    template=sample();before=set(ws.nodes)
    view=ws.templates.preview(template,title='Proiect {{nume}}',values={'nume':'A {{nume}}'})
    assert set(ws.nodes)==before
    assert view.root.title=='Proiect A {{nume}}' # one pass, never recursive
    assert 'x = {"a": 1}' in view.root.description and '{{necunoscut}}' in view.root.description
    assert '**A {{nume}}**' in view.root.description
    assert 'Detaliu A {{nume}}' in view.items[2].title
    fresh=ws.create_from_template(template,**options())
    assert '**Nou**' in ws.get_description(fresh.id)
    children=ws.children(fresh.id);first=next(n for n in children if n.title=='Pregătire');last=next(n for n in children if n.title=='Validare')
    assert ws.children(first.id)[0].depends_on_ids==[last.id]

@pytest.mark.parametrize('values',[{}, {'nume':''},{'nume':'ok','extra':'bad'},{'nume':'a'*10001}])
def test_variables_are_explicit_required_bounded(ws,values):
    with pytest.raises(ValidationError):ws.templates.preview(sample(),title='x',values=values)

@pytest.mark.parametrize('raw',[b'not json',b'{}',b'{"schema_version":2}',b'x'*(MAX_TEMPLATE_BYTES+1)])
def test_bad_imports_are_bounded_and_strict(raw):
    with pytest.raises(ValidationError):parse_template(raw)

@pytest.mark.parametrize('change',[
    lambda t:t['items'][1].update(parent='missing'),
    lambda t:t['items'][0].update(parent='second'),
    lambda t:t['items'][3].update(depends_on=['second']),
    lambda t:t['items'][1].update(related=['outside']),
    lambda t:t['items'][1].update(depends_on=['first']),
    lambda t:t['items'][1].update(source_workspace={'path':'C:/secret','mode':'external'}),
    lambda t:t['items'][1].update(id=new_id()),
    lambda t:t['items'][0].update(estimated_minutes=10),
    lambda t:t.update(variables=['nume','nume']),
])
def test_invalid_graph_and_unapproved_fields(change):
    data=sample().model_dump(mode='json');change(data)
    with pytest.raises(ValidationError):parse_template(json.dumps(data).encode())


def test_catalog_defaults_never_materialize_nodes_and_user_copies_survive(ws):
    assert not ws.nodes
    defaults=ws.templates.catalog();assert len(defaults)==4 and all(b for _,b in defaults)
    assert not ws.templates.directory.exists()
    assert {t.name for t,_ in defaults}=={'Automatizare SAP','Investigare incident','Dezvoltare aplicație Python','Task simplu'}
    assert all(i.estimated_minutes is None and not i.depends_on for t,_ in defaults for i in t.items)
    personal=ws.duplicate_template(defaults[0][0]);assert personal.id!=defaults[0][0].id
    assert not ws.nodes
    path=ws.root;ws.close();reopened=Workspace.open(path)
    try:assert any(t.id==personal.id and not b for t,b in reopened.templates.catalog())
    finally:reopened.close()


def test_edit_conflicts_duplicate_delete_export_import(ws,tmp_path):
    t=ws.save_template(sample());old=digest(t)
    changed=ws.save_template(t.model_copy(update={'name':'Editat'}),expected_hash=old)
    assert changed.revision==2
    with pytest.raises(ExternalModificationError):ws.save_template(t,expected_hash=old)
    with pytest.raises(ExternalModificationError):ws.delete_template(t,old)
    copy=ws.duplicate_template(changed);assert copy.id!=changed.id
    output=tmp_path/'one.json';ws.templates.export_file(copy,output)
    imported=ws.import_template(output);assert imported.id not in (copy.id,t.id)
    ws.delete_template(copy,digest(copy));assert not ws.templates._path(copy.id).exists()
    assert ws.templates._path(changed.id).exists()

@pytest.mark.parametrize('full',[False,True])
def test_backup_restore_templates(ws,tmp_path,full):
    saved=ws.save_template(sample());backup=create_backup(ws,full=full)
    dest=tmp_path/'restored';restore_backup_to_folder(backup.path,dest)
    other=Workspace.open(dest)
    try:assert any(t.id==saved.id and digest(t)==digest(saved) for t,b in other.templates.catalog() if not b)
    finally:other.close()


def test_idempotent_creation_even_after_restart(ws):
    t=sample();params=options();root=ws.create_from_template(t,**params)
    assert ws.create_from_template(t,**params).id==root.id and len(ws.nodes)==4
    path=ws.root;ws.close();other=Workspace.open(path)
    try:
        assert other.create_from_template(t,**params).id==root.id and len(other.nodes)==4
        with pytest.raises(ValidationError):other.create_from_template(t,**{**params,'title':'Changed'})
        other.trash(root.id)
        with pytest.raises(ValidationError):other.create_from_template(t,**params)
    finally:other.close()


def test_failure_rollback_including_partly_written_directory(ws,monkeypatch):
    survivor=ws.create_node(Kind.TASK,'Existing');original=ws.repo.create_node;calls=0
    def fail(node,description):
        nonlocal calls
        calls+=1
        result=original(node,description)
        if calls==2:raise OSError('disk full after write')
        return result
    monkeypatch.setattr(ws.repo,'create_node',fail)
    params=options()
    with pytest.raises(StorageError,match='retrase'):ws.create_from_template(sample(),**params)
    assert set(ws.nodes)=={survivor.id} and len(list(ws.repo.nodes_dir.iterdir()))==1
    assert next(o for o in ws.repo.operations.list_all() if o.id==params['request_id']).state=='rolled_back'
    with pytest.raises(StorageError):ws.create_from_template(sample(),**params)


def test_interrupted_creation_recovered_on_open(ws,monkeypatch):
    original=ws.repo.create_node;calls=0
    def interrupted(node,description):
        nonlocal calls
        calls+=1;result=original(node,description)
        if calls==2:raise KeyboardInterrupt('power loss')
        return result
    monkeypatch.setattr(ws.repo,'create_node',interrupted)
    with pytest.raises(KeyboardInterrupt):ws.create_from_template(sample(),**options())
    assert len(ws.nodes)==2
    path=ws.root;ws.close();reopened=Workspace.open(path)
    try:
        assert not reopened.nodes and not list(reopened.repo.nodes_dir.iterdir())
        assert any('șablon' in m for m in reopened.recovery_messages)
    finally:reopened.close()


def test_invalid_destination_and_readonly_legacy_workspace(ws,tmp_path):
    task=ws.create_node(Kind.TASK,'Parent')
    with pytest.raises(ValidationError):ws.create_from_template(sample(),**options(parent_id=task.id))
    path=ws.root;ws.close();ro=Workspace.open(path,read_only=True)
    try:
        assert len(ro.templates.catalog())==4 and not ro.templates.directory.exists()
        for action in [lambda:ro.save_template(sample()),lambda:ro.duplicate_template(sample()),lambda:ro.templates.capture(task.id,'x'),lambda:ro.create_from_template(sample(),**options())]:
            with pytest.raises(ReadOnlyError):action()
        assert set(ro.nodes)=={task.id}
    finally:ro.close()


def test_import_cannot_use_paths_in_json(ws,tmp_path):
    data=sample().model_dump(mode='json');data['id']='../../outside';file=tmp_path/'hostile.json';file.write_text(json.dumps(data))
    with pytest.raises(ValidationError):ws.import_template(file)
    assert not ws.templates.directory.exists()


def test_invalid_personal_file_does_not_break_existing_workspace(ws):
    ws.templates.directory.mkdir();(ws.templates.directory/'broken.json').write_text('broken')
    assert len(ws.templates.catalog())==4 and ws.templates.issues

@pytest.mark.parametrize('version',[True,1.0,'1',2])
def test_schema_version_requires_exact_supported_integer(version):
    data=sample().model_dump(mode='json');data['schema_version']=version
    with pytest.raises(ValidationError):parse_template(json.dumps(data).encode())


def test_variable_expansion_is_bounded_before_large_allocation(ws):
    template=StructureTemplate(name='T',variables=['x'],items=[TemplateItem(key='root',title='T',description='{{x}}'*1000)])
    with pytest.raises(ValueError,match='limit'):ws.templates.preview(template,title='T',values={'x':'a'*10_000})


def test_pending_rollback_is_retried_after_restart(ws,monkeypatch):
    import focusdesk.services.templates as service
    original=ws.repo.create_node;count=0
    def fail(node,description):
        nonlocal count
        result=original(node,description);count+=1
        if count==2:raise OSError('write failure')
        return result
    def denied(*args):raise PermissionError('busy')
    monkeypatch.setattr(ws.repo,'create_node',fail);monkeypatch.setattr(service,'rollback_template',denied)
    with pytest.raises(StorageError,match='redeschidere'):ws.create_from_template(sample(),**options())
    assert any(o.state=='pending' for o in ws.repo.operations.list_all())
    path=ws.root;ws.close();reopened=Workspace.open(path)
    try:assert not reopened.nodes and not list(reopened.repo.nodes_dir.iterdir())
    finally:reopened.close()


def test_capture_preserves_reordered_siblings_and_new_root_goes_last(ws):
    project=ws.create_node(Kind.PROJECT,'Source')
    first=ws.create_node(Kind.TASK,'Premier',project.id)
    second=ws.create_node(Kind.TASK,'Second',project.id)
    third=ws.create_node(Kind.TASK,'Troisième',project.id)
    ws.reorder(third.id,-1)
    saved=ws.templates.capture(project.id,'Order')
    created=ws.create_from_template(saved,title='Copied',request_id=new_id())
    assert [n.title for n in ws.children(created.id)]==[n.title for n in ws.children(project.id)]
    assert created.sort_order>project.sort_order
