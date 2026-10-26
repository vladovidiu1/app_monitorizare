from focusdesk.ai.assistant_protocol import AssistantReply
from focusdesk.domain.models import Kind
from focusdesk.services.assistant_context import build_context
from focusdesk.services.assistant_proposals import ProposalBatch


def test_unreadable_receipt_mid_batch_preserves_partial_success(ws, monkeypatch):
    task = ws.create_node(Kind.TASK, "T")
    bundle = build_context(ws, "task", task.id, "")
    key = f"task:{task.id}"
    reply = AssistantReply.model_validate({"answer": [{"text": "Propuneri", "sources": [key]}], "actions": [
        {"kind": "add_note", "node_id": task.id, "text": text, "reason": "Cerut", "sources": [key]}
        for text in ("Prima", "A doua", "A treia")]})
    batch = ProposalBatch.prepare(ws, bundle, reply, [key])
    original = ws.ai_receipt
    def failing(item_id):
        if item_id == batch.items[1].id:
            raise OSError("history unreadable")
        return original(item_id)
    monkeypatch.setattr(ws, "ai_receipt", failing)
    results = batch.apply(ws)
    assert [row["state"] for row in results] == ["applied", "uncertain", "not_run"]
    assert [note.text for note in ws.list_notes(task.id)] == ["Prima"]
    assert original(batch.items[0].id).data["state"] == "applied"
