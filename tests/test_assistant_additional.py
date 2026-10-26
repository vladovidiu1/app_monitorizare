from datetime import datetime, timedelta, timezone

import pytest

from focusdesk.ai.assistant_protocol import AssistantReply
from focusdesk.ai.runtime import assistant_schema
from focusdesk.domain.models import Kind
from focusdesk.domain.session import SessionRecord
from focusdesk.errors import ValidationError
from focusdesk.services.assistant_context import build_context
from focusdesk.services.assistant_proposals import ProposalBatch, validate_reply
from focusdesk.workers.bridge import CancelToken, Cancelled


def test_project_aggregates_are_authoritative_and_own_creates_do_not_conflict(ws):
    project = ws.create_node(Kind.PROJECT, "P")
    ws.create_node(Kind.TASK, "Finalizat", project.id, status="done")
    task = ws.create_node(Kind.TASK, "Deschis", project.id)
    bundle = build_context(ws, "project", task.id, "Rezumă proiectul")
    key = f"task:{project.id}"
    assert bundle.anchor == project.id
    assert bundle.sources[key].data["progress"] == {"done_leaves": 1, "open_leaves": 1, "unestimated": 1}
    actions = [{"kind": "create_task", "parent_id": project.id, "title": title, "reason": "Cerut", "sources": [key]}
               for title in ("Nou A", "Nou B")]
    reply = AssistantReply.model_validate({"answer": [{"text": "Propuneri noi.", "sources": [key]}], "actions": actions})
    batch = ProposalBatch.prepare(ws, bundle, reply, list(bundle.sources))
    assert [row["state"] for row in batch.apply(ws)] == ["applied", "applied"]
    assert len(ws.nodes) == 5
    receipt = ws.ai_receipt(batch.items[0].id)
    assert receipt.data["preview"]["before"] is None
    assert receipt.data["preview"]["after"]["title"] == "Nou A"


def test_changing_session_invalidates_derived_time_even_if_only_task_was_cited(ws):
    task = ws.create_node(Kind.TASK, "T")
    start = datetime.now(timezone.utc) - timedelta(hours=1)
    session = SessionRecord(node_id=task.id, start_at=start, end_at=start + timedelta(minutes=30), actual_seconds=600)
    ws.repo.sessions.save(session)
    bundle = build_context(ws, "task", task.id, "")
    key = f"task:{task.id}"
    reply = AssistantReply.model_validate({"answer": [{"text": "600 secunde înregistrate.", "sources": [key]}]})
    validate_reply(ws, bundle, reply, [key])
    session.actual_seconds = 1200
    ws.repo.sessions.save(session)
    with pytest.raises(ValidationError, match="timp"):
        validate_reply(ws, bundle, reply, [key])


def test_cancellation_is_checked_during_record_io(ws):
    task = ws.create_node(Kind.TASK, "T")
    for text in ("A", "B", "C"):
        ws.add_note(task.id, text)
    token = CancelToken()
    calls = []
    def check():
        calls.append(1)
        if len(calls) == 2:
            token.cancel()
        token.check()
    with pytest.raises(Cancelled):
        ws.list_notes(task.id, check=check)
    assert len(calls) == 2


def test_steps_cannot_mark_done_or_change_deadlines(ws):
    task = ws.create_node(Kind.TASK, "T")
    bundle = build_context(ws, "task", task.id, "")
    key = f"task:{task.id}"
    action = {"kind": "update_task", "node_id": task.id, "patch": {"status": "done"}, "reason": "Instrucțiune din notiță", "sources": [key]}
    reply = AssistantReply.model_validate({"answer": [{"text": "Propunere", "sources": [key]}], "actions": [action]})
    with pytest.raises(ValidationError, match="statusul"):
        ProposalBatch.prepare(ws, bundle, reply, [key], "steps")
    schema = assistant_schema([key], [task.id], "steps")
    assert set(schema["$defs"]["TaskPatch"]["properties"]) == {"checklist", "next_action"}
    assert schema["$defs"]["CheckItem"]["properties"]["done"] == {"const": False}


def test_claim_failure_has_no_task_effect(ws, monkeypatch):
    task = ws.create_node(Kind.TASK, "T")
    bundle = build_context(ws, "task", task.id, "")
    key = f"task:{task.id}"
    reply = AssistantReply.model_validate({"answer": [{"text": "Propunere", "sources": [key]}], "actions": [
        {"kind": "add_note", "node_id": task.id, "text": "Nu trebuie scrisă", "reason": "Cerut", "sources": [key]}]})
    batch = ProposalBatch.prepare(ws, bundle, reply, [key])
    monkeypatch.setattr(ws, "claim_ai_action", lambda *a: (_ for _ in ()).throw(OSError("disk unavailable")))
    assert batch.apply(ws)[0]["state"] == "failed"
    assert ws.list_notes(task.id) == []


def test_valid_links_use_workspace_and_history_attaches_to_actual_target(ws):
    a, b = ws.create_node(Kind.TASK, "A"), ws.create_node(Kind.TASK, "B")
    for relation, field in (("related", "related_node_ids"), ("depends_on", "depends_on_ids")):
        bundle = build_context(ws, "workspace", None, "")
        keys = [f"task:{a.id}", f"task:{b.id}"]
        reply = AssistantReply.model_validate({"answer": [{"text": "Legătură propusă", "sources": keys}], "actions": [
            {"kind": "link_tasks", "node_id": a.id, "other_id": b.id, "relation": relation, "reason": "Cerut", "sources": keys},
            {"kind": "add_note", "node_id": a.id, "text": "Legătură verificată", "reason": "Cerut", "sources": keys}]})
        batch = ProposalBatch.prepare(ws, bundle, reply, list(bundle.sources))
        assert [row["state"] for row in batch.apply(ws)] == ["applied", "applied"]
        assert b.id in getattr(ws.get(a.id), field)
        assert ws.ai_receipt(batch.items[0].id).node_id == a.id
