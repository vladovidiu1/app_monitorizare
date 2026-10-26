"""Real Tk editing/preview and shared-buffer save/cancel regressions."""
import tkinter as tk
from datetime import timedelta, datetime, timezone
import pytest

from focusdesk.domain.models import Kind, Status
from focusdesk.ui.markdown_editor import STRUCTURED
from focusdesk.ui.status_visuals import node_icon


def details(ui, text=''):
    tab = ui.inspector.tab_by_title('Detalii')
    ui.ws.set_description(ui.selected_id, text)
    tab.load(ui.ws.get(ui.selected_id))
    ui.root.update()
    return tab


def fill(editor, text):
    editor.replace('1.0', 'end-1c', text)
    editor.text.tag_remove('sel', '1.0', 'end')


@pytest.mark.parametrize('before,after', [('**','**'), ('*','*'), ('```\n','\n```')])
def test_format_selection_and_undo_redo(ui, before, after):
    tab = details(ui, 'Țară și diacritice\nLinia a doua')
    editor = tab.editor
    editor.text.tag_add('sel', '1.0', '1.4')
    editor.wrap(before, after)
    assert editor.get().startswith(before+'Țară'+after)
    editor.undo()
    assert editor.get() == 'Țară și diacritice\nLinia a doua'
    editor.redo()
    assert editor.get().startswith(before+'Țară'+after)
    assert tab.is_dirty()


@pytest.mark.parametrize('original,expected', [
    ('- unu','- unu\n- '), ('3. pas','3. pas\n4. '), ('    - [x] bifat','    - [x] bifat\n    - [ ] '),
    ('- ', ''), ('  - [ ] ', ''), ('2. ', ''), ('    cod','    cod\n    ')])
def test_enter_continues_and_ends_lists(ui, original, expected):
    editor = details(ui, original).editor
    editor.text.mark_set('insert','end-1c')
    editor.enter()
    assert editor.get() == expected


def test_multiline_lists_indent_template_and_link(ui, monkeypatch):
    tab = details(ui, 'unu\ndoi\ntrei')
    editor = tab.editor
    editor.select_all()
    editor.numbered()
    assert editor.get() == '1. unu\n2. doi\n3. trei'
    editor.select_all()
    editor.indent()
    assert editor.get().startswith('    1. unu\n    2. doi')
    editor.indent(True)
    assert editor.get() == '1. unu\n2. doi\n3. trei'
    editor.template()
    assert editor.get() == '1. unu\n2. doi\n3. trei'  # never overwrite
    fill(editor, '')
    editor.template()
    assert editor.get() == STRUCTURED
    fill(editor, 'document')
    editor.select_all()
    monkeypatch.setattr('focusdesk.ui.markdown_editor.simpledialog.askstring',lambda *a,**k:'https://example.com')
    editor.link()
    assert editor.get() == '[document](https://example.com)'


def test_preview_has_formatted_tags_and_inert_html_code_urls(ui):
    source = '# Titlu\n## Subtitlu\n- **bold** și *italic*\n1. pas\n- [x] făcut\n[link](https://example.com)\n`inline`\n```python\nprint("never executed")\n```\n<script>alert(1)</script>\n![imagine](https://example.com/image.png)'
    editor = details(ui, source).editor
    editor.render()
    view = editor.preview
    for tag in ('h1','h2','bold','italic','list','link','code'):
        assert view.tag_ranges(tag), tag
    visible = view.get('1.0','end-1c')
    assert '<script>alert(1)</script>' in visible
    assert 'print("never executed")' in visible
    assert 'https://example.com/image.png' in visible
    assert editor.get() == source
    assert str(view.cget('state')) == 'disabled'


