"""Real disk explorer on disposable data; external applications and mail are always fake."""
from __future__ import annotations

import os
from pathlib import Path
import threading
import time
from zipfile import ZipFile

import pytest

from focusdesk.domain.models import Kind
from focusdesk.errors import FocusDeskError, UnsafePathError
from focusdesk.services.files import FileService, normalized_file_key


def pump(app, condition, seconds=5):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.root.update()
        if condition(): return True
        time.sleep(.01)
    return False


def settled(app, tree):
    return pump(app, lambda: not tree.requests and not tree._queue and tree._refresh_job is None)


def iid_for(tree, path):
    return next((iid for iid, row in tree.rows.items() if row['entry'] and row['entry'].path == path), None)


def select(tab, path):
    iid = iid_for(tab.explorer, path)
    assert iid is not None, path
    tab.tv.selection_set(iid)
    tab.tv.focus(iid)
    return iid


@pytest.fixture
def explorer(ui, tmp_path, monkeypatch):
    root = tmp_path / 'Proiect cu diacritice șț'
    root.mkdir()
    project = ui.ws.create_node(Kind.PROJECT, 'Proiect')
    task = ui.ws.get(ui.selected_id)
    ui.ws.move(task.id, project.id)
    ui.files.set_code_folder(project.id, root)
    ui.refresh_all()
    ui.select_node(task.id, reveal=True)
    ui.root.deiconify()
    ui.inspector.show_tab('Fișiere')
    ui.root.update()
    tab = ui.inspector.tab_by_title('Fișiere')
    tab.explorer.POLL_MS = 60_000  # Tests drive polling explicitly; no timing-dependent accidental refresh.
    assert settled(ui, tab.explorer)
    errors = []
    monkeypatch.setattr('focusdesk.ui.tab_files.show_error', lambda parent, text, *a: errors.append(text))
    monkeypatch.setattr('focusdesk.ui.app.show_error', lambda parent, text, *a: errors.append(text))
    monkeypatch.setattr('focusdesk.ui.tab_files.confirm', lambda *a: True)
    yield ui, tab, root, project, task, errors
    tab.stop_monitoring()


def test_sources_inherited_overlapping_and_unregistered_files(ws, tmp_path):
    fs = FileService(ws)
    project = ws.create_node(Kind.PROJECT, 'P')
    task = ws.create_node(Kind.TASK, 'T', project.id)
    root = tmp_path / 'extern'; root.mkdir()
    fs.set_code_folder(project.id, root)
    (root / 'manual.txt').write_text('document')
    fs.add_external(task.id, root / 'manual.txt')
    sources = fs.explorer_sources(task.id)
    assert len(sources) == 2
    assert sources[0].path == root and 'Moștenit de la P' in sources[0].note
    fs.set_code_folder(task.id, 'files', mode='managed')
    sources = fs.explorer_sources(task.id)
    assert len([s for s in sources if s.path == fs.files_dir(task.id)]) == 1
    fs.set_code_folder(task.id, 'files/cod', mode='managed')
    assert all('Suprapunere' in s.note for s in fs.explorer_sources(task.id) if s.key in ('work', 'files'))
    assert all(s.path != ws.node_dir(task.id) for s in sources)


def test_external_directory_covers_nested_references_once(ws, tmp_path):
    task = ws.create_node(Kind.TASK, 'T'); fs = FileService(ws)
    root = tmp_path / 'extern'; root.mkdir()
    path = root / 'doc.txt'; path.write_text('doc')
    fs.add_external(task.id, path)
    fs.add_external(task.id, root)
    fs.add_external(task.id, root)
    links = [s for s in fs.explorer_sources(task.id) if s.key.startswith('link-')]
    assert len(links) == 1 and links[0].path == root


