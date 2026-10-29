"""Workspace demonstrativ, creat doar la cerere (nu la prima pornire)."""

from __future__ import annotations

from ..i18n import tr

from datetime import timedelta
from pathlib import Path

from ..domain.common import utcnow
from ..domain.models import Kind, Priority, Status
from .queries import Queries
from .workspace import Workspace


def create_demo_workspace(root: Path) -> None:
    ws = Workspace.open(root, create=True, name=tr('demo.workspace_name'))
    try:
        ws.repo.meta = ws.repo.meta.model_copy(update={"demo": True})  # type: ignore[union-attr]
        from ..storage.atomic import atomic_write_json

        atomic_write_json(ws.root / "workspace.json", ws.repo.meta.model_dump(mode="json"))  # type: ignore[union-attr]
        today = Queries(ws).today()
        daily = ws.create_node(Kind.FOLDER, tr('demo.daily_requests'))
        sap = ws.create_node(Kind.FOLDER, "SAP")
        auto = ws.create_node(Kind.FOLDER, tr('demo.automations'))
        proj = ws.create_node(Kind.PROJECT, tr('demo.xml_project'), sap.id,
                              description=tr('demo.xml_description'))
        t1 = ws.create_node(Kind.TASK, tr('demo.compare_xml'), proj.id, estimated_minutes=120,
                            remaining_minutes=120, priority=Priority.HIGH, tags=["SAP", "XML"],
                            next_action=tr('demo.next_xml'), due_date=today + timedelta(days=2))
        ws.create_node(Kind.TASK, tr('demo.extract_sap'), t1.id, estimated_minutes=45, remaining_minutes=45)
        ws.create_node(Kind.TASK, tr('demo.compare_fields'), t1.id)
        ws.create_node(Kind.TASK, tr('demo.user_report'), proj.id, estimated_minutes=60, remaining_minutes=60)
        doc = ws.create_node(Kind.TASK, tr('demo.document_process'), proj.id)
        flow = ws.create_node(Kind.TASK, tr('demo.flow_description'), doc.id)
        diagram = ws.create_node(Kind.TASK, tr('demo.flow_diagram'), flow.id)
        ws.create_node(Kind.TASK, tr('demo.team_review'), diagram.id, estimated_minutes=30, remaining_minutes=30)
        r1 = ws.create_node(Kind.TASK, tr('demo.contract_request'), daily.id, priority=Priority.URGENT,
                            due_date=today, next_action=tr('demo.ask_requester'))
        ws.add_related(proj.id, r1.id)
        ws.create_node(Kind.TASK, tr('demo.monthly_request'), daily.id, status=Status.WAITING,
                       waiting_reason=tr('demo.waiting_accounting'))
        ws.create_node(Kind.TASK, tr('demo.automation_ideas'), auto.id, status=Status.TODO)
        ws.update_node(t1.id, pinned_today=today)
        ws.add_note(t1.id, tr('demo.progress_note'), "progress")
    finally:
        ws.close()
