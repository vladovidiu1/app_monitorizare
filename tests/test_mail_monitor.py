from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import json

import pytest

from focusdesk.ai.mail_protocol import MailAnalysis
from focusdesk.domain.mail_monitor import FolderChoice, MailHeader, MailRecord
from focusdesk.domain.models import Kind
from focusdesk.domain.settings import MailMonitorSettings
from focusdesk.integrations.mail_fake import FakeMailBackend
from focusdesk.services.mail_analysis import build_mail_context, project_analysis, restore_batch, save_batch, resolve_deadline, reconcile
from focusdesk.services.mail_monitor import MailMonitorService, content_hash
from focusdesk.services.workspace import Workspace

UTC = timezone.utc
NOW = datetime(2026, 10, 26, 12, tzinfo=UTC)


def message(index=1, body="Te rog verifică raportul până mâine.", *, folder="inbox", conversation="thread", smtp="ana@example.org"):
    when = NOW - timedelta(minutes=10-index)
    return {"header": {"store_id": "store", "folder_id": folder, "entry_id": f"entry-{index}",
        "internet_id": f"<message-{index}@example.org>", "search_key": f"key-{index}", "conversation_id": conversation,
        "subject": "Raport", "sender_name": "Ana Exemplu", "sender_smtp": smtp,
        "sent_at": when.isoformat(), "received_at": when.isoformat(), "modified_at": when.isoformat()},
        "body": body, "attachments": [{"filename": "script.exe", "size": 123, "type": 1}], "unread": True}


def configure(ws, **values):
    config = {"enabled": True, "store_id": "store", "mailbox": "Test",
              "folders": [FolderChoice(store_id="store", folder_id="inbox", mailbox="Test", path="Inbox")], **values}
    new = ws.settings.model_copy(deep=True)
    new.mail_monitor = MailMonitorSettings(**config)
    ws.update_settings(new)


def scan(ws, backend, now=NOW):
    service = MailMonitorService(ws)
    plan = service.plan(now)
    page = backend.scan_mail_page(plan)
    locators = service.details_needed(plan, page)
    details = backend.read_mail_details(locators) if locators else []
    service.commit(plan, page, details)
    return page


def imported(ws, data=None):
    data = data or message()
    header = MailHeader.model_validate(data["header"])
    record = MailRecord(id=header.identity, header=header, body=data["body"], body_loaded=True,
                        attachments=data.get("attachments", []))
    record.content_hash = content_hash(record)
    ws.save_mail_record(record)
    return record


def analysis(**values):
    return MailAnalysis(classification="request", summary="Solicitare de verificare raport.",
        evidence_quote="Te rog verifică raportul", task_title="Verifică raportul", description="Verificare solicitată de expeditor.",
        requester_is_sender=True, deadline_quote="până mâine", **values)


def test_opt_in_initial_window_cap_restart_and_no_unread_mutation(ws):
    assert MailMonitorService(ws).plan(NOW) is None
    configure(ws, first_max=2, page_size=1)
    backend = FakeMailBackend([message(1), message(2), message(3), message(4, body="Prea vechi")])
    backend.messages[-1]["header"]["received_at"] = (NOW - timedelta(days=30)).isoformat()
    original = copy.deepcopy(backend.messages)
    scan(ws, backend)
    root = ws.root
    ws.close()
    reopened = Workspace.open(root)
    try:
        scan(reopened, backend)
        assert len(reopened.mail_records()) == 2
        cursor = next(iter(reopened.mail_state().cursors.values()))
        assert cursor.initial_done and cursor.limit_reached
        scan(reopened, backend, NOW + timedelta(minutes=1))
        assert len(reopened.mail_records()) == 2  # overlap does not bypass initial cap
        assert backend.messages == original
    finally:
        reopened.close()


def test_duplicate_and_move_same_store_do_not_reset_rejection(ws):
    folders = [FolderChoice(store_id="store", folder_id=value) for value in ("inbox", "archive")]
    configure(ws, folders=folders)
    data = message()
    backend = FakeMailBackend([data])
    scan(ws, backend)
    record = ws.mail_records()[0]
    record.state = "rejected"
    ws.save_mail_record(record)
    backend.messages[0]["header"]["folder_id"] = "archive"
    backend.messages[0]["header"]["entry_id"] = "moved-entry"
    backend.messages[0]["header"]["modified_at"] = (NOW + timedelta(seconds=1)).isoformat()
    scan(ws, backend, NOW + timedelta(minutes=1))
    assert len(ws.mail_records()) == 1
    assert ws.mail_get(record.id).state == "rejected"
    assert ws.mail_get(record.id).header.entry_id == "moved-entry"
    other_store = MailHeader.model_validate({**data["header"], "store_id": "different"})
    assert other_store.identity != record.id


