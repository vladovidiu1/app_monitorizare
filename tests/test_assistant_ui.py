import json
import time
import tkinter as tk
from tkinter import ttk
from uuid import uuid4

from test_ai_ui import ui
from focusdesk.ai.assistant_protocol import AssistantReply
from focusdesk.ai.protocol import Response
from focusdesk.domain.models import Kind
from focusdesk.services.assistant_context import build_context
from focusdesk.services.assistant_proposals import ProposalBatch
from focusdesk.ui.assistant_ui import AssistantPanel, EditOperationDialog, ProposalReview, open_source


def pump(app, predicate, seconds=5):
    end = time.monotonic() + seconds
    while not predicate() and time.monotonic() < end:
        app.root.update()
        time.sleep(0.01)
    assert predicate()


def test_toolbar_chat_is_nonmodal_and_inspector_has_assistant(ui):
    ui.assistant_btn.invoke()
    window = ui.assistant_window
    assert window.winfo_exists() and ui.root.grab_current() is None
    panel = window.panel
    assert ui.selected_id in panel.context_label.get()
    assert str(panel.scope_box.cget("state")) == "readonly"
    assert ui.inspector.tab_by_title("Asistent").node_id == ui.selected_id
    panel.scope.set("Întreg workspace")
    panel.on_selection()
    assert "înregistrări relevante" in panel.context_label.get()
    window.destroy()


def test_chat_retrieval_citations_and_no_automatic_apply(ui, monkeypatch):
    ui.config.ai.enabled = True
    ui.open_assistant()
    panel = ui.assistant_window.panel
    captured = {}
    def request(config, action, instruction, context, callback, **kwargs):
        captured.update(id=str(uuid4()), callback=callback, payload=json.loads(context), action=action)
        return captured["id"]
    monkeypatch.setattr(ui.ai, "request", request)
    panel.entry.insert("1.0", "Propune o notiță")
    panel.send()
    pump(ui, lambda: "callback" in captured)
    assert captured["action"] == "assistant"
    key = f"task:{ui.selected_id}"
    reply = AssistantReply.model_validate({"answer": [{"text": "Propun o notiță pentru task.", "sources": [key]}],
        "actions": [{"kind": "add_note", "node_id": ui.selected_id, "text": "Propunere", "reason": "Cerut", "sources": [key]}]})
    captured["callback"](Response(request_id=captured["id"], kind="result", assistant=reply, context_keys=[key]))
    assert panel._batch and len(panel._batch.items) == 1
    assert ui.ws.list_notes(ui.selected_id) == []
    assert ui.selected_id in panel.transcript.get("1.0", "end")
    assert panel.history and panel.review_button.instate(["!disabled"])


def test_workspace_switch_or_context_change_ignores_late_result(ui, monkeypatch):
    ui.config.ai.enabled = True
    ui.open_assistant()
    panel = ui.assistant_window.panel
    captured = {}
    def request(*args, **kwargs):
        captured.update(id=str(uuid4()), callback=args[-1])
        return captured["id"]
    monkeypatch.setattr(ui.ai, "request", request)
    panel.entry.insert("1.0", "Unde am rămas?")
    panel.send()
    pump(ui, lambda: "callback" in captured)
    old_id = ui.selected_id
    ui.ai.invalidate_workspace()
    captured["callback"](Response(request_id=captured["id"], kind="result", assistant=AssistantReply.model_validate({
        "answer": [{"text": "Târziu", "sources": [f"task:{old_id}"]}]}), context_keys=[f"task:{old_id}"]))
    assert panel._reply is None and "Târziu" not in panel.transcript.get("1.0", "end")
    panel.scope.set("Întreg workspace")
    panel.on_selection()
    assert panel.history == []


def test_review_accept_modify_reject_and_repeated_click(ui, monkeypatch):
    bundle = build_context(ui.ws, "task", ui.selected_id, "")
    key = f"task:{ui.selected_id}"
    reply = AssistantReply.model_validate({"answer": [{"text": "Propuneri", "sources": [key]}], "actions": [
        {"kind": "add_note", "node_id": ui.selected_id, "text": "Prima", "reason": "Cerut", "sources": [key]},
        {"kind": "add_note", "node_id": ui.selected_id, "text": "Respinsă", "reason": "Cerut", "sources": [key]}]})
    batch = ProposalBatch.prepare(ui.ws, bundle, reply, list(bundle.sources))
    window = ProposalReview(ui, batch)
    editor = EditOperationDialog(window, ui, batch, 0)
    assert editor.validate()
    editor.destroy()
    monkeypatch.setattr("focusdesk.ui.assistant_ui.confirm", lambda *a: True)
    window.accept([0])
    window.accept([0])
    assert len(ui.ws.list_notes(ui.selected_id)) == 1
    window.tree.selection_set("1")
    window.reject()
    assert batch.items[1].state == "rejected"
    assert "applied" in window.status.get() or batch.items[0].state == "applied"
    window.destroy()


def test_source_link_opens_exact_note_and_email_only_opens_existing_editor(ui, monkeypatch):
    note = ui.ws.add_note(ui.selected_id, "Înregistrare exactă")
    bundle = build_context(ui.ws, "task", ui.selected_id, "")
    open_source(ui, ui.ws.id, bundle.sources[f"note:{note.id}"])
    windows = [child for child in ui.root.winfo_children() if isinstance(child, tk.Toplevel)]
    assert windows
    assert any(note.id in str(child.cget("text")) for window in windows for child in window.winfo_children() if isinstance(child, ttk.Label))
    for window in windows:
        window.destroy()
    ui.open_assistant()
    panel = ui.assistant_window.panel
    key = f"task:{ui.selected_id}"
    panel._bundle = bundle
    panel._reply = AssistantReply.model_validate({"answer": [{"text": "Ciornă", "sources": [key]}], "email": {
        "node_id": ui.selected_id, "subject": "Clarificare", "body": "Bună ziua", "reason": "Cerut", "sources": [key]}})
    panel._batch = ProposalBatch.prepare(ui.ws, bundle, panel._reply, list(bundle.sources))
    captured = []
    monkeypatch.setattr("focusdesk.ui.assistant_ui.confirm", lambda *a: True)
    monkeypatch.setattr(ui, "compose_mail", lambda node_id, **kw: captured.append((node_id, kw)))
    panel.email()
    assert captured[0][1]["ai_draft"].subject == "Clarificare"
    assert ui.ws.list_notes(ui.selected_id)[0].text == "Înregistrare exactă"
