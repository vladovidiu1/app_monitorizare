"""Workspace demonstrativ, creat doar la cerere (nu la prima pornire)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from ..domain.common import utcnow
from ..domain.models import Kind, Priority, Status
from .queries import Queries
from .workspace import Workspace


def create_demo_workspace(root: Path) -> None:
    ws = Workspace.open(root, create=True, name="FocusDesk — demo")
    try:
        ws.repo.meta = ws.repo.meta.model_copy(update={"demo": True})  # type: ignore[union-attr]
        from ..storage.atomic import atomic_write_json

        atomic_write_json(ws.root / "workspace.json", ws.repo.meta.model_dump(mode="json"))  # type: ignore[union-attr]
        today = Queries(ws).today()
        daily = ws.create_node(Kind.FOLDER, "Solicitări zilnice")
        sap = ws.create_node(Kind.FOLDER, "SAP")
        auto = ws.create_node(Kind.FOLDER, "Automatizări")
        proj = ws.create_node(Kind.PROJECT, "Validări XML", sap.id,
                              description="Validarea diferențelor între XML-urile primite pentru POD-uri.")
        t1 = ws.create_node(Kind.TASK, "Verificare diferențe XML", proj.id, estimated_minutes=120,
                            remaining_minutes=120, priority=Priority.HIGH, tags=["SAP", "XML"],
                            next_action="Verifică un POD cu trei XML-uri", due_date=today + timedelta(days=2))
        ws.create_node(Kind.TASK, "Extragere date din SAP", t1.id, estimated_minutes=45, remaining_minutes=45)
        ws.create_node(Kind.TASK, "Comparare câmpuri", t1.id)
        ws.create_node(Kind.TASK, "Raport pentru utilizator", proj.id, estimated_minutes=60, remaining_minutes=60)
        doc = ws.create_node(Kind.TASK, "Documentare proces", proj.id)
        flow = ws.create_node(Kind.TASK, "Descrierea fluxului", doc.id)
        diagram = ws.create_node(Kind.TASK, "Diagramă de flux", flow.id)
        ws.create_node(Kind.TASK, "Revizuire cu echipa", diagram.id, estimated_minutes=30, remaining_minutes=30)
        r1 = ws.create_node(Kind.TASK, "Solicitare: corectare date contract", daily.id, priority=Priority.URGENT,
                            due_date=today, next_action="Cere detalii de la solicitant")
        ws.add_related(proj.id, r1.id)
        ws.create_node(Kind.TASK, "Solicitare: raport lunar", daily.id, status=Status.WAITING,
                       waiting_reason="Aștept datele de la contabilitate")
        ws.create_node(Kind.TASK, "Idei de automatizare", auto.id, status=Status.INBOX)
        ws.update_node(t1.id, pinned_today=today)
        ws.add_note(t1.id, "Am identificat 3 câmpuri care diferă constant între versiuni.", "progress")
    finally:
        ws.close()
