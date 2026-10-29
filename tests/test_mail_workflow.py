"""Mail snapshots and attachments using temporary files, real Tk and fake Outlook only."""
from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from focusdesk.domain.models import Kind
from focusdesk.errors import StorageError, ValidationError
from focusdesk.integrations.outlook import MailHandoffUncertain
from focusdesk.integrations.outlook_com import OutlookComBackend
from focusdesk.services.files import FileService, inspect_local_file, normalized_file_key
from focusdesk.services.mail import (attachment_selection, attachment_summary, build_draft, confirmation_text,
                                     default_body, journal_text)
from focusdesk.workers.com_worker import ComBlocked


def pump(app, condition, seconds=4):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.root.update()
        if condition():
            return True
        time.sleep(.01)
    return False


@pytest.fixture
def documents(tmp_path):
    paths = []
    for directory, content in (("prima", "Ședință\n  detalii\n"), ("a doua", "Alt document")):
        folder = tmp_path / directory
        folder.mkdir()
        path = folder / "Raport.txt"
        path.write_text(content, encoding="utf-8")
        paths.append(path)
    return paths


@pytest.mark.parametrize("length", [601, 100_000])
def test_full_description_preserves_whitespace_and_diacritics(ws, length):
    text = "  Scop\nȘtiință și țărm\n\nPasul 1\n    păstrează indentarea\n" + "x" * length + "\n\n"
    node = ws.create_node(Kind.TASK, "Task", description=text, next_action="Verifică")
    body = default_body(ws, node)
    assert body.endswith(text) and "Verifică" in body and "…" not in body
    assert build_draft("a@b.ro", "", "S", body).body == body


def test_empty_description_and_explicit_snapshot(ws):
    node = ws.create_node(Kind.TASK, "Task", description="Salvat")
    assert default_body(ws, node, description="\n  ") == default_body(ws, node, description="")
    assert "Ciornă\n  pas" in default_body(ws, node, description="Ciornă\n  pas")
    assert ws.get_description(node.id) == "Salvat"


def test_attachment_deduplication_and_confirmation(documents):
    a, b = documents
    selected = attachment_selection([a, a.parent / "." / a.name, b])
    assert len(selected) == 2 and selected[0].name == selected[1].name == "Raport.txt"
    assert selected[0].path != selected[1].path
    assert normalized_file_key(r"C:\Date\A\..\Raport.TXT") == normalized_file_key("c:/date/raport.txt")
    assert normalized_file_key(r"\\server\share\A.txt") == normalized_file_key("//SERVER/SHARE/a.TXT")
    draft = build_draft("a@b.ro", "c@d.ro", "Subiect", "Corp privat", attachments=selected)
    confirmation = confirmation_text(draft)
    assert "a@b.ro" in confirmation and "c@d.ro" in confirmation and "Subiect" in confirmation
    assert attachment_summary(selected) in confirmation
    log = journal_text(draft)
    assert "Raport.txt" in log and "Corp privat" not in log and "livrare neconfirmată" in log


def test_directory_missing_and_deleted_selection_are_blocked(documents):
    a, b = documents
    with pytest.raises(ValidationError, match="interiorul"):
        build_draft("", "", "", "", for_send=False, attachments=[a.parent])
    selected = attachment_selection([a, b])
    b.unlink()
    assert attachment_selection(selected)[1].state == "missing"
    with pytest.raises(ValidationError, match="nu mai există"):
        build_draft("a@b.ro", "", "S", "B", attachments=selected)
    assert a.is_file()


def test_unreadable_file_is_checked_by_open_not_access(documents, monkeypatch):
    path = documents[0]
    original = Path.open

    def no_access(self, *args, **kwargs):
        if self == path:
            raise PermissionError("Acces refuzat demonstrativ")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", no_access)
    assert inspect_local_file(path).state == "inaccessible"
    with pytest.raises(ValidationError, match="Acces refuzat"):
        build_draft("a@b.ro", "", "S", "B", attachments=[path])