def test_list_reads_no_document_payload_and_no_closed_subfolders(ws, tmp_path, monkeypatch):
    root = tmp_path / 'folder'; root.mkdir()
    child = root / 'copil'; child.mkdir()
    (root / '.ascuns').write_text('ascuns')
    (root / 'document.txt').write_text('document')
    (child / 'greu.bin').write_bytes(b'x' * 4096)
    original = os.scandir
    visited = []
    def scan(path):
        visited.append(Path(path)); return original(path)
    monkeypatch.setattr(os, 'scandir', scan)
    monkeypatch.setattr(Path, 'open', lambda *a, **k: (_ for _ in ()).throw(AssertionError('No payload reads')))
    entries = FileService.browse_directory(root)
    assert {entry.path.name for entry in entries} == {'copil', '.ascuns', 'document.txt'}
    assert visited == [root]
    assert next(e for e in entries if e.is_dir).size_bytes is None


def test_path_boundaries_links_and_replaced_ancestor_are_blocked(tmp_path):
    root = tmp_path / 'root'; root.mkdir()
    outside = tmp_path / 'outside'; outside.mkdir()
    (outside / 'secret.txt').write_text('secret')
    link = root / 'link'
    try: link.symlink_to(outside, target_is_directory=True)
    except OSError: pytest.skip('Symlink unavailable')
    entries = FileService.browse_directory(root, include_links=True)
    assert len(entries) == 1 and entries[0].is_link and entries[0].state == 'link'
    with pytest.raises(UnsafePathError): FileService.browse_directory(link, root=root)
    with pytest.raises(UnsafePathError): FileService.describe_entry(root, link / 'secret.txt')
    with pytest.raises(UnsafePathError): FileService.describe_entry(root, outside / 'secret.txt')
    directory = root / 'initial'; directory.mkdir(); (directory / 'doc.txt').write_text('old')
    (directory / 'doc.txt').unlink(); directory.rmdir(); directory.symlink_to(outside, target_is_directory=True)
    with pytest.raises(UnsafePathError): FileService.browse_directory(directory, root=root)


def test_manual_add_expand_deep_refresh_rename_delete_and_metadata_unchanged(explorer):
    app, tab, root, _, task, _ = explorer
    metadata = (app.ws.node_dir(task.id) / 'node.json').read_bytes()
    folder = root / 'subfolder'; folder.mkdir()
    first = folder / 'manual.txt'; first.write_text('manual')
    tab.refresh(); assert settled(app, tab.explorer)
    folder_id = iid_for(tab.explorer, folder)
    assert folder_id and not iid_for(tab.explorer, first)  # Lazy directory, no recursion.
    tab.explorer.open_directory(folder_id); assert settled(app, tab.explorer)
    selected = select(tab, first)
    second = folder / 'nou.txt'; second.write_text('nou')
    # The root's mtime need not change; the opened child directory is checked independently.
    before_root = root.stat().st_mtime_ns
    second.rename(folder / 'redenumit.txt')
    assert root.stat().st_mtime_ns == before_root
    tab.explorer._poll(); assert settled(app, tab.explorer)
    assert tab.tv.selection() == (selected,) and bool(tab.tv.item(folder_id, 'open'))
    assert iid_for(tab.explorer, folder / 'redenumit.txt')
    first.unlink()
    tab.refresh(); assert settled(app, tab.explorer)
    assert not tab.tv.exists(selected)
    assert not app.ws.get(task.id).attachments
    assert (app.ws.node_dir(task.id) / 'node.json').read_bytes() == metadata
    assert not app.inspector.is_dirty()


