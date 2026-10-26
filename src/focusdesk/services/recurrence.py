"""Task-uri recurente: sabloane simple, instante independente, fara duplicate."""

from __future__ import annotations

from datetime import date, timedelta

from ..domain.models import Kind, Node
from ..domain.session import RecurrenceTemplate
from ..errors import FocusDeskError, NotFoundError, ValidationError
from .queries import Queries
from .workspace import Workspace

MAX_LOOKBACK_DAYS = 60


class RecurrenceService:
    def __init__(self, ws: Workspace) -> None:
        self.ws = ws
        self.q = Queries(ws)

    def templates(self) -> list[RecurrenceTemplate]:
        return sorted(self.ws.repo.recurrences.list_all(), key=lambda t: t.title.lower())

    def create(self, **fields) -> RecurrenceTemplate:
        self.ws.repo._require_writable()
        try:
            t = RecurrenceTemplate(**fields)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        if t.parent_id is not None:
            self.ws.check_parent(Kind.TASK, t.parent_id)
        self.ws.repo.recurrences.save(t)
        return t

    def set_active(self, template_id: str, active: bool) -> None:
        t = self.ws.repo.recurrences.get(template_id)
        t.active = active
        self.ws.repo.recurrences.save(t)

    def delete(self, template_id: str) -> None:
        """Sterge doar sablonul; task-urile deja generate raman."""
        self.ws.repo.recurrences.delete(template_id)

    def pending(self, t: RecurrenceTemplate, today: date) -> tuple[bool, list[date]]:
        """(azi_nu_e_generat, zile_ratate_in_ultimele_60_zile). Nu genereaza nimic."""
        done = set(t.generated_dates) | set(t.skipped_dates)
        existing = {(n.recurrence_template_id, n.occurrence_date) for n in self.ws.nodes.values()
                    if n.recurrence_template_id}
        floor = max(t.start_date, today - timedelta(days=MAX_LOOKBACK_DAYS))
        missed: list[date] = []
        d = floor
        while d < today:
            if t.occurs_on(d) and d not in done and (t.id, d) not in existing:
                missed.append(d)
            d += timedelta(days=1)
        today_pending = t.occurs_on(today) and today not in done and (t.id, today) not in existing
        return today_pending, missed

    def generate(self, template_id: str, day: date) -> Node | None:
        """Genereaza instanta pentru `day`; cheia (template_id, occurrence_date) este unica."""
        self.ws.repo._require_writable()
        t = self.ws.repo.recurrences.get(template_id)
        if not t.active:
            raise ValidationError("Șablonul este dezactivat.")
        if not t.occurs_on(day):
            raise ValidationError("Șablonul nu se aplică în această zi.")
        for n in self.ws.nodes.values():
            if n.recurrence_template_id == t.id and n.occurrence_date == day:
                self._record(t, day)
                return None
        if day in t.generated_dates:
            return None
        parent = t.parent_id if t.parent_id in self.ws.nodes else None
        node = self.ws.create_node(
            Kind.TASK, f"{t.title} — {day:%d.%m.%Y}", parent, priority=t.priority, due_date=day,
            estimated_minutes=t.estimated_minutes, remaining_minutes=t.estimated_minutes,
            next_action=t.next_action, tags=t.tags, recurrence_template_id=t.id, occurrence_date=day,
        )
        self._record(t, day)
        return node

    def skip(self, template_id: str, days: list[date]) -> None:
        t = self.ws.repo.recurrences.get(template_id)
        t.skipped_dates = sorted(set(t.skipped_dates) | set(days))
        self.ws.repo.recurrences.save(t)

    def _record(self, t: RecurrenceTemplate, day: date) -> None:
        if day not in t.generated_dates:
            t.generated_dates = sorted({*t.generated_dates, day})
            self.ws.repo.recurrences.save(t)

    def generate_today_all(self, today: date | None = None) -> tuple[list[Node], dict[str, list[date]]]:
        """La pornire: genereaza instantele de azi; intoarce si zilele ratate (de ales de utilizator)."""
        today = today or self.q.today()
        created: list[Node] = []
        missed: dict[str, list[date]] = {}
        for t in self.templates():
            if not t.active:
                continue
            try:
                today_pending, old = self.pending(t, today)
                if old:
                    missed[t.id] = old
                if today_pending:
                    n = self.generate(t.id, today)
                    if n:
                        created.append(n)
            except FocusDeskError:
                continue
        return created, missed