def test_project_browser_includes_unregistered_files_and_external_locations(ws, tmp_path):
    project = ws.create_node(Kind.PROJECT, "Proiect")
    task = ws.create_node(Kind.TASK, "Task", project.id)
    files = FileService(ws)
    managed = files.files_dir(project.id)
    managed.mkdir(exist_ok=True)
    manual = managed / "pus manual.txt"
    manual.write_text("document")
    sub = managed / "folder"
    sub.mkdir()
    (sub / "alt.txt").write_text("alt")
    external = tmp_path / "extern"
    external.mkdir()
    files.add_external(task.id, external)
    locations = files.browse_locations(task.id)
    assert managed in [item.path for item in locations]
    assert external in [item.path for item in locations]
    entries = files.browse_directory(managed)
    assert [(item.path.name, item.is_dir) for item in entries] == [("folder", True), ("pus manual.txt", False)]
    assert not ws.get(project.id).attachments  # Discovery does not register manual files.
    with pytest.raises(StorageError, match="nu poate fi citit"):
        files.browse_directory(managed / "lipsește")


class FakeMailItem:
    """Records concrete COM calls without constructing Outlook or sending real messages."""
    def __init__(self, *, fail_attachment=None, fail_send=False, resolved=True):
        self.calls = []
        self.paths = []
        self.Attachments = SimpleNamespace(Add=self.add)
        self.Recipients = SimpleNamespace(ResolveAll=lambda: resolved)
        self.fail_attachment, self.fail_send = fail_attachment, fail_send

    def add(self, path):
        self.calls.append(("attach", path))
        if len(self.paths) == self.fail_attachment:
            raise RuntimeError("Politica Outlook refuză fișierul")
        self.paths.append(path)

    def Display(self, modal):
        self.calls.append(("display", modal))

    def Send(self):
        self.calls.append(("send",))
        if self.fail_send:
            raise RuntimeError("COM connection lost")

    def Close(self, mode):
        self.calls.append(("close", mode))


def com_backend(item):
    backend = OutlookComBackend()
    created = []
    backend._connect = lambda: (SimpleNamespace(CreateItem=lambda kind: created.append(kind) or item), None)
    return backend, created


@pytest.mark.parametrize("send", [False, True])
def test_real_backend_method_adds_same_files_before_display_or_send(documents, send):
    before = [path.read_bytes() for path in documents]
    item = FakeMailItem()
    backend, created = com_backend(item)
    result = backend.send_mail(["a@b.ro"], ["c@d.ro"], "S", "  Și\n    corp\n", send=send,
                               attachments=[str(path) for path in documents])
    assert result == ("submitted" if send else "displayed")
    assert created == [0] and item.paths == [str(path) for path in documents]
    assert item.calls[-1][0] == ("send" if send else "display")
    assert all(call[0] == "attach" for call in item.calls[:-1])
    assert item.Body == "  Și\n    corp\n"
    assert [path.read_bytes() for path in documents] == before


@pytest.mark.parametrize("send", [False, True])
def test_attachment_failure_never_displays_or_sends_partial_mail(documents, send):
    item = FakeMailItem(fail_attachment=1)
    backend, _ = com_backend(item)
    with pytest.raises(RuntimeError, match="Outlook a refuzat atașamentul"):
        backend.send_mail(["a@b.ro"], [], "S", "B", send=send, attachments=[str(p) for p in documents])
    assert [call[0] for call in item.calls] == ["attach", "attach", "close"]
    assert all(path.exists() for path in documents)


def test_backend_rechecks_files_and_classifies_send_error_as_uncertain(documents):
    item = FakeMailItem(fail_send=True)
    backend, created = com_backend(item)
    selected = [str(documents[0])]
    with pytest.raises(MailHandoffUncertain, match="COM connection lost"):
        backend.send_mail(["a@b.ro"], [], "S", "B", send=True, attachments=selected)
    documents[0].unlink()
    with pytest.raises(ValidationError):
        backend.send_mail(["a@b.ro"], [], "S", "B", send=True, attachments=selected)
    assert len(created) == 1