def test_refresh_preserves_selection_scroll_expanded_and_updates_only_changed_rows(explorer, monkeypatch):
    app, tab, root, _, _, _ = explorer
    for i in range(80): (root / f'{i:03}.txt').write_text('x')
    tab.refresh(); assert settled(app, tab.explorer)
    selected = select(tab, root / '055.txt')
    tab.tv.yview_moveto(.35); tab.tv.xview_moveto(.1); app.root.update()
    y, x = tab.tv.yview()[0], tab.tv.xview()[0]
    original = tab.tv.item
    changed = []
    def item(iid, option=None, **kwargs):
        if kwargs: changed.append(iid)
        return original(iid, option, **kwargs)
    monkeypatch.setattr(tab.tv, 'item', item)
    tab.refresh(); assert settled(app, tab.explorer)
    assert changed == []
    assert tab.tv.selection() == (selected,) and abs(tab.tv.yview()[0] - y) < .03
    assert abs(tab.tv.xview()[0] - x) < .03
    (root / '030.txt').write_text('changed size')
    tab.refresh(); assert settled(app, tab.explorer)
    assert selected == tab.tv.selection()[0]
    assert set(changed) <= {iid_for(tab.explorer, root / '030.txt')}


def test_large_directories_sorted_before_paging_and_children_lazy(explorer):
    app, tab, root, _, _, _ = explorer
    folder = root / 'sub'; folder.mkdir(); (folder / 'not-yet.txt').write_text('x')
    for i in reversed(range(215)): (root / f'Document {i:03}.txt').write_text('x')
    tab.refresh(); assert settled(app, tab.explorer)
    root_id = iid_for(tab.explorer, root)
    rows = [iid for iid in tab.tv.get_children(root_id) if iid in tab.explorer.rows]
    assert len(rows) == 200 and tab.tv.item(rows[0], 'text') == 'sub'
    assert not iid_for(tab.explorer, folder / 'not-yet.txt')
    more = root_id + ':more'; tab.tv.focus(more)
    tab.explorer.activate_selected()
    assert len([i for i in tab.tv.get_children(root_id) if i in tab.explorer.rows]) == 216
    assert iid_for(tab.explorer, root / 'Document 214.txt')


def test_same_names_and_legacy_reference_are_one_disk_row(explorer):
    app, tab, root, _, task, _ = explorer
    paths = []
    for name in ('A', 'B'):
        directory = root / name; directory.mkdir(); path = directory / 'Raport.txt'; path.write_text(name); paths.append(path)
    ref = app.files.add_external(task.id, paths[0])
    tab.load(app.ws.get(task.id)); tab.refresh(); assert settled(app, tab.explorer)
    for path in paths:
        tab.explorer.open_directory(iid_for(tab.explorer, path.parent))
    assert settled(app, tab.explorer)
    rows = [row for row in tab.explorer.rows.values() if row['entry'] and row['entry'].path in paths]
    assert len(rows) == 2
    select(tab, paths[0]); assert tab._selected_att().id == ref.id
    tab._remove(); assert settled(app, tab.explorer)
    assert paths[0].exists() and not app.ws.get(task.id).attachments
    assert iid_for(tab.explorer, paths[0])


def test_missing_reference_remains_manageable_without_duplicate(explorer):
    app, tab, root, _, task, _ = explorer
    path = root / 'referință.txt'; path.write_text('ref')
    ref = app.files.add_external(task.id, path)
    tab.load(app.ws.get(task.id)); tab.refresh(); assert settled(app, tab.explorer)
    path.unlink(); tab.refresh(); assert settled(app, tab.explorer)
    iid = select(tab, path)
    assert tab.explorer.rows[iid]['entry'].state == 'missing'
    assert tab._selected_att().id == ref.id
    tab._remove(); assert settled(app, tab.explorer)
    assert iid_for(tab.explorer, path) is None