def test_failed_details_do_not_advance_checkpoint_and_replay_deduplicates(ws, monkeypatch):
    configure(ws)
    backend = FakeMailBackend([message()])
    service = MailMonitorService(ws)
    plan = service.plan(NOW)
    page = backend.scan_mail_page(plan)
    with pytest.raises(ValueError):
        service.commit(plan, page, [])
    assert next(iter(ws.mail_state().cursors.values())).offset == 0
    scan(ws, backend)
    assert len(ws.mail_records()) == 1
    # Simulated crash after record write, before final checkpoint save.
    state = ws.mail_state()
    cursor = next(iter(state.cursors.values()))
    cursor.initial_done, cursor.offset, cursor.initial_count = False, 0, 0
    ws.save_mail_state(state)
    scan(ws, backend)
    assert len(ws.mail_records()) == 1


def test_information_has_no_task_and_is_not_reset_by_scan(ws):
    record = imported(ws, message(body="Informare: raport disponibil."))
    bundle, payload = build_mail_context(ws, record.id)
    batch = project_analysis(ws, record.id, MailAnalysis(classification="informational", summary="Mesaj informativ.", evidence_quote="raport disponibil"), bundle)
    assert batch.items == [] and ws.nodes == {}
    assert ws.mail_get(record.id).state == "informational"
    assert "script.exe" in json.dumps(payload) and "attachments_metadata_only" in json.dumps(payload)


def test_new_request_uses_real_smtp_and_deterministic_date_then_replay_is_blocked(ws):
    record = imported(ws)
    bundle, _ = build_mail_context(ws, record.id)
    batch = project_analysis(ws, record.id, analysis(), bundle)
    assert ws.nodes == {}
    assert batch.preview(ws)[0]["after"]["due_date"] == "2026-10-27"
    assert batch.apply(ws)[0]["state"] == "applied"
    save_batch(ws, record.id, batch)
    task = next(iter(ws.nodes.values()))
    assert task.requested_by.email == "ana@example.org" and task.requested_by.code == ""
    assert task.due_date.isoformat() == "2026-10-27"
    assert ws.mail_get(record.id).confirmed_task_ids == [task.id]
    assert batch.apply(ws)[0]["state"] == "already_recorded"
    assert len(ws.nodes) == 1


def test_conversation_is_only_hint_and_update_requires_individual_accept(ws):
    task = ws.create_node(Kind.TASK, "Raport")
    prior = imported(ws, message(1))
    ws.confirm_mail_link(prior.id, task.id)
    follow = imported(ws, message(2, body="Raportul este finalizat. Am verificat toate datele."))
    bundle, payload = build_mail_context(ws, follow.id)
    assert payload["candidates"][0]["confirmed_conversation_hint"]
    assert ws.mail_get(follow.id).confirmed_task_ids == []
    value = MailAnalysis(classification="update", summary="Actualizare primită.", evidence_quote="Raportul este finalizat",
        target_task_id=task.id, status="done", status_quote="Raportul este finalizat", journal_update="Expeditorul a confirmat finalizarea.")
    batch = project_analysis(ws, follow.id, value, bundle)
    assert ws.get(task.id).status.value == "todo"
    assert all(row["state"] == "applied" for row in batch.apply(ws))
    save_batch(ws, follow.id, batch)
    assert ws.get(task.id).status.value == "done"
    assert ws.mail_get(follow.id).confirmed_task_ids == [task.id]
    assert len(ws.list_notes(task.id)) == 1


def test_ambiguous_deadline_requires_edit_and_estimate_stays_separate(ws):
    data = message(body="Te rog verifică raportul până vineri.")
    for key in ("sent_at", "received_at", "modified_at"):
        data["header"][key] = "2026-10-30T08:00:00+00:00"
    record = imported(ws, data)
    bundle, _ = build_mail_context(ws, record.id)
    value = analysis().model_copy(update={"deadline_quote": "până vineri"})
    batch = project_analysis(ws, record.id, value, bundle)
    assert batch.apply(ws)[0]["state"] == "needs_clarification"
    assert ws.nodes == {} and batch.items[0].state == "pending"
    payload = batch.items[0].operation.model_dump()
    payload["due_date"] = "2026-11-06"
    batch.edit(ws, 0, payload)
    assert batch.apply(ws)[0]["state"] == "applied"
    save_batch(ws, record.id, batch)
    stored = ws.mail_get(record.id)
    assert stored.analysis["deadline_quote"] == "până vineri"
    assert stored.edited_items == [True]
    assert next(iter(ws.nodes.values())).due_date.isoformat() == "2026-11-06"