@pytest.fixture
def mail_ui(ui, monkeypatch):
    from test_outlook import FakeOutlook
    from focusdesk.ui.outlook_ui import OutlookController
    from focusdesk.ui.mail_ui import MailDialog
    errors = []
    monkeypatch.setattr("focusdesk.ui.mail_ui.show_error", lambda *args: errors.append(args[1]))
    monkeypatch.setattr("focusdesk.ui.mail_ui.show_info", lambda *args: None)
    monkeypatch.setattr("focusdesk.ui.mail_ui.confirm", lambda *args: True)
    backend = FakeOutlook()
    ui.outlook.shutdown()
    ui.outlook = OutlookController(ui, backend_factory=lambda: backend, use_com=False)
    ui.outlook.attach()
    dialog = MailDialog(ui.root, ui, ui.ws.get(ui.selected_id))
    dialog.to_var.set("ana@firma.ro")
    dialog.cc_var.set("ion@firma.ro")
    yield ui, dialog, backend, errors
    if dialog.winfo_exists():
        dialog.destroy()


@pytest.mark.parametrize("choice", ["current", "saved", None])
def test_unsaved_shared_buffer_choice_never_saves_other_metadata(ui, monkeypatch, choice):
    from focusdesk.ui.mail_ui import MailDialog
    details = ui.inspector.tab_by_title("Detalii")
    ui.open_task_space(ui.selected_id)
    original = ui.ws.get_description(details.node_id)
    current = "Ciornă curentă\n  cu indentare"
    ui.task_space.editor.replace("1.0", "end-1c", current)
    details.vars["title"].set("Titlu nesalvat")
    old_title = ui.ws.get(details.node_id).title
    assert details.desc.get("1.0", "end-1c") == current
    monkeypatch.setattr("focusdesk.ui.app.DescriptionSourceDialog.run", lambda self: self.destroy() or choice)
    seen = []

    def capture(self):
        seen.append(self.text.get("1.0", "end-1c"))
        self.text.insert("end", "Editat numai în e-mail")
        self.destroy()

    monkeypatch.setattr(MailDialog, "run", capture)
    ui.compose_mail(details.node_id)
    assert len(seen) == (0 if choice is None else 1)
    if seen:
        assert seen[0].endswith(current if choice == "current" else original)
    assert ui.ws.get_description(details.node_id) == original
    assert ui.ws.get(details.node_id).title == old_title
    assert details.desc.get("1.0", "end-1c") == current and details.is_dirty()
    assert details.vars["title"].get() == "Titlu nesalvat"


def test_editable_mail_snapshot_survives_refresh_and_does_not_change_task(mail_ui):
    app, dialog, _, _ = mail_ui
    details = app.inspector.tab_by_title("Detalii")
    original = details.desc.get("1.0", "end-1c")
    dialog.text.delete("1.0", "end")
    dialog.text.insert("1.0", "Text propriu\n  editabil")
    app.refresh_all()
    app.root.update()
    assert dialog.text.get("1.0", "end-1c") == "Text propriu\n  editabil"
    assert details.desc.get("1.0", "end-1c") == original


def test_remove_attachment_only_changes_mail_selection(mail_ui, documents):
    app, dialog, _, _ = mail_ui
    original = [p.read_bytes() for p in documents]
    reference = app.files.add_external(dialog.node_id, documents[0])
    dialog._select_attachments([*documents, documents[0]])
    assert len(dialog.attachments) == 2
    assert dialog.attachment_tree.item("0", "values")[3] != dialog.attachment_tree.item("1", "values")[3]
    dialog.attachment_tree.selection_set("0")
    dialog._remove_attachments()
    assert len(dialog.attachments) == 1 and dialog.attachments[0].path == str(documents[1])
    assert [p.read_bytes() for p in documents] == original
    assert reference.id in [a.id for a in app.ws.get(dialog.node_id).attachments]