def test_missing_root_and_inaccessible_subfolder_do_not_block_other_sources(explorer, monkeypatch):
    app, tab, root, _, _, _ = explorer
    private = root / 'privat'; private.mkdir()
    allowed = root / 'ok.txt'; allowed.write_text('ok')
    tab.refresh(); assert settled(app, tab.explorer)
    original = FileService.browse_directory
    def denied(path, **kwargs):
        if Path(path) == private: raise FocusDeskError('Acces refuzat pentru subfolder')
        return original(path, **kwargs)
    monkeypatch.setattr(FileService, 'browse_directory', staticmethod(denied))
    tab.explorer.open_directory(iid_for(tab.explorer, private)); assert settled(app, tab.explorer)
    assert iid_for(tab.explorer, allowed)
    assert 'Acces refuzat' in tab.tv.set(iid_for(tab.explorer, private), 'state')
    allowed.unlink(); private.rmdir(); root.rmdir()
    tab.refresh(); assert settled(app, tab.explorer)
    assert 'nu este disponibilă' in tab.tv.set(iid_for(tab.explorer, root), 'state')
    root.mkdir(); (root / 'revenit.txt').write_text('ok')
    tab.refresh(); assert settled(app, tab.explorer)
    assert iid_for(tab.explorer, root / 'revenit.txt')


def test_scans_run_outside_tk_and_stale_task_results_are_ignored(explorer, monkeypatch):
    app, tab, root, _, task, _ = explorer
    other = app.ws.create_node(Kind.TASK, 'Alt task')
    other_dir = app.files.files_dir(other.id); (other_dir / 'actual.txt').write_text('actual')
    app.root.update()
    app.select_node(task.id, reveal=True); app.root.update()
    gate = threading.Event(); started = threading.Event(); threads = []
    original = FileService.browse_directory
    def delayed(path, **kwargs):
        threads.append(threading.get_ident())
        if Path(path) == root:
            started.set(); gate.wait(4)
        return original(path, **kwargs)
    monkeypatch.setattr(FileService, 'browse_directory', staticmethod(delayed))
    (root / 'vechi.txt').write_text('vechi')
    tab.refresh(); assert pump(app, started.is_set)
    app.select_node(other.id, reveal=True); tab.load(app.ws.get(other.id)); app.root.update()
    gate.set(); assert settled(app, tab.explorer)
    assert iid_for(tab.explorer, other_dir / 'actual.txt'), (app.selected_id, tab.node_id, tab.explorer.node_id,
        tab.explorer._active, tab.explorer.winfo_viewable(), tab.explorer.rows, tab.explorer._cache)
    assert not iid_for(tab.explorer, root / 'vechi.txt')
    assert threads and all(value != threading.get_ident() for value in threads)


def test_monitor_stops_when_hidden_and_f5_does_not_reload_workspace(explorer, monkeypatch):
    app, tab, root, _, _, _ = explorer
    app.inspector.show_tab('Detalii'); app.root.update()
    assert not tab.explorer._active and tab.explorer._poll_job is None
    path = root / 'revenire.txt'; path.write_text('document')
    app.inspector.show_tab('Fișiere'); app.root.update(); assert settled(app, tab.explorer)
    assert iid_for(tab.explorer, path)
    called = []
    monkeypatch.setattr(app, 'reload_preserving_context', lambda: called.append(True))
    another = root / 'F5.txt'; another.write_text('F5')
    tab.tv.focus_force(); tab.tv.event_generate('<F5>'); app.root.update()
    assert settled(app, tab.explorer)
    assert iid_for(tab.explorer, another) and not called


def test_document_open_script_protection_and_action_revalidation(explorer, monkeypatch):
    app, tab, root, _, _, errors = explorer
    doc = root / 'Document.txt'; doc.write_text('doc')
    script = root / 'rulare.py'; script.write_text('raise AssertionError("never execute")')
    tab.refresh(); assert settled(app, tab.explorer)
    opened, code, revealed = [], [], []
    monkeypatch.setattr('focusdesk.integrations.system.open_with_default_app', lambda path: opened.append(path))
    monkeypatch.setattr('focusdesk.integrations.system.open_in_vscode', lambda path, *a: code.append(path))
    monkeypatch.setattr('focusdesk.integrations.system.reveal_in_explorer', lambda path: revealed.append(path))
    select(tab, doc); tab._open(); assert pump(app, lambda: bool(opened))
    assert opened == [doc]
    monkeypatch.setattr('focusdesk.ui.tab_files.ask_choice', lambda *a: 'editor')
    select(tab, script); tab._open(); assert pump(app, lambda: bool(code))
    assert code == [script] and opened == [doc]
    monkeypatch.setattr('focusdesk.ui.tab_files.ask_choice', lambda *a: 'explorer')
    tab._open(); assert pump(app, lambda: bool(revealed))
    script.unlink(); tab._open(); assert pump(app, lambda: bool(errors))
    assert opened == [doc] and code == [script] and revealed == [script]


