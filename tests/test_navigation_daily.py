"""Real UI daily flows plus compatibility and deterministic activity totals."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import pytest

from focusdesk.config import AppConfig
from focusdesk.domain.models import Kind, Status
from focusdesk.domain.labels import STATUS_LABELS, VISIBLE_STATUSES
from focusdesk.domain.session import SessionRecord
from focusdesk.domain.colleagues import Colleague
from focusdesk.services.queries import Queries
from focusdesk.services.activity import activity_ledger
from focusdesk.ui.status_visuals import node_icon


def wait_activity(ui):
    import time
    deadline=time.monotonic()+5
    while True:
        ui.root.update()
        job=ui.activity_page._job
        if job is None or job.done:return
        assert time.monotonic()<deadline,'Activity report did not finish'
        time.sleep(.01)


def test_legacy_status_display_filter_no_move_or_rewrite(ws):
    folder=ws.create_node(Kind.FOLDER,'Categorie')
    old=ws.create_node(Kind.TASK,'Vechi',folder.id,status=Status.INBOX)
    new=ws.quick_capture('Nou')
    q=Queries(ws)
    assert new.status==Status.TODO
    assert STATUS_LABELS[old.status]==STATUS_LABELS[new.status]=='De făcut'
    assert [STATUS_LABELS[s] for s in VISIBLE_STATUSES].count('De făcut')==1
    assert {n.id for n in q.filter(q.tasks(),status=Status.TODO)}=={old.id,new.id}
    root=ws.root;ws.close()
    from focusdesk.services.workspace import Workspace
    opened=Workspace.open(root)
    try:
        assert opened.get(old.id).status==Status.INBOX and opened.get(old.id).parent_id==folder.id
    finally:opened.close()


def test_project_membership_and_requester_filters(ws):
    folder=ws.create_node(Kind.FOLDER,'Folder')
    independent=ws.create_node(Kind.TASK,'Independent',folder.id,requested_by=Colleague(name='Ana Pop',code='ana'))
    project=ws.create_node(Kind.PROJECT,'Proiect')
    legacy=ws.create_node(Kind.TASK,'Legacy în proiect',project.id,status=Status.INBOX)
    q=Queries(ws)
    assert [n.id for n in q.filter(q.tasks(),no_project=True)]==[independent.id]
    assert [n.id for n in q.filter(q.tasks(),requester='ANA')]==[independent.id]
    # A related link is not ownership; only a real move changes membership.
    ws.add_related(project.id,independent.id)
    assert q.filter([independent],no_project=True)
    ws.move(independent.id,project.id)
    assert not q.filter([ws.get(independent.id)],no_project=True)
    assert {n.id for n in q.filter(q.tasks(),project_id=project.id)}=={legacy.id,independent.id}


def test_activity_uses_saved_seconds_once_and_separates_planned(ws):
    project=ws.create_node(Kind.PROJECT,'Proiect')
    parent=ws.create_node(Kind.TASK,'Părinte',project.id)
    child=ws.create_node(Kind.TASK,'Copil',parent.id)
    now=datetime.now(timezone.utc)
    for node,seconds in ((parent,120),(child,240)):
        ws.repo.sessions.save(SessionRecord(node_id=node.id,start_at=now-timedelta(hours=1),end_at=now,
            status='done',actual_seconds=seconds,started_actual_at=now))
    ws.repo.sessions.save(SessionRecord(node_id=child.id,start_at=now+timedelta(days=1),end_at=now+timedelta(days=1,hours=2)))
    all_data=activity_ledger(ws,None)
    assert all_data['worked']==360
    assert all_data['planned']==4*3600
    assert all_data['projects'][project.id]['worked']==360
    assert sum(d['worked'] for d in all_data['days'].values())==360
    assert len(all_data['sessions'])==3


@pytest.mark.parametrize('view',['inbox','waiting','overdue','completed','Asistent','tree:old'])
def test_old_navigation_preferences_are_safe(view):
    config=AppConfig(last_view=view,inspector_tab='Jurnal')
    assert config.last_view=='tasks' and config.inspector_tab=='Activitate'
    assert AppConfig(inspector_tab='Subtask-uri').inspector_tab=='Subtaskuri'


def test_four_destinations_and_task_tabs(ui):
    assert list(ui.sidebar.views.get_children())==['today','tasks','calendar','activity']
    assert [ui.inspector.nb.tab(tab,'text') for tab in ui.inspector.nb.tabs()]==['Detalii','Subtaskuri','Activitate','Fișiere','Planificare','Versiuni']
    for view in ('today','tasks','calendar','activity'):
        ui.show_view(view)
        ui.root.update()
        assert ui.current_view==view
        assert str(ui.inspector) not in ui.paned.panes()
    ui.select_node(next(iter(ui.ws.nodes)),reveal=True)
    assert str(ui.inspector) in ui.paned.panes()


def test_old_inbox_ui_save_is_inert_and_only_one_todo_option(ui):
    old=ui.ws.create_node(Kind.TASK,'Legacy',status=Status.INBOX)
    ui.select_node(old.id,reveal=True);ui.root.update()
    tab=ui.inspector.tab_by_title('Detalii')
    assert tab.vars['status'].get()=='De făcut'
    assert list(tab.status_box.cget('values')).count('De făcut')==1
    assert str(node_icon(ui.root,old))==str(node_icon(ui.root,old.model_copy(update={'status':Status.TODO})))
    tab.vars['next'].set('Următorul pas')
    assert tab.save() and ui.ws.get(old.id).status==Status.INBOX
    ui.show_view('inbox')
    assert ui.current_view=='tasks' and old.id in ui.tasklist.tv.get_children()


def test_independent_to_project_subtask_timer_finish_reopen_archive(ui,monkeypatch):
    from types import SimpleNamespace
    import focusdesk.ui.app as app_module
    gesture_time=[100.0]
    monkeypatch.setattr(app_module,'time',SimpleNamespace(monotonic=lambda:gesture_time[0]))
    ui.show_view('tasks');ui.tasklist.add_var.set('Independent nou')
    ui.tasklist._quick_add(False)
    task=next(n for n in ui.ws.nodes.values() if n.title=='Independent nou')
    assert task.parent_id is None and task.status==Status.TODO
    project=ui.ws.create_node(Kind.PROJECT,'Proiect nou')
    ui.ws.move(task.id,project.id)
    child=ui.ws.create_node(Kind.TASK,'Pas mic',task.id)
    ui.select_node(task.id,reveal=True);ui.root.update()
    ui.timer.start(task.id);ui.update_session_buttons()
    assert ui.inspector.start_btn.cget('text')=='Pauză'
    ui.inspector.start_btn.invoke()
    assert not ui.timer.running and ui.inspector.start_btn.cget('text')=='Continuă'
    gesture_time[0]+=1  # a distinct Continue gesture, after the double-click guard
    ui.inspector.start_btn.invoke()
    assert ui.timer.running
    ui.timer.stop(summary='Sesiune verificată',next_action='Continuă verificarea')
    ui.ws.update_node(child.id,status=Status.DONE)
    assert ui.ws.get(task.id).status!=Status.DONE
    ui.refresh_all();ui.inspector.reopen_btn.invoke();ui.root.update()
    assert ui.ws.get(task.id).status==Status.DONE
    ui.inspector.reopen_btn.invoke();ui.root.update()
    assert ui.ws.get(task.id).status==Status.TODO
    ui.ws.archive(task.id)
    ui.show_view('archive');ui.root.update()
    assert task.id in {n.id for n in ui.tasklist._shown}
    ui.ws.unarchive(task.id)
    ui.ws.trash(child.id);ui.ws.restore(child.id)
    assert child.id in ui.ws.nodes
    ui.show_view('activity');ui.activity_page.period.set('Tot istoricul');ui.activity_page.refresh();wait_activity(ui)
    assert ui.activity_page.tables['Sesiuni'].get_children()


def test_task_note_draft_obeys_selection_confirmation(ui,monkeypatch):
    original=ui.selected_id
    journal=ui.inspector.tab_by_title('Activitate')
    journal.entry.insert('1.0','Notiță nesalvată')
    other=ui.ws.create_node(Kind.TASK,'Alt task')
    monkeypatch.setattr('focusdesk.ui.app.ask_choice',lambda *a,**k:'cancel')
    ui.select_node(other.id)
    assert ui.selected_id==original and journal.is_dirty()
    monkeypatch.setattr('focusdesk.ui.app.ask_choice',lambda *a,**k:'save')
    ui.select_node(other.id)
    assert ui.selected_id==other.id
    assert ui.ws.list_notes(original)[0].text=='Notiță nesalvată'
    assert not ui.ws.list_notes(other.id)


def test_refresh_keeps_task_selection_scroll_and_daily_widgets(ui):
    for i in range(70):ui.ws.create_node(Kind.TASK,f'Task {i:03d}')
    ui.show_view('tasks');ui.root.deiconify();ui.root.update()
    tv=ui.tasklist.tv
    nid=next(n.id for n in ui.ws.nodes.values() if n.title=='Task 040')
    tv.selection_set(nid);tv.yview_moveto(.45);ui.root.update()
    before=tv.yview()[0]
    ui.refresh_all();ui.root.update()
    assert tv.selection()==(nid,) and abs(tv.yview()[0]-before)<.03
    ui.show_view('today');ui.root.update()
    widget=ui.today.priorities
    ui.today.sf.canvas.yview_moveto(.2)
    ui.today.refresh()
    assert ui.today.priorities is widget


def test_requester_and_no_project_ui_filters(ui):
    project=ui.ws.create_node(Kind.PROJECT,'Proiect filtrat')
    a=ui.ws.create_node(Kind.TASK,'Task independent',requested_by=Colleague(name='Mara Test',code='mara'))
    b=ui.ws.create_node(Kind.TASK,'Task în proiect',project.id,requested_by=Colleague(name='Mara Test',code='mara'))
    ui.show_view('tasks');ui.tasklist.proj_var.set('Fără proiect');ui.tasklist.requester_var.set('mara');ui.tasklist.refresh()
    assert [n.id for n in ui.tasklist._shown]==[a.id]
    ui.tasklist.proj_var.set(project.title);ui.tasklist.refresh()
    assert [n.id for n in ui.tasklist._shown]==[b.id]


def test_quick_filters_and_readable_empty_states(ui):
    waiting=ui.ws.create_node(Kind.TASK,'În așteptare',status=Status.WAITING)
    done=ui.ws.create_node(Kind.TASK,'Finalizat',status=Status.DONE)
    ui.quick_tasks('waiting');assert [n.id for n in ui.tasklist._shown]==[waiting.id]
    ui.quick_tasks('done');assert [n.id for n in ui.tasklist._shown]==[done.id]
    ui.quick_tasks('all');assert all(n.status!=Status.DONE for n in ui.tasklist._shown)
    ui.show_view('activity');wait_activity(ui);assert 'Nu există sesiuni' in ui.activity_page.empty.cget('text')


def test_today_controls_actual_timer_and_cancelled_session_cannot_start(ui,monkeypatch):
    from types import SimpleNamespace
    import focusdesk.ui.app as app_module
    gesture_time=[100.0]
    monkeypatch.setattr(app_module,'time',SimpleNamespace(monotonic=lambda:gesture_time[0]))
    task=ui.ws.get(ui.selected_id)
    ui.timer.start(task.id);ui.show_view('today');ui.today.update_timer()
    assert ui.today.timer_toggle.cget('text')=='Pauză'
    ui.today.timer_toggle.invoke()
    assert ui.today.timer_toggle.cget('text')=='Continuă' and not ui.timer.running
    gesture_time[0]+=1  # a distinct Continue gesture
    ui.today.timer_toggle.invoke();assert ui.timer.running
    ui.timer.stop();ui.today.update_timer()
    assert str(ui.today.timer_toggle.cget('state'))=='disabled'


def test_old_tab_preference_and_note_scroll_survive_refresh(ui):
    task=ui.selected_id
    ui.inspector.load(None)
    ui.config.inspector_tab='Activitate'
    ui.inspector.load(task)
    assert ui.inspector.nb.tab(ui.inspector.nb.select(),'text')=='Activitate'
    journal=ui.inspector.tab_by_title('Jurnal')
    for i in range(15):ui.ws.add_note(task, f'Notiță {i}\n' * 4)
    ui.root.deiconify();ui.inspector.load(task);ui.root.update()
    journal.text.yview_moveto(.4);before=journal.text.yview()[0]
    ui.refresh_all();ui.root.update()
    assert abs(journal.text.yview()[0]-before)<.05


def test_combobox_events_apply_filters_and_closed_toggle_is_consistent(ui):
    done=ui.ws.create_node(Kind.TASK,'Task finalizat',status=Status.DONE)
    ui.show_view('tasks')
    ui.tasklist.status_var.set('Finalizat')
    ui.tasklist.status_box.event_generate('<<ComboboxSelected>>')
    assert ui.tasklist.closed_var.get()
    assert [n.id for n in ui.tasklist._shown]==[done.id]
    ui.tasklist.closed_var.set(False);ui.tasklist._toggle_closed()
    assert done.id not in [n.id for n in ui.tasklist._shown]


def test_background_status_change_is_not_overwritten_by_description_save(ui):
    task=ui.selected_id
    details=ui.inspector.tab_by_title('Detalii')
    details.editor.replace('1.0','end-1c','Documentare nesalvată')
    ui.ws.update_node(task,status=Status.IN_PROGRESS)
    ui.refresh_all()
    assert details.editor.get()=='Documentare nesalvată'
    assert details.save()
    assert ui.ws.get(task).status==Status.IN_PROGRESS
    assert ui.ws.get_description(task)=='Documentare nesalvată'


def test_cancel_navigation_from_secondary_archive_keeps_unsaved_description(ui,monkeypatch):
    task=ui.selected_id
    ui.ws.archive(task)
    ui.show_view('archive');ui.select_node(task);ui.root.update()
    details=ui.inspector.tab_by_title('Detalii')
    details.editor.replace('1.0','end-1c','Ciornă în arhivă')
    other=ui.ws.create_node(Kind.TASK,'Alt task')
    monkeypatch.setattr('focusdesk.ui.app.ask_choice',lambda *a,**k:'cancel')
    ui.select_node(other.id);ui.root.update()
    assert ui.current_view=='archive' and ui.selected_id==task
    assert details.editor.get()=='Ciornă în arhivă'
