"""Planificare asistata: leaga planner-ul determinist de workspace si aplica propunerile aprobate."""

from __future__ import annotations

from ..i18n import tr

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from ..domain.common import utcnow
from ..domain.models import CLOSED_STATUSES, Kind
from ..domain.session import SessionRecord
from ..errors import FocusDeskError
from ..integrations.calendar import AvailabilityResult
from ..domain.timeutil import local_day_bounds_utc
from .planner import Planner, PlanRequest, PlanResult, ProposedSession
from .sessions import SessionService
from .workspace import Workspace


@dataclass
class ApplyOutcome:
    created: list[SessionRecord] = field(default_factory=list)
    failed: list[tuple[ProposedSession, str]] = field(default_factory=list)


class PlanningService:
    def __init__(self, ws: Workspace, sessions: SessionService) -> None:
        self.ws = ws
        self.sessions = sessions

    def plan(self, requests: list[PlanRequest], start_day: date, end_day: date,
             availability: AvailabilityResult | None = None, now: datetime | None = None) -> PlanResult:
        now = now or utcnow()
        availability = availability or AvailabilityResult()
        planner = Planner(self.ws.settings)
        nodes = {r.node_id: self.ws.get(r.node_id) for r in requests if r.node_id in self.ws.nodes}
        deps = {nid: [d.id for d in self.ws.unfinished_dependencies(nid)] for nid in nodes}
        # dependentele dintre noduri selectate trebuie cunoscute ca obiecte
        for lst in deps.values():
            for d in lst:
                if d in self.ws.nodes:
                    nodes.setdefault(d, self.ws.nodes[d])
        period_start = local_day_bounds_utc(start_day, self.ws.settings.timezone)[0]
        period_end = local_day_bounds_utc(end_day, self.ws.settings.timezone)[1]
        local = self.sessions.between(period_start - timedelta(hours=1), period_end + timedelta(hours=1))
        already: dict[str, int] = {}
        for s in local:
            if s.status == "planned" and s.start_at > now:
                already[s.node_id] = already.get(s.node_id, 0) + s.planned_minutes
        result = planner.plan(requests, nodes, start_day, end_day, busy=availability.busy, local_sessions=local,
                              now=now, unfinished_deps=deps, already_planned_minutes=already)
        if availability.verified_scope == "local":
            result.notes.append(availability.note)
        for w in availability.warnings:
            result.notes.append(w)
        return result

    def apply(self, proposals: list[ProposedSession], *, reserve_calendar: bool = False) -> ApplyOutcome:
        """Aplica doar propunerile selectate, trecand prin aceleasi validari ca editarea manuala."""
        out = ApplyOutcome()
        for p in sorted(proposals, key=lambda x: x.start):
            try:
                node = self.ws.get(p.node_id)
                if node.kind != Kind.TASK or node.status in CLOSED_STATUSES:
                    raise FocusDeskError(tr('services.planning.task_finalizat_intre_timp'))
                out.created.append(self.sessions.create(p.node_id, p.start, p.end, origin="assisted",
                                                        reserve_calendar=reserve_calendar))
            except FocusDeskError as exc:
                out.failed.append((p, str(exc)))
        return out