def test_discovered_document_prefills_real_mail_form_without_send(explorer, monkeypatch):
    from focusdesk.ui.mail_ui import MailDialog
    app, tab, root, _, task, _ = explorer
    path = root / 'manual.txt'; path.write_text('document')
    tab.refresh(); assert settled(app, tab.explorer)
    seen = []
    def capture(self):
        self.to_var.set('ana@test.ro')
        seen.append(self.collect()); self.destroy()
    monkeypatch.setattr(MailDialog, 'run', capture)
    select(tab, path); tab._email(); assert pump(app, lambda: bool(seen))
    assert [item.path for item in seen[0]['draft'].attachments] == [str(path)]
    assert not app.ws.get(task.id).attachments


def test_read_only_completed_archived_exploration_and_backup_rules(explorer, monkeypatch, tmp_path):
    from focusdesk.services.backup import create_backup, restore_backup_to_folder
    app, tab, root, project, task, _ = explorer
    external = root / 'external.txt'; external.write_text('extern')
    own = app.files.files_dir(task.id) / 'manual-local.txt'; own.write_text('local')
    app.ws.update_node(task.id, status='done'); app.ws.archive(task.id)
    tab.load(app.ws.get(task.id)); tab.refresh(); assert settled(app, tab.explorer)
    assert iid_for(tab.explorer, external) and iid_for(tab.explorer, own)
    backup = create_backup(app.ws, full=True)
    with ZipFile(backup.path) as archive:
        assert any(name.endswith('files/manual-local.txt') for name in archive.namelist())
        assert not any(name.endswith('external.txt') for name in archive.namelist())
    target = restore_backup_to_folder(backup.path, tmp_path / 'restored')
    assert list(target.rglob('manual-local.txt'))
    before = (app.ws.node_dir(task.id) / 'node.json').read_bytes()
    monkeypatch.setattr(app.ws.repo, 'read_only', True)
    tab.load(app.ws.get(task.id)); tab.refresh(); assert settled(app, tab.explorer)
    opened = []
    monkeypatch.setattr('focusdesk.integrations.system.open_with_default_app', lambda path: opened.append(path))
    select(tab, external); tab._open(); assert pump(app, lambda: bool(opened))
    tab._remove(); tab._clear_code(); tab._set_managed_code()
    assert (app.ws.node_dir(task.id) / 'node.json').read_bytes() == before


def test_navigation_back_restores_expansion_selection_and_scroll(explorer):
    app, tab, root, _, task, _ = explorer
    other = app.ws.create_node(Kind.TASK, 'Alt task')
    app.root.update()
    folder = root / 'dosar'; folder.mkdir()
    for i in range(40): (folder / f'{i:02}.txt').write_text('doc')
    tab.refresh(); assert settled(app, tab.explorer)
    folder_id = iid_for(tab.explorer, folder)
    tab.explorer.open_directory(folder_id); assert settled(app, tab.explorer)
    chosen = select(tab, folder / '20.txt')
    tab.tv.yview_moveto(.3); app.root.update(); scroll = tab.tv.yview()[0]
    app.select_node(other.id, reveal=True); app.root.update(); assert settled(app, tab.explorer)
    app.select_node(task.id, reveal=True); app.root.update(); assert settled(app, tab.explorer)
    assert tab.tv.item(folder_id, 'open') and tab.tv.selection() == (chosen,)
    assert abs(tab.tv.yview()[0] - scroll) < .08