def test_send_cancel_and_enter_do_not_handoff(mail_ui, monkeypatch):
    app, dialog, backend, _ = mail_ui
    monkeypatch.setattr("focusdesk.ui.mail_ui.confirm", lambda *args: False)
    dialog._on_ok()
    assert not dialog.pending and not backend.mails
    dialog.to_entry.event_generate("<Return>")
    app.root.update()
    assert not backend.mails
    dialog._cancel()
    assert not dialog.winfo_exists()


def test_deleted_file_blocks_handoff_with_form_preserved(mail_ui, documents):
    _, dialog, backend, errors = mail_ui
    dialog._select_attachments(documents)
    body = dialog.text.get("1.0", "end-1c")
    documents[0].unlink()
    dialog._on_ok()
    assert not dialog.pending and not backend.mails
    assert errors and dialog.attachments[0].state == "missing"
    assert dialog.text.get("1.0", "end-1c") == body
    assert len(dialog.attachments) == 2


def test_failure_keeps_every_field_and_attachments_then_explicit_retry(mail_ui, documents):
    app, dialog, backend, _ = mail_ui
    dialog._select_attachments(documents)
    original = dialog.collect()
    send = backend.send_mail
    backend.send_mail = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("Outlook refuză dimensiunea mesajului"))
    dialog._on_ok()
    assert pump(app, lambda: not dialog.pending)
    assert dialog.collect() == original
    assert "refuză dimensiunea" in dialog.message.cget("text")
    assert dialog.winfo_exists() and not backend.mails
    backend.send_mail = send
    dialog._on_ok()
    assert pump(app, lambda: not dialog.winfo_exists())
    assert len(backend.mails) == 1
    assert backend.mails[0]["attachments"] == [str(path) for path in documents]
    assert backend.thread_names == {"focusdesk-com"}


def test_repeated_click_and_second_controller_call_do_not_duplicate(mail_ui):
    app, dialog, backend, _ = mail_ui
    gate = threading.Event()
    original = backend.send_mail
    backend.send_mail = lambda *a, **k: gate.wait(3) and original(*a, **k)
    dialog._on_ok()
    dialog._on_ok()
    dialog._open_draft()
    assert dialog.pending and str(dialog.ok_btn.cget("state")) == "disabled"
    errors = []
    app.outlook.send_mail(dialog._validated_draft, True, lambda _: None, errors.append)
    assert isinstance(errors[0], ComBlocked)
    dialog._cancel()
    assert dialog.winfo_exists()
    gate.set()
    assert pump(app, lambda: not dialog.winfo_exists())
    assert len(backend.mails) == 1


@pytest.mark.parametrize("mode", ["timeout", "send_exception", "unknown_result"])
def test_uncertain_outcome_requires_outlook_check_and_never_auto_retries(mail_ui, monkeypatch, mode):
    app, dialog, backend, _ = mail_ui
    gate = threading.Event()
    original = backend.send_mail
    if mode == "timeout":
        monkeypatch.setattr("focusdesk.ui.outlook_ui.COM_TIMEOUT_S", .08)
        backend.send_mail = lambda *a, **k: gate.wait(3) and original(*a, **k)
    elif mode == "send_exception":
        backend.send_mail = lambda *a, **k: (_ for _ in ()).throw(MailHandoffUncertain("Răspuns pierdut după Send"))
    else:
        backend.send_mail = lambda *a, **k: "unexpected"
    dialog._on_ok()
    assert pump(app, lambda: dialog.uncertain)
    assert "incert" in dialog.message.cget("text")
    dialog._on_ok()
    dialog._open_draft()
    if mode == "timeout":
        gate.set()
        assert pump(app, lambda: not app.outlook.worker.blocked)
        # Drain a possible late result; it must not destroy or resubmit the form.
        pump(app, lambda: False, .15)
        assert len(backend.mails) <= 1
    assert dialog.winfo_exists() and dialog.uncertain
    monkeypatch.setattr("focusdesk.ui.mail_ui.confirm", lambda *a: False)
    dialog._checked_outlook()
    assert dialog.uncertain
    monkeypatch.setattr("focusdesk.ui.mail_ui.confirm", lambda *a: True)
    dialog._checked_outlook()
    assert not dialog.uncertain


