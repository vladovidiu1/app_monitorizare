from __future__ import annotations

from datetime import datetime, timedelta, timezone
import threading
from uuid import uuid4

import pytest
from pydantic import ValidationError as PydanticError

from focusdesk.ai.assistant_protocol import AssistantReply
from focusdesk.domain.models import Kind
from focusdesk.domain.session import SessionRecord
from focusdesk.errors import ValidationError
from focusdesk.services.assistant_context import build_context, validate_source
from focusdesk.services.assistant_proposals import ProposalBatch, validate_reply
from focusdesk.services.queries import Queries
from focusdesk.services.workspace import Workspace


def reply(bundle, actions=None, text="Date din context.", sources=None, email=None):
    keys = sources if sources is not None else [next(iter(bundle.sources))]
    return AssistantReply.model_validate({"answer": [{"text": text, "sources": keys}],
                                          "actions": actions or [], "email": email})


def note_op(node, text="Notă propusă", sources=None):
    return {"kind": "add_note", "node_id": node.id, "text": text,
            "reason": "Cerut de utilizator.", "sources": sources or [f"task:{node.id}"]}


def make_batch(ws, nodes=None, actions=None):
    node = nodes[0] if nodes else ws.create_node(Kind.TASK, "Țintă")
    bundle = build_context(ws, "workspace", None, "")
    result = reply(bundle, actions if actions is not None else [note_op(node)])
    return node, ProposalBatch.prepare(ws, bundle, result, list(bundle.sources))


def test_requester_search_and_limited_context(ws):
    wanted = ws.create_node(Kind.TASK, "Verificare", requested_by={"name": "Ana Șerban", "code": "aserban"})
    for i in range(24):
        ws.create_node(Kind.TASK, f"Alt task {i}", requested_by={"name": "Mihai", "code": "mihai"})
    assert [n.id for n in Queries(ws).assistant_candidates("Ce taskuri am de la colegul Ana Serban?", None)] == [wanted.id]
    bundle = build_context(ws, "workspace", None, "Ce taskuri am de la colegul Ana Serban?")
    assert bundle.matched == 1
    assert {source.node_id for source in bundle.sources.values()} == {wanted.id}
    assert "Alt task" not in bundle.wire()
    assert build_context(ws, "workspace", None, "Ce taskuri am de la colegul Inexistent?").matched == 0
    general = build_context(ws, "workspace", None, "Rezumă")
    assert general.truncated and len(general.guards) <= 12
    assert len(general.wire().encode()) <= 24000


def test_retrieves_description_checklist_dependencies_notes_and_real_session_time(ws):
    dep = ws.create_node(Kind.TASK, "Blocaj")
    task = ws.create_node(Kind.TASK, "Analiză", description="Detalii relevante", next_action="Verifică fișierul",
                          checklist=[{"text": "Primul pas", "done": True}], depends_on_ids=[dep.id])
    note = ws.add_note(task.id, "Ultima notiță")
    start = datetime.now(timezone.utc) - timedelta(hours=2)
    session = SessionRecord(node_id=task.id, start_at=start, end_at=start + timedelta(hours=1), status="done",
                            actual_seconds=600, summary="Rezultatul sesiunii")
    ws.repo.sessions.save(session)
    bundle = build_context(ws, "task", task.id, "Unde am rămas?")
    assert f"note:{note.id}" in bundle.sources and f"session:{session.id}" in bundle.sources
    facts = bundle.sources[f"task:{task.id}"].data
    assert facts["actual_seconds"] == 600  # not the planned 3600 seconds
    assert facts["description"] == "Detalii relevante" and facts["checklist"][0]["done"]
    assert f"task:{dep.id}" in bundle.sources


def test_forged_source_or_record_ownership_is_rejected(ws):
    task, batch = make_batch(ws)
    result = reply(batch.bundle, sources=[f"task:{uuid4()}"])
    with pytest.raises(ValidationError, match="surs"):
        validate_reply(ws, batch.bundle, result, batch.included)
    note = ws.add_note(task.id, "Notă")
    bundle = build_context(ws, "task", task.id, "")
    source = bundle.sources[f"note:{note.id}"]
    ws.repo.notes_store(task.id).get(note.id)  # actual source exists
    changed = ws.repo.notes_store(task.id).get(note.id)
    changed.node_id = str(uuid4())
    ws.repo.notes_store(task.id).save(changed)
    with pytest.raises(ValidationError, match="aparține"):
        validate_source(ws, source, bundle.guards)


@pytest.mark.parametrize("text", ["Am lucrat 999999 minute.", "Am citit codul și l-am testat."])
def test_unsupported_numbers_and_code_claims_are_rejected(ws, text):
    task, batch = make_batch(ws)
    with pytest.raises(ValidationError):
        validate_reply(ws, batch.bundle, reply(batch.bundle, text=text), batch.included)


@pytest.mark.parametrize("action", [
    {"kind": "shell", "command": "whoami"}, {"kind": "delete_task"}, {"kind": "restore_checkpoint"},
    {"kind": "update_task", "node_id": str(uuid4()), "patch": {"parent_id": str(uuid4())}},
])
def test_forbidden_actions_and_fields_fail_schema(action):
    with pytest.raises(PydanticError):
        AssistantReply.model_validate({"answer": [{"text": "X", "sources": []}], "actions": [action]})


def test_no_writes_before_accept_and_receipts_prevent_replay_after_reopen(ws):
    task, batch = make_batch(ws)
    batch.preview(ws)
    assert ws.list_notes(task.id) == [] and ws.ai_receipt(batch.items[0].id) is None
    assert batch.apply(ws)[0]["state"] == "applied"
    assert len(ws.list_notes(task.id)) == 1
    root = ws.root
    ws.close()
    reopened = Workspace.open(root)
    try:
        assert batch.apply(reopened)[0]["state"] == "already_recorded"
        assert len(reopened.list_notes(task.id)) == 1
        assert reopened.ai_receipt(batch.items[0].id).data["state"] == "applied"
    finally:
        reopened.close()


