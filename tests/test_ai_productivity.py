from datetime import date, datetime, timedelta, timezone
import pytest

from focusdesk.ai.assistant_protocol import AssistantReply
from focusdesk.domain.models import Kind, Status
from focusdesk.domain.session import SessionRecord
from focusdesk.errors import ValidationError
from focusdesk.integrations.calendar import AvailabilityResult, BusyInterval
from focusdesk.services.ai_productivity import (activity_report, report_context, report_text, mail_instruction,
    MAIL_MODES, day_context, day_selection, validate_mail_reply)
from focusdesk.services.assistant_context import build_context, validate_source
from focusdesk.services.planning import PlanningService
from focusdesk.services.planner import PlanRequest
from focusdesk.services.sessions import SessionService

UTC = timezone.utc
DAY = date(2026, 10, 26)
START = datetime(2026, 10, 26, 7, tzinfo=UTC)


def session(ws, node, seconds, when=START, **extra):
    value = SessionRecord(node_id=node.id, start_at=when, end_at=when + timedelta(hours=2), actual_seconds=seconds, **extra)
    ws.repo.sessions.save(value)
    return value


def test_empty_report_has_zero_work_and_no_claimed_completion(ws):
    data = activity_report(ws, DAY, DAY)
    assert data['actual_seconds'] == data['worked_tasks'] == data['completed_tasks'] == 0
    assert data['tasks'] == []
    bundle, _ = report_context(ws, DAY, DAY)
    assert len(bundle.sources) == 1
    assert 'Nu există' in report_text(data)


def test_actual_seconds_not_planned_minutes_no_parent_double_count(ws):
    parent = ws.create_node(Kind.TASK, 'Părinte')
    child = ws.create_node(Kind.TASK, 'Copil', parent_id=parent.id)
    session(ws, parent, 61)
    child_session = session(ws, child, 125, started_actual_at=START)
    session(ws, child, 0, when=START + timedelta(hours=4))  # planned 2h contributes zero
    session(ws, child, 999, when=START - timedelta(days=8))
    data = activity_report(ws, DAY, DAY)
    assert data['actual_seconds'] == 186
    assert data['worked_tasks'] == 2
    assert sum(row['actual_seconds'] for row in data['tasks']) == 186
    assert child_session.id in report_text(data)
    assert data['completed_tasks'] == 0


def test_report_uses_workspace_day_of_actual_start_and_completed_at(ws):
    task = ws.create_node(Kind.TASK, 'Raport')
    session(ws, task, 80, when=START, started_actual_at=datetime(2026, 10, 25, 23, 30, tzinfo=UTC))
    ws.update_node(task.id, status=Status.DONE)
    task = ws.get(task.id)
    done_day = task.completed_at.astimezone(__import__('zoneinfo').ZoneInfo(ws.settings.timezone)).date()
    assert activity_report(ws, DAY, DAY)['actual_seconds'] == 80
    assert activity_report(ws, done_day, done_day)['completed_tasks'] == 1
    assert activity_report(ws, done_day-timedelta(days=8), done_day-timedelta(days=8))['completed_tasks'] == 0


def test_report_source_detects_changed_session_and_restored_status(ws):
    task = ws.create_node(Kind.TASK, 'Raport')
    value = session(ws, task, 70)
    bundle, _ = report_context(ws, DAY, DAY)
    source = next(iter(bundle.sources.values()))
    validate_source(ws, source, {})
    value.actual_seconds = 80
    ws.repo.sessions.save(value)
    with pytest.raises(ValidationError, match='raportului'):
        validate_source(ws, source, {})


def test_day_rejects_four_priorities_and_invented_source(ws):
    tasks = [ws.create_node(Kind.TASK, f'Activitate {i}') for i in range(4)]
    bundle = day_context(ws, '')
    reply = AssistantReply(answer=[{'text': 'Prioritate', 'sources': ['task:'+n.id]} for n in tasks])
    with pytest.raises(ValidationError, match='trei'):
        day_selection(ws, bundle, reply, list(bundle.sources))
    reply.answer = reply.answer[:3]
    assert day_selection(ws, bundle, reply, list(bundle.sources)) == [n.id for n in tasks[:3]]
    assert ws.repo.sessions.list_all() == []


def test_planner_handles_unknown_estimates_and_blocked_dependencies(ws):
    dependency = ws.create_node(Kind.TASK, 'Dependență')
    blocked = ws.create_node(Kind.TASK, 'Blocat', estimated_minutes=30, depends_on_ids=[dependency.id])
    unknown = ws.create_node(Kind.TASK, 'Neestimat')
    planning = PlanningService(ws, SessionService(ws))
    result = planning.plan([PlanRequest(blocked.id), PlanRequest(unknown.id)], DAY, DAY, now=START)
    assert result.sessions == []
    reasons = {row.node_id:row.reason for row in result.unallocated}
    assert 'neestimat' in reasons[unknown.id]
    assert 'dependențe' in reasons[blocked.id]
    assert ws.repo.sessions.list_all() == []


def test_planner_preview_respects_busy_local_breaks_and_has_no_overlaps(ws):
    a = ws.create_node(Kind.TASK, 'Unu', estimated_minutes=80)
    b = ws.create_node(Kind.TASK, 'Doi', estimated_minutes=80)
    session(ws, a, 0, when=START + timedelta(hours=1))
    busy = BusyInterval(start=START, end=START + timedelta(minutes=30), source='outlook')
    planning = PlanningService(ws, SessionService(ws))
    result = planning.plan([PlanRequest(a.id),PlanRequest(b.id)], DAY, DAY, AvailabilityResult(busy=[busy]), now=START)
    assert result.sessions
    for first, second in zip(result.sessions, result.sessions[1:]):
        assert first.end <= second.start
    for row in result.sessions:
        assert not (row.start < busy.end and row.end > busy.start)
        assert not (row.start < START+timedelta(hours=3) and row.end > START+timedelta(hours=1))
    assert len(ws.repo.sessions.list_all()) == 1  # preview only


def test_mail_modes_and_false_completion_are_rejected_without_sending(ws):
    task = ws.create_node(Kind.TASK, 'Raport')
    with pytest.raises(ValidationError, match='nu este finalizat'):
        mail_instruction(ws, task.id, MAIL_MODES[3])
    assert 'mesaj NOU' in mail_instruction(ws, task.id, MAIL_MODES[0])
    bundle = build_context(ws, 'task', task.id, '')
    key = 'task:'+task.id
    reply = AssistantReply(answer=[{'text':'Ciornă', 'sources':[key]}], email={
        'node_id':task.id,'subject':'Raport','body':'Taskul este finalizat.', 'reason':'Actualizare','sources':[key]})
    with pytest.raises(ValidationError, match='finalizare'):
        validate_mail_reply(ws,bundle,reply,list(bundle.sources),task.id)
    reply.email.body = 'Te rog să clarifici cerințele.'
    assert validate_mail_reply(ws,bundle,reply,list(bundle.sources),task.id).items == []
    assert ws.list_notes(task.id) == []


def test_day_priorities_expire_when_local_day_changes(ws, monkeypatch):
    from focusdesk.services.queries import Queries
    task = ws.create_node(Kind.TASK, 'Prioritate')
    bundle = day_context(ws, '')
    source = bundle.sources['task:' + task.id]
    tomorrow = date.fromisoformat(source.data['today']) + timedelta(days=1)
    monkeypatch.setattr(Queries, 'today', lambda self: tomorrow)
    with pytest.raises(ValidationError, match='Ziua'):
        validate_source(ws, source, bundle.guards)
