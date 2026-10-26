"""Test de integrare UI: porneste fereastra reala (invizibila) si parcurge fluxurile principale.

Nu deschide dialoguri modale (ar bloca testul); fluxurile cu dialoguri sunt acoperite prin servicii si prin construirea
dialogurilor fara `run()`.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import tkinter as tk
import faulthandler
from pathlib import Path
from datetime import datetime, timedelta, timezone
from tkinter import messagebox

import pytest

# Watchdog: daca un test UI se blocheaza (dialog modal neasteptat), scrie stivele si opreste procesul.
_HANG_FILE = Path(tempfile.gettempdir()) / "focusdesk_ui_hang.txt"


def _watchdog() -> None:
    with open(_HANG_FILE, "w") as f:
        faulthandler.dump_traceback(file=f, all_threads=True)
        f.flush()
    os._exit(1)


_wd = threading.Timer(float(os.environ.get("FD_UI_WATCHDOG", "400")), _watchdog)
_wd.daemon = True
_wd.start()

from focusdesk.config import AppConfig
from focusdesk.domain.models import Kind, Status
from focusdesk.services.demo import create_demo_workspace

UTC = timezone.utc


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    base = tmp_path_factory.mktemp("ui")
    mp = pytest.MonkeyPatch()
    mp.setenv("APPDATA", str(base / "appdata"))
    mp.setattr(messagebox, "showinfo", lambda *a, **k: None)
    mp.setattr(messagebox, "showerror", lambda *a, **k: None)
    mp.setattr(messagebox, "askyesno", lambda *a, **k: True)
    modal_log: list[tuple[str, str]] = []

    def fake_choice(parent, title, message, choices):
        modal_log.append((title, message))  # un dialog modal neasteptat devine o eroare de test, nu un blocaj
        return "cancel"

    from focusdesk.ui import app as app_mod, common, tab_files, tab_versions

    for mod in (common, app_mod, tab_files, tab_versions):
        mp.setattr(mod, "ask_choice", fake_choice, raising=False)
    ws_path = base / "demo"
    create_demo_workspace(ws_path)
    try:
        from focusdesk.ui.app import FocusDeskApp

        a = FocusDeskApp()
    except tk.TclError as exc:  # pragma: no cover - fara display
        mp.undo()
        pytest.skip(f"Tk indisponibil: {exc}")
    a.root.attributes("-alpha", 0.0)  # fereastra reala, dar invizibila
    errors: list[str] = []
    a.root.report_callback_exception = lambda exc, val, tb: errors.append(f"{exc.__name__}: {val}")
    a.callback_errors = errors  # type: ignore[attr-defined]
    a.modal_log = modal_log  # type: ignore[attr-defined]
    assert a.open_workspace(ws_path)
    pump(a, lambda: False, 0.4)
    yield a
    try:
        a.inspector.revert()  # un test esuat poate lasa formular murdar -> dialog modal la inchidere
        if a.timer and a.timer.state is not None:
            a.timer.discard()
        a.on_close()
    except tk.TclError:
        pass
    mp.undo()


def pump(app, cond, timeout=5.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        app.root.update()
        if cond():
            return True
        time.sleep(0.02)
    return False


def no_errors(app):
    assert app.callback_errors == [], app.callback_errors
    assert app.modal_log == [], app.modal_log


def find(app, title):
    return next(n for n in app.ws.nodes.values() if n.title == title)


def test_window_layout_and_initial_state(app):
    assert app.root.title().startswith("FocusDesk")
    assert app.current_view == "today"
    assert app.today.winfo_ismapped()
    assert [app.inspector.nb.tab(t, "text") for t in app.inspector.nb.tabs()] == [
        "Detalii", "Subtask-uri", "Planificare", "Fișiere", "Jurnal", "Versiuni"]
    assert "Calendar: local" in app.status._labels["calendar"].cget("text")
    no_errors(app)


def test_all_views_and_every_node_with_every_tab_render(app):
    for key in ("today", "inbox", "waiting", "overdue", "calendar", "archive", "today"):
        app.show_view(key, select_sidebar=True)
        app.root.update()
        assert app.current_view == key
    for node in list(app.ws.nodes.values()):
        app.select_node(node.id, reveal=True)
        app.root.update()
        for title in [app.inspector.nb.tab(t, "text") for t in app.inspector.nb.tabs()]:
            if app.inspector.nb.tab(app.inspector.tab_by_title(title), "state") == "normal":
                app.inspector.show_tab(title)
                app.root.update()
        assert app.selected_id == node.id
    no_errors(app)


def test_search_and_list_filters(app):
    app.search_var.set("xml")
    app._run_search()
    app.root.update()
    assert app.current_view == "search:xml"
    titles = {app.tasklist.tv.item(i, "text") for i in app.tasklist.tv.get_children()}
    assert any("Verificare diferențe XML" in t for t in titles)
    app.search_var.set("")
    app._run_search()
    assert app.current_view == "today"
    node = find(app, "Validări XML")
    app.show_node_scope(node.id)
    app.tasklist.status_var.set("Toate")
    app.tasklist.text_var.set("raport")
    app.tasklist.refresh()
    assert len(app.tasklist.tv.get_children()) == 1
    app.tasklist.reset_filters()
    no_errors(app)


def test_details_tab_edit_and_save_persists(app):
    task = find(app, "Comparare câmpuri")
    app.select_node(task.id, reveal=True)
    tab = app.inspector.tab_by_title("Detalii")
    tab.vars["title"].set("Comparare câmpuri (editat)")
    tab.vars["priority"].set("Urgentă")
    tab.vars["due"].set("25.12.2026")
    tab.vars["due_time"].set("14:30")
    tab.vars["est"].set("1h30")
    tab.vars["tags"].set("a, b")
    tab.vars["next"].set("Pasul următor")
    tab.desc.insert("1.0", "Descriere nouă")
    tab._desc_changed()
    assert app.inspector.is_dirty()
    assert tab.save()
    n = app.ws.get(task.id)
    assert n.title == "Comparare câmpuri (editat)" and n.estimated_minutes == 90 and n.tags == ["a", "b"]
    assert n.due_at is not None and n.due_date is None
    assert app.ws.get_description(task.id) == "Descriere nouă"
    assert not app.inspector.is_dirty()
    # valoare invalida: nu se scrie nimic
    tab.vars["est"].set("abc")
    assert not tab.save()
    assert app.ws.get(task.id).estimated_minutes == 90
    tab.revert()
    no_errors(app)


def test_colleagues_import_selection_and_mail(app, tmp_path, monkeypatch):
    from openpyxl import Workbook
    from focusdesk.ui.colleagues_ui import ColleaguePickerDialog
    from focusdesk.ui.dialogs import NewNodeDialog
    from focusdesk.ui.mail_ui import MailDialog
    from focusdesk.ui.settings_dialog import SettingsDialog
    from focusdesk.services.colleagues import load_colleagues

    source = tmp_path / "colegi.xlsx"
    book = Workbook()
    book.active.append(["Nume complet", "Cod"])
    book.active.append(["Pintilie Vlad Ovidiu", "V13275"])
    book.active.append(["Ana Pop", "ana123"])
    book.save(source)
    book.close()
    monkeypatch.setattr("focusdesk.ui.settings_dialog.filedialog.askopenfilename", lambda **kwargs: str(source))
    settings = SettingsDialog(app.root, app)
    try:
        settings._import_colleagues()
        assert settings.colleagues_status.get() == "Colegi salvați: 2"
    finally:
        settings.destroy()
    picker = ColleaguePickerDialog(app.root, app.ws)
    try:
        picker.var.set("vlad 13275")
        assert picker.tv.get_children() == ("v13275",)
        picker.tv.selection_set("v13275")
        assert picker.validate()
        person = picker.collect()
    finally:
        picker.destroy()
    monkeypatch.setattr(ColleaguePickerDialog, "run", lambda self: (self.destroy(), person)[1])
    new = NewNodeDialog(app.root, app.ws)
    try:
        new.title_var.set("Task cu solicitant")
        new.more_open.set(True)
        new.requester_field._pick()
        result = new.collect()
        assert result["fields"]["requested_by"] == person
        task = app.ws.create_node(result["kind"], result["title"], **result["fields"])
    finally:
        new.destroy()
    app.select_node(task.id, reveal=True)
    tab = app.inspector.tab_by_title("Detalii")
    assert tab.requester_field.var.get() == "Pintilie Vlad Ovidiu (v13275)"
    tab.requester_field._clear()
    assert tab.save()
    assert app.ws.get(task.id).requested_by is None
    tab.requester_field._pick()
    assert tab.save()
    task = app.ws.get(task.id)
    mail = MailDialog(app.root, app, task)
    try:
        assert mail.to_var.get() == "v13275@eon.com"
        mail._add_colleague(mail.to_var)
        mail._add_colleague(mail.cc_var)
        assert mail._build().to == ["v13275@eon.com"]
        assert mail._build().cc == ["v13275@eon.com"]
    finally:
        mail.destroy()
    assert len(load_colleagues(app.ws)) == 2
    no_errors(app)


def test_subtasks_checklist_and_journal(app):
    task = find(app, "Raport pentru utilizator")
    app.select_node(task.id, reveal=True)
    sub = app.inspector.tab_by_title("Subtask-uri")
    sub.add_var.set("Subtask rapid")
    sub._quick_add()
    kids = [c.title for c in app.ws.children(task.id)]
    assert kids == ["Subtask rapid"]
    sub.check_var.set("pas mic")
    sub._add_check()
    sub.check_tv.selection_set("0")
    sub._toggle_check()
    assert [(c.text, c.done) for c in app.ws.get(task.id).checklist] == [("pas mic", True)]
    j = app.inspector.tab_by_title("Jurnal")
    j.entry.insert("1.0", "Notiță de test")
    j._add()
    assert any(n.text == "Notiță de test" for n in app.ws.list_notes(task.id))
    no_errors(app)


def test_files_and_checkpoint_flow(app, tmp_path):
    task = find(app, "Verificare diferențe XML")
    code = tmp_path / "cod"
    code.mkdir()
    (code / "main.py").write_text("print(1)\n", "utf-8")
    ext = tmp_path / "extern.txt"
    ext.write_text("x", "utf-8")
    app.select_node(task.id, reveal=True)
    app.run_write(lambda: app.files.set_code_folder(task.id, code), refresh=True)
    app.run_write(lambda: app.files.add_external(task.id, ext), refresh=True)
    files_tab = app.inspector.tab_by_title("Fișiere")
    files_tab.load(app.ws.get(task.id))
    assert len(files_tab.tv.get_children()) == 1 and str(code) in files_tab.code_lbl.cget("text")
    done = []
    app.create_checkpoint(task.id, "test", on_finished=lambda: done.append(1))
    assert pump(app, lambda: bool(done), 10)
    ver = app.inspector.tab_by_title("Versiuni")
    ver.load(app.ws.get(task.id))
    assert len(ver.tv.get_children()) == 1
    ver.tv.selection_set(ver.tv.get_children()[0])
    (code / "main.py").write_text("print(2)\n", "utf-8")
    ver._diff_current()
    assert pump(app, lambda: bool(ver.changes.get_children()), 10)
    ver.changes.selection_set(ver.changes.get_children()[0])
    ver._show_text_diff()
    assert "+print(2)" in ver.diff_text.get("1.0", "end")
    assert pump(app, lambda: "Git" in ver.git_lbl.cget("text") or "Branch" in ver.git_lbl.cget("text"), 10)
    no_errors(app)


def test_timer_session_lifecycle_in_ui(app):
    task = find(app, "Solicitare: raport lunar")
    t = app.timer
    t.start(task.id)
    app._tick()
    assert "Sesiune:" in app.status._labels["timer"].cget("text")
    assert app.timer_active()
    t.pause()
    app._tick()
    assert "Pauză" in app.status._labels["timer"].cget("text")
    t.resume()
    s = t.stop(summary="Gata pentru azi", next_action="Continuă mâine")
    app._tick()
    assert s.status == "done" and not app.timer_active()
    assert app.last_worked_node() is not None
    app.show_view("today", select_sidebar=True)
    app.today.refresh()
    app.refresh_all()
    no_errors(app)


def test_calendar_page_and_plan_tab_with_sessions(app):
    task = find(app, "Verificare diferențe XML")
    start = datetime.now(UTC).replace(second=0, microsecond=0) + timedelta(days=1, hours=1)
    app.sessions.create(task.id, start, start + timedelta(hours=1), reserve_calendar=True)
    app.show_view("calendar", select_sidebar=True)
    app.root.update()
    assert any(app.calendar_page.tv.get_children(i) for i in app.calendar_page.tv.get_children())
    app.select_node(task.id, reveal=True)
    plan = app.inspector.tab_by_title("Planificare")
    plan.load(app.ws.get(task.id))
    assert len(plan.tv.get_children()) >= 1
    no_errors(app)


def test_planner_dialog_builds_and_computes(app):
    from focusdesk.ui.planning import PlannerDialog

    task = find(app, "Extragere date din SAP")
    dlg = PlannerDialog(app.root, app, [task.id])
    dlg.tasks_tv.selection_set(task.id)
    dlg._calculate()
    assert pump(app, lambda: bool(dlg.proposals) or "Nu există timp" in dlg.note_lbl.cget("text"), 5)
    assert "doar local" in dlg.note_lbl.cget("text")
    dlg.destroy()
    no_errors(app)


def test_settings_dialog_collects_valid_settings(app):
    from focusdesk.ui.settings_dialog import SettingsDialog

    dlg = SettingsDialog(app.root, app)
    dlg.name_var.set("Workspace redenumit")
    dlg.b_ret.set("3")
    assert dlg.validate()
    assert dlg.collect() is not False
    assert app.ws.settings.backup.retention == 3 and app.ws.name == "Workspace redenumit"
    dlg.destroy()
    dlg2 = SettingsDialog(app.root, app)
    dlg2.tz_var.set("Nu/Exista")
    assert not dlg2.validate()
    dlg2.destroy()
    no_errors(app)


def test_theme_toggle_roundtrip(app):
    app.dark_var.set(True)
    app.toggle_theme()
    app.root.update()
    app.dark_var.set(False)
    app.toggle_theme()
    app.root.update()
    app.refresh_all()
    no_errors(app)


def test_outlook_flow_with_fake_backend(app):
    from test_outlook import FakeOutlook, FOLDER, STORE
    from focusdesk.ui.outlook_ui import OutlookController

    be = FakeOutlook()
    app.outlook.shutdown()
    app.outlook = OutlookController(app, backend_factory=lambda: be, use_com=False)
    app.outlook.attach()
    got = []
    app.outlook.test(on_ready=lambda d, c: got.append((d, c)))
    assert pump(app, lambda: bool(got), 5)
    assert got[0][0]["outlook"] and len(got[0][1]) == 2
    assert app.outlook.verified
    new = app.ws.settings.model_copy(deep=True)
    new.outlook.enabled, new.outlook.calendar_store_id, new.outlook.calendar_folder_id = True, STORE, FOLDER
    new.outlook.calendar_name = "Test"
    app.ws.update_settings(new)
    av = []
    app.outlook.get_availability(datetime.now().date(), datetime.now().date() + timedelta(days=1), av.append)
    assert pump(app, lambda: bool(av), 5)
    assert av[0].verified_scope == "outlook"
    task = find(app, "Verificare diferențe XML")
    sessions = app.sessions.for_node(task.id)
    pending = [s for s in sessions if s.reserve_calendar and s.status == "planned"]
    assert pending
    app.outlook.sync(quiet=True)
    assert pump(app, lambda: all(app.ws.repo.sessions.get(s.id).sync.state == "saved_locally" for s in pending), 5)
    assert len(be.items) == len(pending) and "Outlook — Test" in app.status._labels["calendar"].cget("text")
    from focusdesk.integrations.outlook import RawEvent

    meeting_start = datetime.now(UTC).replace(second=0, microsecond=0) + timedelta(days=1, hours=2)
    be.calendar_events = [
        RawEvent(meeting_start, meeting_start + timedelta(hours=1), "busy", subject="Ședință proiect"),
        RawEvent(pending[0].start_at, pending[0].end_at, "busy", subject="Duplicat FocusDesk",
                 session_id=pending[0].id),
    ]
    app.show_view("calendar", select_sidebar=True)
    app.calendar_page.refresh(force_outlook=True)
    assert pump(app, lambda: any(
        app.calendar_page.tv.item(child, "values")[1] == "Ședință proiect"
        for day in app.calendar_page.tv.get_children()
        for child in app.calendar_page.tv.get_children(day)
    ), 5)
    rows = [app.calendar_page.tv.item(child, "values")
            for day in app.calendar_page.tv.get_children()
            for child in app.calendar_page.tv.get_children(day)]
    assert not any(row[1] == "Duplicat FocusDesk" for row in rows)
    # a doua sincronizare nu duplica
    app.outlook.sync(quiet=True)
    pump(app, lambda: False, 0.3)
    assert len(be.items) == len(pending)
    no_errors(app)


def test_tree_list_shows_nested_hierarchy_and_quick_add(app):
    proj = find(app, "Validări XML")
    t1, sub = find(app, "Verificare diferențe XML"), find(app, "Comparare câmpuri (editat)")
    app.show_node_scope(proj.id)
    app.root.update()
    tv = app.tasklist.tv
    assert tv.parent(t1.id) == "" and tv.parent(sub.id) == t1.id
    app.select_node(sub.id, reveal=True)
    assert app.current_scope == proj.id and app.tasklist.scope_id == proj.id
    app.tasklist.add_var.set("Pas A")
    app.tasklist._quick_add(under_selection=True)
    app.root.update()
    pas = find(app, "Pas A")
    assert pas.parent_id == sub.id and tv.parent(pas.id) == sub.id
    app.select_node(pas.id, reveal=True)
    app.tasklist.add_var.set("Pas A1")
    app.tasklist._quick_add(under_selection=True)
    pas1 = find(app, "Pas A1")
    assert pas1.parent_id == pas.id and tv.parent(pas1.id) == pas.id
    assert len(app.ws.ancestors(pas1.id)) == 5  # folder SAP, proiect, 3 niveluri de task-uri
    app.select_node(pas1.id, reveal=True)
    app.outdent_selected()
    assert app.ws.get(pas1.id).parent_id == sub.id
    app.indent_selected()
    assert app.ws.get(pas1.id).parent_id == pas.id
    app.tasklist.add_var.set("La nivelul proiectului")
    app.tasklist._quick_add(under_selection=False)
    assert find(app, "La nivelul proiectului").parent_id == proj.id
    no_errors(app)


def test_mail_from_task_sends_through_outlook_and_journals(app):
    from test_outlook import FakeOutlook
    from focusdesk.services.mail import build_draft
    from focusdesk.ui.mail_ui import MailDialog
    from focusdesk.ui.outlook_ui import OutlookController

    be = FakeOutlook()
    app.outlook.shutdown()
    app.outlook = OutlookController(app, backend_factory=lambda: be, use_com=False)
    app.outlook.attach()
    task = find(app, "Raport pentru utilizator")
    dlg = MailDialog(app.root, app, task)
    assert "Raport pentru utilizator" in dlg.subject_var.get() and "Context" in dlg.text.get("1.0", "end")
    dlg.to_var.set("nu-este-adresa")
    assert not dlg.validate()
    dlg.to_var.set("ana@firma.ro")
    assert dlg.validate() and dlg.collect()["action"] == "send"
    dlg.destroy()
    draft = build_draft("ana@firma.ro", "", "Nelămuriri", "Când e termenul?")

    class Stub:
        action = "send"

        def __init__(self, *a, **k):
            pass

        def run(self):
            return {"action": Stub.action, "draft": draft}

    with pytest.MonkeyPatch.context() as m:
        m.setattr("focusdesk.ui.app.MailDialog", Stub)
        Stub.action = "draft"
        app.compose_mail(task.id)
        assert pump(app, lambda: bool(be.mails), 5) and be.mails[0]["send"] is False
        assert not any("E-mail trimis" in n.text for n in app.ws.list_notes(task.id))  # ciorna nu se jurnalizeaza
        Stub.action = "send"
        app.compose_mail(task.id)
        assert pump(app, lambda: len(be.mails) == 2, 5) and be.mails[1]["send"] is True
        assert pump(app, lambda: any("ana@firma.ro" in n.text for n in app.ws.list_notes(task.id)), 5)
        # esec la trimitere: nimic jurnalizat
        before = len(app.ws.list_notes(task.id))

        def boom(*a, **k):
            raise RuntimeError("Outlook indisponibil")

        be.send_mail = boom
        app.compose_mail(task.id)
        pump(app, lambda: False, 0.6)
        assert len(app.ws.list_notes(task.id)) == before
    no_errors(app)


def test_trash_restore_move_through_app_refresh(app):
    n = find(app, "Idei de automatizare")
    app.select_node(n.id, reveal=True)
    app.ws.trash(n.id)
    app.refresh_all()
    assert n.id not in app.ws.nodes and app.selected_id != n.id
    app.ws.restore(n.id)
    app.refresh_all()
    assert n.id in app.ws.nodes
    no_errors(app)


def test_worked_time_column_and_dashboard_window(app):
    from focusdesk.domain.session import SessionRecord
    from focusdesk.domain.labels import format_worked

    proj = app.ws.create_node(Kind.PROJECT, "Proiect timp lucrat", None)
    t1 = app.ws.create_node(Kind.TASK, "Task părinte timp", proj.id)
    sub = app.ws.create_node(Kind.TASK, "Subtask timp", t1.id)
    before = app.q.worked_map()
    start = datetime.now(timezone.utc) - timedelta(hours=3)
    for node, secs in ((t1, 1800), (sub, 5400)):
        s = SessionRecord(node_id=node.id, workspace_id=app.ws.id, start_at=start, end_at=start + timedelta(minutes=1),
                          status="done", origin="timer", actual_seconds=secs, started_actual_at=start,
                          stopped_actual_at=start + timedelta(seconds=secs))
        app.ws.repo.sessions.save(s)
    worked = app.q.worked_map()
    assert worked[sub.id] - before.get(sub.id, 0) == 5400
    assert worked[t1.id] - before.get(t1.id, 0) == 7200  # sesiunile proprii + cele ale subtask-ului
    assert format_worked(5400) == "1 h 30 min"

    app.inspector.revert()  # un formular murdar al testelor anterioare ar bloca schimbarea contextului
    app.inspector.load(None)
    app.selected_id = None
    app.modal_log.clear()
    app.refresh_all()  # sidebar-ul trebuie sa contina deja proiectul nou inainte de selectie
    app.root.update()
    app.select_node(t1.id, reveal=True)  # sincronizeaza si sidebar-ul, altfel selectia veche il readuce pe vechiul context
    app.root.update()
    app.tasklist.reset_filters()  # filtrele lasate de testele anterioare ascund randul
    app.tasklist.refresh()
    assert app.current_scope == proj.id
    assert app.tasklist.tv.exists(t1.id)
    shown = app.tasklist.tv.set(t1.id, "worked")
    assert shown == format_worked(worked[t1.id])

    day = start.astimezone(app.q.tz()).date()
    by_day = app.q.worked_by_day(day, day)
    assert by_day[day][sub.id] >= 5400
    app.open_dashboard()
    app.root.update()
    dash = app.dashboard
    assert dash is not None and dash.winfo_exists()
    dash.year, dash.month = day.year, day.month
    dash._select(day)
    app.root.update()
    assert sub.id in dash.tv.get_children()
    dash.destroy()
    no_errors(app)
