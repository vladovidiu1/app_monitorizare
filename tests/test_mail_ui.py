import copy
import threading
import time
from uuid import uuid4

from test_ai_ui import ui
from test_mail_monitor import NOW, configure, message, imported, analysis
from focusdesk.ai.protocol import Response
from focusdesk.integrations.mail_fake import FakeMailBackend
from focusdesk.ui.outlook_ui import OutlookController
from focusdesk.ui.settings_dialog import SettingsDialog


def pump(app, predicate, seconds=5):
    until = time.monotonic() + seconds
    while not predicate() and time.monotonic() < until:
        app.root.update()
        time.sleep(0.01)
    assert predicate()


def attach(ui, backend):
    ui.outlook.shutdown()
    ui.outlook = OutlookController(ui, backend_factory=lambda: backend, use_com=False)
    ui.outlook.attach()


def test_page_is_distinct_and_settings_default_to_no_import(ui):
    ui.show_view("mail_review", select_sidebar=True)
    assert ui.current_view == "mail_review" and ui.mail_page is not ui.tasklist
    assert not ui.ws.settings.mail_monitor.enabled
    dialog = SettingsDialog(ui.root, ui)
    assert "Mailuri" in [dialog.nb.tab(tab, "text") for tab in dialog.nb.tabs()]
    assert not dialog.mail_page.enabled.get()
    dialog.destroy()


def test_tick_scans_through_existing_com_worker_without_overlap(ui):
    # Use current timestamps for the real tick's initial window.
    from datetime import datetime, timezone, timedelta
    data = message()
    stamp = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    for key in ("sent_at", "received_at", "modified_at"):
        data["header"][key] = stamp
    backend = FakeMailBackend([data])
    before = copy.deepcopy(backend.messages)
    attach(ui, backend)
    configure(ui.ws)
    ui._tick()
    assert ui.mail_watch.active
    ui.mail_watch.scan()  # overlapping request is refused, never queued
    pump(ui, lambda: not ui.mail_watch.active)
    assert len(ui.ws.mail_records()) == 1
    assert sum(kind == "page" for kind, _ in backend.calls) == 1
    assert all(ident != threading.get_ident() for _, ident in backend.calls)
    assert backend.messages == before


def test_com_unavailable_is_controlled_and_checkpoints_are_not_advanced(ui):
    backend = FakeMailBackend()
    backend.available = False
    attach(ui, backend)
    configure(ui.ws)
    ui.mail_watch.scan()
    pump(ui, lambda: not ui.mail_watch.active)
    assert "indisponibil" in ui.mail_watch.status
    assert all(cursor.offset == 0 for cursor in ui.ws.mail_state().cursors.values())
    assert ui.ws.mail_records() == []


def test_ai_estimate_does_not_create_task_and_late_workspace_reply_is_ignored(ui, monkeypatch):
    ui.config.ai.enabled = True
    record = imported(ui.ws)
    ui.show_view("mail_review")
    ui.mail_page.select_message(record.id)
    captured = {}
    def request(*args, **kwargs):
        captured.update(id=str(uuid4()), callback=args[-1], action=args[1])
        return captured["id"]
    monkeypatch.setattr(ui.ai, "request", request)
    count = len(ui.ws.nodes)
    ui.mail_page.analyze()
    pump(ui, lambda: "callback" in captured)
    assert captured["action"] == "analyze_mail"
    captured["callback"](Response(request_id=captured["id"], kind="result", mail_analysis=analysis()))
    assert len(ui.ws.nodes) == count
    assert ui.ws.mail_get(record.id).state == "proposed"
    assert "neconfirmată" in ui.mail_page.text.get("1.0", "end")
    monkeypatch.setattr("focusdesk.ui.mail_monitor_ui.confirm", lambda *a: True)
    captured.clear()
    ui.mail_page.analyze()
    pump(ui, lambda: "callback" in captured)
    ui.ai.invalidate_workspace()
    ui.mail_watch.invalidate()
    captured["callback"](Response(request_id=captured["id"], kind="result", mail_analysis=analysis()))
    assert len(ui.ws.nodes) == count


def test_timeout_blocks_followup_until_com_returns(ui):
    from focusdesk.workers.com_worker import ComWorker
    backend = FakeMailBackend()
    backend.block = threading.Event()
    attach(ui, backend)
    errors = []
    worker = ui.outlook.worker
    worker.submit(lambda b: b.list_mail_folders(), lambda _: None, errors.append, timeout_s=0.03, name="fake-blocked")
    pump(ui, lambda: bool(errors))
    configure(ui.ws)
    ui.mail_watch.scan()
    assert not ui.mail_watch.active and "blocat" in ui.mail_watch.status
    backend.block.set()
    pump(ui, lambda: not worker.busy)