def test_rejected_proposals_and_ignored_conversation_survive_restart(ws):
    record = imported(ws)
    bundle, _ = build_mail_context(ws, record.id)
    batch = project_analysis(ws, record.id, analysis(), bundle)
    batch.reject(ws, 0)
    save_batch(ws, record.id, batch)
    MailMonitorService(ws).ignore_conversation(record.id)
    root = ws.root
    ws.close()
    reopened = Workspace.open(root)
    try:
        assert reopened.mail_get(record.id).state == "ignored"
        assert record.header.conversation_key in reopened.mail_state().ignored_conversations
        assert reopened.ai_receipt(batch.items[0].id).data["state"] == "rejected"
    finally:
        reopened.close()


def test_partial_batch_restores_only_confirmed_guard_versions(ws):
    task = ws.create_node(Kind.TASK, "Raport")
    record = imported(ws, message(body="Raportul este finalizat."))
    bundle, _ = build_mail_context(ws, record.id)
    value = MailAnalysis(classification="update", summary="Actualizare", evidence_quote="Raportul este finalizat",
        target_task_id=task.id, status="done", status_quote="Raportul este finalizat", journal_update="Finalizare confirmată.")
    batch = project_analysis(ws, record.id, value, bundle)
    assert batch.apply(ws, [0])[0]["state"] == "applied"
    restored = restore_batch(ws, record.id)
    assert restored.items[0].state == "applied"
    assert all(row["state"] in ("already_recorded", "applied") for row in restored.apply(ws))
    reconcile(ws)
    assert ws.mail_get(record.id).state == "handled"


@pytest.mark.parametrize("quote,stamp,expected", [
    ("până mâine", "2026-10-26T23:30:00+00:00", "2026-10-28"),
    ("până vineri", "2026-10-26T10:00:00+00:00", "2026-10-30"),
    ("vineri 06.11.2026", "2026-10-30T10:00:00+00:00", "2026-11-06"),
    ("până vineri", "2026-10-30T10:00:00+00:00", None),
    ("mâine sau vineri", "2026-10-26T10:00:00+00:00", None),
])
def test_relative_dates_use_message_date_and_workspace_timezone(quote, stamp, expected):
    result, issue = resolve_deadline(quote, datetime.fromisoformat(stamp), "Europe/Bucharest")
    assert (result.isoformat() if result else None) == expected
    assert bool(issue) == (expected is None)


def test_unignore_preserves_rejection_and_global_ignore_blocks_analysis(ws):
    record = imported(ws)
    record.state = "rejected"
    ws.save_mail_record(record)
    monitor = MailMonitorService(ws)
    monitor.ignore_conversation(record.id)
    monitor.ignore_conversation(record.id)  # idempotent; never overwrite suspended decision
    with pytest.raises(Exception, match="Reia explicit"):
        build_mail_context(ws, record.id)
    monitor.ignore_conversation(record.id, False)
    assert ws.mail_get(record.id).state == "rejected"
    # Crash gap: global flag written, per-record update not yet written.
    state = ws.mail_state()
    state.ignored_conversations = [record.header.conversation_key]
    ws.save_mail_state(state)
    with pytest.raises(Exception, match="Reia explicit"):
        build_mail_context(ws, record.id)


def test_quotes_must_be_observed_and_targets_must_survive_prompt_budget(ws):
    record = imported(ws)
    bundle, _ = build_mail_context(ws, record.id)
    with pytest.raises(Exception, match="Fragmentul justificativ"):
        project_analysis(ws, record.id, analysis(), bundle, body_chars=2)
    task = ws.create_node(Kind.TASK, "Raport")
    bundle, _ = build_mail_context(ws, record.id)
    value = MailAnalysis(classification="update", summary="Actualizare", evidence_quote="Te rog verifică raportul", target_task_id=task.id)
    with pytest.raises(Exception, match="nu a fost consultat"):
        project_analysis(ws, record.id, value, bundle, candidate_ids=[])


def test_negated_status_never_becomes_confirmed_done(ws):
    task = ws.create_node(Kind.TASK, "Raport")
    record = imported(ws, message(body="Raportul nu este finalizat."))
    bundle, _ = build_mail_context(ws, record.id)
    value = MailAnalysis(classification="update", summary="Actualizare", evidence_quote="Raportul nu este finalizat",
        target_task_id=task.id, status="done", status_quote="Raportul nu este finalizat")
    batch = project_analysis(ws, record.id, value, bundle)
    assert not any(item.operation.kind == "update_task" for item in batch.items)
    assert ws.get(task.id).status.value != "done"
    assert ws.mail_get(record.id).clarification
