"""Real Tk task space: shared state, reversible navigation/focus and safety."""
import tkinter as tk
from types import SimpleNamespace
from pathlib import Path
import pytest
from focusdesk.domain.models import Kind, Status


def opened(ui):
    ui.root.deiconify();ui.root.update()
    assert ui.open_task_space()
    ui.root.update()
    return ui.task_space


def test_open_edit_save_back_restores_list_context(ui):
    for i in range(40):ui.ws.create_node(Kind.TASK,f'Task {i:02d}')
    ui.show_view('tasks');ui.tasklist.requester_var.set('');ui.tasklist.text_var.set('Task');ui.tasklist.refresh()
    task=next(n for n in ui.ws.nodes.values() if n.title=='Task 20')
    ui.select_node(task.id);ui.tasklist.select(task.id)
    ui.root.deiconify();ui.root.update();ui.tasklist.tv.yview_moveto(.4)
    ui.root.update();view=ui.current_view;before=ui.tasklist.tv.yview()[0]
    space=opened(ui)
    space.editor.replace('1.0','end-1c','# Document nou\n\nȘțâîă')
    assert space.details.desc.get('1.0','end-1c')==space.editor.get()
    assert space.is_dirty() and 'nesalvate' in space.state.cget('text')
    assert space.save()
    assert ui.ws.get_description(task.id)=='# Document nou\n\nȘțâîă'
    assert space.back();ui.root.update()
    assert ui.current_view==view and ui.selected_id==task.id
    assert ui.tasklist.text_var.get()=='Task' and ui.tasklist.tv.selection()==(task.id,)
    assert abs(ui.tasklist.tv.yview()[0]-before)<.04


def test_unsaved_same_task_can_return_to_inspector_without_copy_or_prompt(ui,monkeypatch):
    details=ui.inspector.tab_by_title('Detalii')
    details.editor.replace('1.0','end-1c','Ciornă din inspector')
    space=opened(ui)
    assert space.editor.get()=='Ciornă din inspector'
    space.editor.text.insert('end-1c',' și din pagină');ui.root.update()
    monkeypatch.setattr('focusdesk.ui.app.ask_choice',lambda *a,**k:pytest.fail('Same-buffer back must not prompt'))
    assert space.back()
    assert details.editor.get()=='Ciornă din inspector și din pagină' and details.is_dirty()
    assert ui.ws.get_description(ui.selected_id)=='Descriere locală'


def test_child_workspace_and_back_restore_document_scroll(ui):
    parent=ui.selected_id
    ui.ws.set_description(parent,'\n'.join(f'Linie {i}' for i in range(200)))
    child=ui.ws.create_node(Kind.TASK,'Subtask',parent,description='Descriere copil')
    ui.inspector.load(parent)
    space=opened(ui);space.editor.text.yview_moveto(.55);ui.root.update()
    before=space.editor.text.yview()[0]
    steps=space.sections['Pași'];steps.tv.selection_set(child.id);steps._open();ui.root.update()
    assert space.node_id==child.id and space.editor.get()=='Descriere copil'
    assert space.back();ui.root.update()
    assert space.node_id==parent and abs(space.editor.text.yview()[0]-before)<.04


def test_focus_restores_panes_sashes_tabs_and_does_not_control_timer(ui):
    space=opened(ui)
    ui.timer.start(space.node_id);ui.root.update()
    sid=ui.timer.state.session_id
    ui.paned.sashpos(0,195)
    space.nb.select(1);space.body.sashpos(0,520)
    layout=space.layout();split=space.body.sashpos(0)
    space.toggle_focus();ui.root.update()
    assert ui.paned.panes()==(str(ui.center),)
    assert ui.timer.active and ui.timer.running and ui.timer.state.session_id==sid
    assert 'Ieși' in space.focus_btn.cget('text')
    space.exit_focus();ui.root.update()
    assert ui.paned.panes()==layout['panes']
    assert [ui.paned.sashpos(i) for i in range(len(layout['sashes']))]==layout['sashes']
    assert space.nb.index(space.nb.select())==1 and space.body.sashpos(0)==split
    assert ui.timer.running and ui.timer.state.session_id==sid
    ui.timer.discard()


def test_focus_child_back_can_still_exit_focus(ui):
    parent=ui.selected_id;child=ui.ws.create_node(Kind.TASK,'Copil',parent)
    space=opened(ui);space.toggle_focus();ui.root.update()
    assert ui.open_task_space(child.id)
    assert space.back();ui.root.update()
    assert space.node_id==parent and space.focus_layout is not None
    space.exit_focus();ui.root.update()
    assert str(ui.sidebar) in ui.paned.panes()