def test_old_description_roundtrip_paste_and_selection_guard(ui, monkeypatch):
    source = 'Descriere veche\n\nȘir cu ț, ș, î, â și ă.\n  indentare\n'
    tab = details(ui, source)
    assert tab.desc.get('1.0','end-1c') == source
    assert tab.save() and ui.ws.get_description(ui.selected_id) == source
    tab.desc.mark_set('insert', 'end-1c')
    tab.desc.insert('insert','Lipire\npe mai multe linii\ncu diacritice: șț')
    ui.root.update()
    assert tab.is_dirty()
    original_id = ui.selected_id
    other = ui.ws.create_node(Kind.TASK,'Alt task')
    monkeypatch.setattr('focusdesk.ui.app.ask_choice',lambda *a,**k:'cancel')
    ui.select_node(other.id)
    assert ui.selected_id == original_id and 'Lipire' in tab.editor.get()
    monkeypatch.setattr('focusdesk.ui.app.ask_choice',lambda *a,**k:'save')
    ui.select_node(other.id)
    assert ui.selected_id == other.id
    assert 'Lipire\npe mai multe linii' in ui.ws.get_description(original_id)


def test_expanded_peer_cancel_restores_only_this_session_and_blocks_selection(ui):
    tab = details(ui, 'Pe disc')
    fill(tab.editor, 'Ciornă anterioară')
    tab.expand_description()
    window = tab.expanded
    try:
        window.editor.text.insert('end-1c','\nAdăugare în extins')
        ui.refresh_all()  # a pending refresh must not overwrite the peer before Modified is delivered
        ui.root.update()
        assert 'Adăugare' in tab.editor.get()  # same buffer, no copy on save
        assert not ui.confirm_leave()
        window.cancel()
        ui.root.update()
        assert tab.editor.get() == 'Ciornă anterioară' and tab.is_dirty()
        assert ui.ws.get_description(ui.selected_id) == 'Pe disc'
    finally:
        if tab.expanded:
            tab.expanded.cancel()


def test_expanded_cancel_clean_and_save_persists(ui, monkeypatch):
    tab = details(ui, 'Inițial')
    tab.expand_description()
    fill(tab.expanded.editor,'Anulat')
    tab.expanded.cancel()
    ui.root.update()
    assert tab.editor.get() == 'Inițial' and not tab.is_dirty()
    tab.expand_description()
    fill(tab.expanded.editor,'# Salvat\n\nDescriere nouă')
    tab.expanded.save()
    ui.root.update()
    assert tab.expanded is None and not tab.is_dirty()
    assert ui.ws.get_description(ui.selected_id) == '# Salvat\n\nDescriere nouă'


def test_failed_expanded_save_stays_open_without_losing_text(ui, monkeypatch):
    tab = details(ui,'Inițial')
    tab.expand_description()
    window = tab.expanded
    fill(window.editor,'Ciornă')
    monkeypatch.setattr(ui,'run_write',lambda *a,**k:False)
    window.save()
    assert tab.expanded is window and window.winfo_exists()
    assert window.editor.get() == 'Ciornă' and ui.ws.get_description(ui.selected_id) == 'Inițial'
    window.cancel()


def test_status_icons_are_distinct_live_and_parent_is_not_completed(ui):
    task = ui.ws.get(ui.selected_id)
    project = ui.ws.create_node(Kind.PROJECT,'Proiect')
    folder = ui.ws.create_node(Kind.FOLDER,'Folder')
    pictures = set()
    for state in (Status.TODO, Status.IN_PROGRESS, Status.WAITING, Status.TESTING, Status.DONE, Status.CANCELLED):
        ui.ws.update_node(task.id,status=state)
        ui.root.update()
        expected = str(node_icon(ui.root,ui.ws.get(task.id)))
        pictures.add(expected)
        assert ui.sidebar.tree.item(task.id,'image')[0] == expected
        assert str(ui.inspector.status_lbl.cget('image')[0]) == expected
    assert len(pictures) == 6
    assert str(node_icon(ui.root,project)) not in pictures
    assert str(node_icon(ui.root,folder)) != str(node_icon(ui.root,project))
    ui.ws.update_node(task.id,status=Status.TODO)
    child = ui.ws.create_node(Kind.TASK,'Copil',task.id)
    ui.ws.update_node(child.id,status=Status.DONE)
    ui.root.update()
    assert ui.ws.get(task.id).status == Status.TODO