def test_stale_revision_or_description_never_overwrites(ws):
    task, batch = make_batch(ws)
    ws.update_node(task.id, next_action="Pas nou salvat ulterior")
    result = batch.apply(ws)
    assert result[0]["state"] == "conflict" and ws.list_notes(task.id) == []
    assert ws.get(task.id).next_action == "Pas nou salvat ulterior"
    task, batch = make_batch(ws, [task])
    (ws.node_dir(task.id) / "description.md").write_text("Schimbat extern", encoding="utf-8")
    assert batch.apply(ws)[0]["state"] == "conflict"


def test_multi_operation_updates_same_node_without_false_staleness(ws):
    task = ws.create_node(Kind.TASK, "Inițial", checklist=[{"text": "Există", "done": True}])
    actions = [{"kind": "update_task", "node_id": task.id, "patch": {"title": "Nou", "checklist": [{"text": "Adăugat", "done": False}]},
                "reason": "Cerut", "sources": [f"task:{task.id}"]}, note_op(task)]
    _, batch = make_batch(ws, [task], actions)
    assert [r["state"] for r in batch.apply(ws)] == ["applied", "applied"]
    assert ws.get(task.id).title == "Nou"
    assert [v.text for v in ws.get(task.id).checklist] == ["Există", "Adăugat"]
    assert ws.get(task.id).checklist[0].done


def test_cycles_across_proposals_and_unknown_targets_rejected_before_write(ws):
    a, b = ws.create_node(Kind.TASK, "A"), ws.create_node(Kind.TASK, "B")
    keys = [f"task:{a.id}", f"task:{b.id}"]
    actions = [{"kind": "link_tasks", "node_id": a.id, "other_id": b.id, "relation": "depends_on", "reason": "Test", "sources": keys},
               {"kind": "link_tasks", "node_id": b.id, "other_id": a.id, "relation": "depends_on", "reason": "Test", "sources": keys}]
    with pytest.raises(ValidationError, match="ciclu"):
        make_batch(ws, [a], actions)
    assert ws.get(a.id).depends_on_ids == []
    action = note_op(a)
    action["node_id"] = str(uuid4())
    with pytest.raises(ValidationError):
        make_batch(ws, [a], [action])


def test_reject_and_edit_are_shared_and_audited(ws):
    task, batch = make_batch(ws)
    payload = batch.items[0].operation.model_dump()
    payload["text"] = "Modificat de utilizator"
    batch.edit(ws, 0, payload)
    assert batch.preview(ws)[0]["after"]["note"] == "Modificat de utilizator"
    batch.reject(ws, 0)
    assert batch.apply(ws)[0]["state"] == "already_recorded"
    assert ws.list_notes(task.id) == []
    assert ws.ai_receipt(batch.items[0].id).data["state"] == "rejected"
    with pytest.raises(ValidationError):
        batch.edit(ws, 0, payload)


def test_exception_after_write_is_uncertain_and_never_replayed(ws, monkeypatch):
    task = ws.create_node(Kind.TASK, "T")
    _, batch = make_batch(ws, [task], [note_op(task, "Prima"), note_op(task, "A doua")])
    original = ws.add_note
    def failing(*args, **kwargs):
        original(*args, **kwargs)
        raise OSError("Disk error after write")
    monkeypatch.setattr(ws, "add_note", failing)
    results = batch.apply(ws)
    assert [r["state"] for r in results] == ["uncertain", "not_run"]
    assert len(ws.list_notes(task.id)) == 1
    assert batch.apply(ws, [0])[0]["state"] == "already_recorded"
    assert len(ws.list_notes(task.id)) == 1


def test_lost_final_receipt_still_prevents_duplicate_effect(ws, monkeypatch):
    task, batch = make_batch(ws)
    monkeypatch.setattr(ws, "finish_ai_action", lambda *a: (_ for _ in ()).throw(OSError("cannot finalize")))
    assert batch.apply(ws)[0]["state"] == "uncertain"
    assert ws.ai_receipt(batch.items[0].id).data["state"] == "started"
    assert batch.apply(ws)[0]["state"] == "already_recorded"
    assert len(ws.list_notes(task.id)) == 1


def test_partial_success_is_reported_without_claiming_rollback(ws, monkeypatch):
    a, b = ws.create_node(Kind.TASK, "A"), ws.create_node(Kind.TASK, "B")
    _, batch = make_batch(ws, [a], [note_op(a), note_op(b)])
    original = ws.add_note
    def change_next(*args, **kw):
        result = original(*args, **kw)
        ws.update_node(b.id, title="Modificat între operații")
        return result
    monkeypatch.setattr(ws, "add_note", change_next)
    assert [r["state"] for r in batch.apply(ws)] == ["applied", "conflict"]
    assert len(ws.list_notes(a.id)) == 1 and ws.list_notes(b.id) == []


def test_applying_in_background_or_wrong_workspace_is_refused(ws, tmp_path):
    task, batch = make_batch(ws)
    errors = []
    def run():
        try:
            batch.apply(ws)
        except Exception as exc:
            errors.append(exc)
    thread = threading.Thread(target=run)
    thread.start(); thread.join()
    assert isinstance(errors[0], ValidationError)
    other = Workspace.open(tmp_path / "other", create=True)
    try:
        assert batch.apply(other)[0]["state"] == "conflict"
        with pytest.raises(ValidationError):
            batch.reject(other, 0)
    finally:
        other.close()
