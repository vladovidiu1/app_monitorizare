from __future__ import annotations

import threading
import time
import tkinter as tk
from uuid import uuid4

import pytest

from focusdesk.ai.protocol import Proposal, Response
from focusdesk.domain.models import Kind
from focusdesk.ui.app import FocusDeskApp
from focusdesk.ui.ai_ui import AiWindow
from focusdesk.ui.settings_dialog import SettingsDialog


@pytest.fixture
def ui(ws, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    try:
        app = FocusDeskApp()
    except tk.TclError as exc:
        pytest.skip(f"Tk display indisponibil: {exc}")
    app.root.withdraw()
    # Release the fixture lock before opening it through the real application.
    ws.close()
    assert app.open_workspace(ws.root)
    node = app.ws.create_node(Kind.TASK, "Test AI", description="Descriere locală")
    app.refresh_all()
    app.select_node(node.id, reveal=True)
    yield app
    engine = app.ai.engine
    app.on_close()
    if engine:
        assert engine.wait_closed()


def test_application_and_settings_work_without_ai_model(ui):
    assert not ui.config.ai.enabled and ui.ai.engine is None
    dialog = SettingsDialog(ui.root, ui)
    assert "AI" in [dialog.nb.tab(tab, "text") for tab in dialog.nb.tabs()]
    dialog.ai_page.enabled.set(True)
    dialog.ai_page.context.set("4096")
    dialog.ai_page.threads.set("2")
    assert dialog.validate() and dialog.collect()
    assert ui.config.ai.enabled and ui.config.ai.threads == 2
    assert ui.ai.engine is None  # saving configuration never loads the model
    dialog.destroy()


def test_ai_preview_confirmation_and_single_application(ui, monkeypatch):
    ui.config.ai.enabled = True
    captured = {}
    def fake_request(config, action, instruction, context, callback):
        captured.update(callback=callback, action=action, context=context, id=str(uuid4()))
        assert threading.current_thread() is threading.main_thread()
        return captured["id"]
    monkeypatch.setattr(ui.ai, "request", fake_request)
    monkeypatch.setattr("focusdesk.ui.ai_ui.confirm", lambda *a: True)
    window = AiWindow(ui)
    ui.ai_window = window
    window.operation.set("Propune o notiță")
    window.generate()
    node_id = ui.selected_id
    assert "Descriere locală" in captured["context"]
    captured["callback"](Response(request_id=captured["id"], kind="result",
        proposal=Proposal(action="add_note", title="", text="Propunere verificată")))
    assert ui.ws.list_notes(node_id) == []
    window.apply()
    window.apply()
    assert len(ui.ws.list_notes(node_id)) == 1
    window.destroy()


def test_late_response_after_cancel_is_ignored(ui, monkeypatch):
    ui.config.ai.enabled = True
    captured = {}
    def fake_request(*args):
        captured["callback"] = args[-1]
        return "b3595d47-d4e1-4595-9ffc-d801ffdcaa8a"
    monkeypatch.setattr(ui.ai, "request", fake_request)
    window = AiWindow(ui)
    ui.ai_window = window
    window.generate()
    window.cancel()
    captured["callback"](Response(request_id="b3595d47-d4e1-4595-9ffc-d801ffdcaa8a", kind="result",
        proposal=Proposal(action="create_subtask", title="Neaplicat", text="Nu aplica")))
    assert window._proposal is None
    window.destroy()


def test_model_test_missing_file_reports_error_and_ui_stays_usable(ui):
    dialog = SettingsDialog(ui.root, ui)
    dialog.ai_page.path.set(str(ui.ws.root.parent / "absent.gguf"))
    dialog.ai_page.test()
    end = time.monotonic() + 8
    while dialog.ai_page._request_id and time.monotonic() < end:
        ui.root.update()
        time.sleep(0.02)
    assert dialog.ai_page._request_id is None
    assert "absent" in dialog.ai_page.status.get()
    ui.ws.create_node(Kind.TASK, "Editarea funcționează în continuare")
    assert any(n.title.startswith("Editarea funcționează") for n in ui.ws.nodes.values())
    dialog.destroy()