def test_completed_filter_reopen_and_central_search_icons(ui):
    task_id = ui.selected_id
    ui.ws.update_node(task_id,status=Status.DONE)
    ui.root.update()
    ui.current_view = 'search:Task'
    ui.refresh_all()
    expected = str(node_icon(ui.root,ui.ws.get(task_id)))
    assert ui.tasklist.tv.item(task_id,'image')[0] == expected
    assert 'closed' in ui.tasklist.tv.item(task_id,'tags')
    ui.tasklist.closed_var.set(False)
    ui.tasklist.refresh()
    assert not ui.tasklist.tv.exists(task_id)
    ui.refresh_all()
    assert not ui.tasklist.closed_var.get()  # automatic refresh must not reset the filter
    ui.completed_var.set(False)
    ui.toggle_completed()
    assert not ui.sidebar.tree.exists(task_id)
    ui.completed_var.set(True)
    ui.toggle_completed()
    ui.inspector.reopen_btn.invoke()
    ui.root.update()
    assert ui.ws.get(task_id).status == Status.TODO
    assert ui.inspector.reopen_btn.cget("text") == "Finalizează"


def test_real_paste_and_ctrl_s_save_without_double_submission(ui, monkeypatch):
    tab = details(ui, '')
    ui.root.deiconify()
    tab.desc.focus_force()
    ui.root.update()
    value = 'Prima linie\nA doua: șțăîâ\n    indentat'
    tab.desc.clipboard_clear()
    tab.desc.clipboard_append(value)
    tab.desc.event_generate('<<Paste>>')
    ui.root.update()
    assert tab.editor.get() == value and tab.is_dirty()
    writes = []
    original = ui.ws.set_description
    def tracked(*args):
        writes.append(args)
        return original(*args)
    monkeypatch.setattr(ui.ws, 'set_description', tracked)
    tab.desc.event_generate('<Control-s>')
    ui.root.update()
    assert len(writes) == 1 and ui.ws.get_description(ui.selected_id) == value


def test_inspector_status_save_updates_header_tree_and_list(ui):
    from focusdesk.domain.labels import STATUS_LABELS
    tab = details(ui, 'Descriere')
    ui.current_view = 'search:Task'
    ui.refresh_all()
    tab.vars['status'].set(STATUS_LABELS[Status.TESTING])
    assert tab.save()
    expected = str(node_icon(ui.root, ui.ws.get(ui.selected_id)))
    assert ui.sidebar.tree.item(ui.selected_id, 'image')[0] == expected
    assert ui.tasklist.tv.item(ui.selected_id, 'image')[0] == expected
    assert ui.inspector.status_lbl.cget('image')[0] == expected


def test_description_split_keeps_fields_editor_and_save_visible(ui):
    tab = details(ui, '# Document\n\nText lung\n' * 60)
    ui.root.deiconify()
    ui.root.geometry('1100x700')
    ui.root.update()
    assert tab.sf.winfo_height() >= 100
    assert tab.editor.text.winfo_height() >= 50
    assert tab.save_btn.winfo_ismapped()
    assert tab.editor.winfo_height() >= 200


def test_heading_and_markdown_checkboxes_do_not_change_functional_checklist(ui):
    tab = details(ui, 'Obiectiv')
    tab.editor.select_all()
    tab.editor.heading(1)
    assert tab.editor.get() == '# Obiectiv'
    tab.editor.select_all()
    tab.editor.heading(3)
    assert tab.editor.get() == '### Obiectiv'
    fill(tab.editor,'- [x] Documentare, nu checklist funcțional')
    assert tab.save()
    assert ui.ws.get(ui.selected_id).checklist == []
    tab.editor.set_read_only(True)
    tab.editor.wrap('**','**')
    assert tab.editor.get() == '- [x] Documentare, nu checklist funcțional'
    tab.editor.set_read_only(False)


def test_expanded_shortcut_and_cancel_cannot_reintroduce_discarded_text(ui):
    tab = details(ui, 'Inițial')
    ui.root.deiconify()
    ui.root.update()
    tab.expand_description()
    fill(tab.expanded.editor,'De abandonat')
    tab.expanded.cancel()
    tab.editor.undo()
    assert tab.editor.get() == 'Inițial'
    tab.expand_description()
    window = tab.expanded
    fill(window.editor,'Salvat prin scurtătură')
    window.editor.text.focus_force()
    ui.root.update()
    window.editor.text.event_generate('<Control-s>')
    ui.root.update()
    assert tab.expanded is None
    assert ui.ws.get_description(ui.selected_id) == 'Salvat prin scurtătură'