def test_ctrl_s_saves_shared_next_note_and_checklist(ui):
    space=opened(ui);node=space.node_id
    space.editor.replace('1.0','end-1c','Salvare din pagină')
    space.details.vars['next'].set('Pas următor')
    journal=space.sections['Activitate'];journal.entry.insert('1.0','Notiță comună');journal.kind_var.set('Progres')
    space.sections['Pași'].check_var.set('Verifică datele')
    space.editor.text.focus_force();ui.root.update();space.editor.text.event_generate('<Control-s>');ui.root.update()
    assert ui.ws.get_description(node)=='Salvare din pagină'
    assert ui.ws.get(node).next_action=='Pas următor'
    assert ui.ws.get(node).checklist[0].text=='Verifică datele'
    assert ui.ws.list_notes(node)[0].text=='Notiță comună' and ui.ws.list_notes(node)[0].kind=='progress'
    assert not space.is_dirty()


def test_cancel_navigation_workspace_change_and_close_protect_draft(ui,tmp_path,monkeypatch):
    space=opened(ui);space.editor.replace('1.0','end-1c','Ciornă')
    monkeypatch.setattr('focusdesk.ui.app.ask_choice',lambda *a,**k:'cancel')
    ui.show_view('calendar');assert ui.current_view=='task_space'
    assert not ui.open_workspace(tmp_path/'other',create=True)
    ui.on_close();assert ui.root.winfo_exists()
    assert space.editor.get()=='Ciornă'


def test_read_only_task_space_is_usable_without_writes(ui):
    node=ui.selected_id;before=ui.ws.get_description(node)
    ui.ws.repo.read_only=True
    ui.inspector.load(node)
    space=opened(ui)
    assert str(space.editor.text.cget('state'))=='disabled'
    assert str(space.next_entry.cget('state'))=='disabled'
    assert space.save_btn.instate(['disabled'])
    space.editor.replace('1.0','end-1c','Nepermis')
    assert space.editor.get()==before and not space.save()
    assert ui.ws.get_description(node)==before
    ui.ws.repo.read_only=False


def test_removed_task_keeps_recoverable_draft_and_can_discard(ui,monkeypatch):
    space=opened(ui);node=space.node_id
    space.editor.replace('1.0','end-1c','Ciornă recuperabilă')
    ui.ws.trash(node);ui.root.update()
    assert ui.current_view=='task_space' and 'indisponibil' in space.title.cget('text')
    assert space.editor.get()=='Ciornă recuperabilă' and not space.save()
    space.copy_description();assert ui.root.clipboard_get()=='Ciornă recuperabilă'
    monkeypatch.setattr('focusdesk.ui.app.ask_choice',lambda *a,**k:'discard')
    assert space.back();ui.root.update()
    assert ui.current_view=='tasks'


def test_archived_task_and_failed_save_keep_page_and_draft(ui,monkeypatch):
    space=opened(ui);node=space.node_id
    space.editor.replace('1.0','end-1c','Nesalvat')
    ui.ws.archive(node);ui.root.update()
    assert 'Arhivat' in space.summary.cget('text') and space.editor.get()=='Nesalvat'
    monkeypatch.setattr(ui,'run_write',lambda *a,**k:False)
    assert not space.save() and space.is_dirty()
    assert 'eșuat' in space.state.cget('text')


def test_double_click_keeps_original_tree_and_inspector_behavior(ui,monkeypatch):
    called=[];monkeypatch.setattr(ui,'focus_inspector',lambda:called.append('inspector'))
    monkeypatch.setattr(ui.tasklist.tv,'identify_region',lambda x,y:'cell')
    ui.tasklist._on_double(SimpleNamespace(x=0,y=0))
    assert called==['inspector'] and ui.current_view!='task_space'
    monkeypatch.setattr(ui.tasklist.tv,'identify_region',lambda x,y:'tree')
    ui.tasklist._on_double(SimpleNamespace(x=0,y=0));assert called==['inspector']