def test_window_focus_refresh_is_debounced(explorer):
    app, tab, root, _, _, _ = explorer
    path = root / 'din-explorer.txt'; path.write_text('manual')
    for _ in range(4): app.root.event_generate('<FocusIn>')
    assert pump(app, lambda: iid_for(tab.explorer, path) is not None)


def test_polling_checks_a_bounded_number_of_open_directories(explorer, monkeypatch):
    app, tab, root, _, _, _ = explorer
    for i in range(10): (root / f'dir{i}').mkdir()
    tab.refresh(); assert settled(app, tab.explorer)
    for i in range(10): tab.explorer.open_directory(iid_for(tab.explorer, root / f'dir{i}'))
    assert settled(app, tab.explorer)
    calls = []
    original = FileService.browse_directory
    def scan(path, **kwargs):
        calls.append(Path(path)); return original(path, **kwargs)
    monkeypatch.setattr(FileService, 'browse_directory', staticmethod(scan))
    tab.explorer._poll(); assert settled(app, tab.explorer)
    assert 0 < len(calls) <= tab.explorer.POLL_DIRECTORIES


@pytest.mark.parametrize('extension', ['.py', '.bat', '.ps1', '.exe'])
def test_runnable_file_never_uses_default_application(explorer, monkeypatch, extension):
    app, tab, root, _, _, _ = explorer
    path = root / ('rulare' + extension); path.write_text('never execute')
    tab.refresh(); assert settled(app, tab.explorer)
    launched = []
    monkeypatch.setattr('focusdesk.integrations.system.open_with_default_app', lambda *_: launched.append('unsafe'))
    monkeypatch.setattr('focusdesk.ui.tab_files.ask_choice', lambda *_: 'cancel')
    select(tab, path); tab._open(); assert pump(app, lambda: not tab._action_pending)
    assert not launched and path.read_text() == 'never execute'


def test_legacy_reference_in_missing_parent_can_be_removed_in_manager(explorer, monkeypatch):
    from focusdesk.ui.tab_files import ReferenceDialog
    app, tab, root, _, task, _ = explorer
    folder = root / 'disparut'; folder.mkdir()
    path = folder / 'old.txt'; path.write_text('old')
    ref = app.files.add_external(task.id, path)
    path.unlink(); folder.rmdir()
    dialog = ReferenceDialog(tab, app.ws.get(task.id))
    dialog.geometry('520x300'); app.root.update()
    assert dialog.ok_btn.winfo_height() >= 20
    assert dialog.ok_btn.winfo_rooty() + dialog.ok_btn.winfo_height() <= dialog.winfo_rooty() + dialog.winfo_height()
    dialog.destroy()
    monkeypatch.setattr('focusdesk.ui.tab_files.ReferenceDialog.run', lambda self: self.destroy() or ref.id)
    monkeypatch.setattr('focusdesk.ui.tab_files.ask_choice', lambda *a: 'remove')
    tab._manage_references()
    assert not app.ws.get(task.id).attachments and not path.exists()


def test_inheritance_can_be_disabled_without_changing_project_or_files(explorer):
    app, tab, root, project, task, _ = explorer
    path = root / 'continua-sa-existe.txt'; path.write_text('doc')
    original = app.ws.get(project.id).source_workspace
    tab._clear_code()
    assert app.ws.get(task.id).source_workspace.mode == 'disabled'
    assert app.ws.get(project.id).source_workspace == original and path.exists()
    assert app.files.effective_source(task.id) is None


def test_symlink_is_visible_but_never_expanded_or_opened(explorer, monkeypatch):
    app, tab, root, _, _, errors = explorer
    outside = root.parent / 'afara'; outside.mkdir()
    path = outside / 'secret.txt'; path.write_text('secret')
    link = root / 'link'
    try: link.symlink_to(outside, target_is_directory=True)
    except OSError: pytest.skip('Symlink unavailable')
    tab.refresh(); assert settled(app, tab.explorer)
    iid = select(tab, link)
    assert tab.explorer.rows[iid]['entry'].is_link
    tab.explorer.open_directory(iid)
    assert not tab.tv.get_children(iid) and not iid_for(tab.explorer, path)
    opened = []
    monkeypatch.setattr('focusdesk.integrations.system.open_with_default_app', lambda path: opened.append(path))
    tab._open(); assert pump(app, lambda: bool(errors))
    assert not opened