def test_journal_failure_after_success_does_not_offer_transport_retry(mail_ui, monkeypatch):
    app, dialog, backend, _ = mail_ui
    notices = []
    monkeypatch.setattr("focusdesk.ui.mail_ui.show_info", lambda parent, text, title: notices.append(text))
    monkeypatch.setattr(app.ws, "add_note", lambda *a, **k: (_ for _ in ()).throw(StorageError("Disc ocupat")))
    dialog._on_ok()
    assert pump(app, lambda: not dialog.winfo_exists())
    assert len(backend.mails) == 1 and dialog.result["result"] == "submitted"
    assert "Disc ocupat" in notices[0] and "Nu retrimite" in notices[0]


def test_late_callback_cannot_write_into_other_workspace(mail_ui, tmp_path):
    from focusdesk.services.workspace import Workspace
    app, dialog, backend, _ = mail_ui
    gate = threading.Event()
    original = backend.send_mail
    backend.send_mail = lambda *a, **k: gate.wait(3) and original(*a, **k)
    old_ws = app.ws
    other = Workspace.open(tmp_path / "other", create=True)
    dialog._on_ok()
    app.ws = other  # Simulate workspace replacement while COM is in flight.
    gate.set()
    try:
        assert pump(app, lambda: not dialog.winfo_exists())
        assert len(backend.mails) == 1
        assert not old_ws.list_notes(dialog.node_id)
        assert not list((other.root / "nodes").rglob("notes.json"))
    finally:
        app.ws = old_ws
        other.close()


def test_task_unavailable_blocks_send(mail_ui):
    app, dialog, backend, errors = mail_ui
    app.ws.trash(dialog.node_id)
    dialog._on_ok()
    assert not backend.mails and not dialog.pending and errors
    assert dialog.winfo_exists()


def test_draft_and_send_through_real_worker_use_same_attachment_paths(mail_ui, documents):
    from focusdesk.ui.mail_ui import MailDialog
    app, dialog, backend, _ = mail_ui
    dialog._select_attachments(documents)
    dialog._open_draft()
    assert pump(app, lambda: not dialog.winfo_exists())
    second = MailDialog(app.root, app, app.ws.get(dialog.node_id))
    second.to_var.set("ana@firma.ro")
    second._select_attachments(documents)
    second._on_ok()
    assert pump(app, lambda: not second.winfo_exists())
    assert [mail["send"] for mail in backend.mails] == [False, True]
    assert backend.mails[0]["attachments"] == backend.mails[1]["attachments"] == [str(p) for p in documents]
    logs = app.ws.list_notes(dialog.node_id)
    assert len(logs) == 2 and all("Raport.txt" in note.text for note in logs)


def test_file_becomes_unreadable_after_selection(mail_ui, documents, monkeypatch):
    app, dialog, backend, errors = mail_ui
    dialog._select_attachments(documents)
    original = Path.open

    def deny(self, *args, **kwargs):
        if self == documents[0]:
            raise PermissionError("Fișier blocat")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", deny)
    dialog._on_ok()
    assert not dialog.pending and not backend.mails and errors
    assert dialog.attachments[0].state == "inaccessible"
    assert len(dialog.attachments) == 2


def test_controller_rechecks_after_confirmation_before_backend(mail_ui, documents, monkeypatch):
    app, dialog, backend, _ = mail_ui
    dialog._select_attachments(documents)

    def confirm_then_delete(*_):
        documents[0].unlink()
        return True

    monkeypatch.setattr("focusdesk.ui.mail_ui.confirm", confirm_then_delete)
    dialog._on_ok()
    assert pump(app, lambda: not dialog.pending)
    assert not backend.mails and dialog.winfo_exists()
    assert dialog.attachments[0].state == "missing"