def test_minimum_layout_many_subtasks_and_nonmodal_focus_shortcut(ui):
    parent=ui.selected_id
    for i in range(45):ui.ws.create_node(Kind.TASK,f'Pas {i:02d}',parent)
    space=opened(ui);ui.root.geometry('1100x700');ui.root.update()
    assert len(space.sections['Pași'].tv.get_children())==45
    assert ui.root.grab_current() is None
    assert space.editor.text.winfo_height()>100
    space.editor.text.focus_force();space.editor.text.event_generate('<F11>');ui.root.update()
    assert space.focus_layout is not None
    space.editor.text.event_generate('<F11>');ui.root.update()
    assert space.focus_layout is None and str(ui.sidebar) in ui.paned.panes()


def test_deleted_then_restored_task_retains_draft_and_shared_note(ui):
    space=opened(ui);node=space.node_id
    space.editor.replace('1.0','end-1c','Descriere de recuperat')
    space.sections['Activitate'].entry.insert('1.0','Notiță de recuperat')
    ui.ws.trash(node);ui.root.update()
    assert space.is_dirty()
    ui.ws.restore(node);ui.root.update()
    assert space.editor.get()=='Descriere de recuperat'
    assert space.sections['Activitate'].entry.get('1.0','end-1c')=='Notiță de recuperat'
    assert ui.selected_id==node and space.save()
    assert ui.ws.get_description(node)=='Descriere de recuperat'
    assert ui.ws.list_notes(node)[0].text=='Notiță de recuperat'


def test_focus_route_change_restores_sidebar_and_preserves_timer(ui):
    space=opened(ui);node=space.node_id
    ui.timer.start(node);sid=ui.timer.state.session_id
    space.toggle_focus();ui.root.update()
    ui.show_view('calendar');ui.root.update()
    assert str(ui.sidebar) in ui.paned.panes() and space.focus_layout is None
    assert ui.timer.active and ui.timer.state.session_id==sid
    ui.timer.discard()


def test_back_restores_layout_from_inspector_and_does_not_reset_scroll_on_save(ui):
    node=ui.selected_id
    ui.ws.set_description(node,'\n'.join(f'Rând {i}' for i in range(250)))
    ui.inspector.load(node)
    ui.root.deiconify();ui.root.update()
    ui.paned.sashpos(0,205);ui.paned.sashpos(1,980);ui.root.update()
    layout=ui.task_space.layout()
    space=opened(ui);space.editor.text.yview_moveto(.6);ui.root.update()
    before=space.editor.text.yview()[0]
    space.details.vars['next'].set('Pas nou')
    assert space.save();ui.root.update()
    assert abs(space.editor.text.yview()[0]-before)<.03
    assert space.back();ui.root.update()
    assert ui.paned.panes()==layout['panes']
    assert [ui.paned.sashpos(i) for i in range(len(layout['sashes']))]==layout['sashes']


def test_readonly_to_editable_reopens_metadata_and_space(ui):
    node=ui.selected_id;ui.ws.repo.read_only=True;ui.inspector.load(node)
    space=opened(ui)
    ui.ws.repo.read_only=False;ui.inspector.load(node);space.refresh()
    assert str(space.editor.text.cget('state'))=='normal'
    assert str(space.next_entry.cget('state'))=='normal'
    assert str(space.details.title_entry.cget('state'))=='normal'
    space.editor.replace('1.0','end-1c','Editabil din nou')
    assert space.save()


def test_workspace_change_clears_history_and_shared_undo(ui,tmp_path,monkeypatch):
    old=ui.selected_id
    space=opened(ui);space.editor.replace('1.0','end-1c','Ciornă înainte de schimbare')
    monkeypatch.setattr('focusdesk.ui.app.ask_choice',lambda *a,**k:'save')
    assert ui.open_workspace(tmp_path/'new-workspace',create=True)
    assert space.history==[] and space.positions=={} and not space.active
    new=ui.ws.create_node(Kind.TASK,'Task nou',description='Text nou')
    ui.select_node(new.id,reveal=True);assert ui.open_task_space(new.id)
    space.editor.undo()
    assert space.editor.get()=='Text nou' and space.node_id!=old


def test_panel_visibility_restored_after_focus_and_primary_navigation_is_available(ui):
    space=opened(ui)
    assert not ui.sidebar.views.selection()
    space.nb.select(2);space.toggle_panel()
    assert str(space.secondary) not in space.body.panes()
    space.toggle_focus();assert str(space.secondary) in space.body.panes()
    space.exit_focus();assert str(space.secondary) not in space.body.panes()
    assert space.nb.index(space.nb.select())==2
    ui.show_view('tasks');ui.root.update()
    assert ui.current_view=='tasks' and str(ui.sidebar) in ui.paned.panes()