def test_per_child_stat_error_does_not_hide_readable_sibling(tmp_path, monkeypatch):
    from types import SimpleNamespace
    root = tmp_path / 'root'; root.mkdir()
    good = root / 'good.txt'; good.write_text('doc')
    class Entries:
        def __enter__(self):
            return iter([SimpleNamespace(path=str(root/'locked'), stat=lambda **_: (_ for _ in ()).throw(PermissionError('denied'))),
                         SimpleNamespace(path=str(good), stat=lambda **_: good.stat())])
        def __exit__(self, *args): pass
    monkeypatch.setattr(os, 'scandir', lambda _: Entries())
    entries = FileService.browse_directory(root, include_links=True)
    assert {e.path.name: e.state for e in entries} == {'locked':'inaccessible', 'good.txt':'ready'}


def test_workspace_switch_cancels_monitoring_and_ignores_late_directory_results(explorer, monkeypatch, tmp_path):
    from focusdesk.services.workspace import Workspace
    app, tab, root, _, _, _ = explorer
    gate = threading.Event(); started = threading.Event()
    original = FileService.browse_directory
    def delayed(path, **kwargs):
        if Path(path) == root:
            started.set(); gate.wait(4)
        return original(path, **kwargs)
    monkeypatch.setattr(FileService, 'browse_directory', staticmethod(delayed))
    old_ws = app.ws
    replacement = Workspace.open(tmp_path / 'alt-workspace', create=True)
    node = replacement.create_node(Kind.TASK, 'Task din alt workspace')
    new_path = FileService(replacement).files_dir(node.id) / 'nou.txt'; new_path.write_text('nou')
    replacement_root = replacement.root; replacement.close()
    assert pump(app, lambda: not app._pending_workspace_jobs())
    (root / 'nu-aplica.txt').write_text('vechi')
    tab.refresh(); assert pump(app, started.is_set)
    try:
        assert app.open_workspace(replacement_root)
        assert tab.explorer.ws is None and tab._ws is None and not tab.explorer._cache
        app.select_node(node.id, reveal=True); app.inspector.show_tab('Fișiere'); app.root.update()
        gate.set(); assert settled(app, tab.explorer)
        assert app.ws is not old_ws and tab.explorer.ws is app.ws
        assert iid_for(tab.explorer, new_path)
        assert not iid_for(tab.explorer, root / 'nu-aplica.txt')
    finally:
        gate.set()


def test_focus_return_restarts_a_stopped_monitor(explorer):
    app, tab, root, _, _, _ = explorer
    tab.stop_monitoring()
    path = root / 'dupa-revenire.txt'; path.write_text('manual')
    app.root.event_generate('<FocusIn>')
    assert pump(app, lambda: tab.explorer._active and iid_for(tab.explorer, path) is not None)


def test_keyboard_expansion_keeps_the_requested_folder_when_focus_moves(explorer):
    app, tab, root, _, _, _ = explorer
    a, b = root / 'A', root / 'B'; a.mkdir(); b.mkdir()
    (a / 'a.txt').write_text('a'); (b / 'b.txt').write_text('b')
    tab.refresh(); assert settled(app, tab.explorer)
    a_id, b_id = iid_for(tab.explorer, a), iid_for(tab.explorer, b)
    tab.tv.focus(a_id); tab.tv.event_generate('<<TreeviewOpen>>')
    tab.tv.focus(b_id)
    assert settled(app, tab.explorer)
    assert iid_for(tab.explorer, a / 'a.txt')
    assert not iid_for(tab.explorer, b / 'b.txt') and not tab.tv.item(b_id, 'open')