def test_read_only_task_can_compose_without_journal_writes(mail_ui, monkeypatch):
    app, dialog, backend, _ = mail_ui
    monkeypatch.setattr(app.ws.repo, "read_only", True)
    before = {p: p.read_bytes() for p in app.ws.root.rglob("*") if p.is_file()}
    dialog._open_draft()
    assert pump(app, lambda: not dialog.winfo_exists())
    assert backend.mails[0]["send"] is False
    assert {p: p.read_bytes() for p in before} == before


def test_file_picker_folder_navigation_and_nested_grab(mail_ui, documents, monkeypatch):
    from focusdesk.ui.file_picker import TaskFilePicker
    app, dialog, _, _ = mail_ui
    app.root.deiconify()
    app.root.update()
    dialog.grab_set()
    files = app.files
    folder = files.files_dir(dialog.node_id)
    folder.mkdir(exist_ok=True)
    sub = folder / "documente"
    sub.mkdir()
    path = sub / "manual.txt"
    path.write_text("document")
    picker = TaskFilePicker(dialog, files, dialog.node_id)
    key = next(key for key, entry in picker.entries.items() if entry.is_dir)
    picker.tree.selection_set(key)
    picker._activate()
    assert picker.directory == sub
    file_key = next(iter(picker.entries))
    picker.tree.selection_set(file_key)
    picker.after(50, picker._on_ok)
    result = picker.run()
    assert result == [str(path)]
    assert dialog.grab_current() is dialog
    assert path.read_text() == "document"
    dialog.grab_release()


def test_mail_snapshot_does_not_reset_external_edit_conflict_baselines(ws):
    from focusdesk.errors import ExternalModificationError
    node = ws.create_node(Kind.TASK, "Task", description="Versiune inițială")
    ws.get_description(node.id)  # Existing editor baseline.
    desc_key, node_key = (node.id, "description.md"), (node.id, "node.json")
    ws.repo._edit_baselines.update({key: ws.repo._hashes[key] for key in (desc_key, node_key)})
    baselines = dict(ws.repo._edit_baselines)
    hashes = dict(ws.repo._hashes)
    path = ws.node_dir(node.id) / "description.md"
    path.write_text("Modificat extern", encoding="utf-8")
    assert default_body(ws, node).endswith("Modificat extern")
    assert ws.repo._edit_baselines == baselines and ws.repo._hashes == hashes
    with pytest.raises(ExternalModificationError):
        ws.set_description(node.id, "Nu suprascrie schimbarea externă")
    assert path.read_text(encoding="utf-8") == "Modificat extern"


def test_description_source_defaults_to_current_and_supports_cancel(ui):
    from focusdesk.ui.mail_ui import DescriptionSourceDialog
    current = DescriptionSourceDialog(ui.root)
    current._on_ok()
    assert current.result == "current"
    saved = DescriptionSourceDialog(ui.root)
    saved._saved()
    assert saved.result == "saved"
    cancelled = DescriptionSourceDialog(ui.root)
    cancelled.destroy()
    assert cancelled.result is None


def test_file_picker_sorts_full_directory_before_paging(mail_ui):
    from focusdesk.ui.file_picker import TaskFilePicker
    app, dialog, _, _ = mail_ui
    directory = app.files.files_dir(dialog.node_id)
    directory.mkdir(exist_ok=True)
    for i in reversed(range(205)):
        (directory / f"Document {i:03}.txt").write_text("test")
    picker = TaskFilePicker(dialog, app.files, dialog.node_id)
    assert len(picker.tree.get_children()) == 200
    names = [picker.entries[key].path.name for key in picker.tree.get_children()]
    assert names[0] == "Document 000.txt" and names[-1] == "Document 199.txt"
    picker.tree.selection_set("0")
    picker._append()
    assert len(picker.tree.get_children()) == 205 and picker.tree.selection() == ("0",)
    picker.destroy()
