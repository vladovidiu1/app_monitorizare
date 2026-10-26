"""Interogari in memorie: cautare, vizualizari inteligente, agregare progres."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Iterable
from zoneinfo import ZoneInfo

from ..domain.common import utcnow
from ..domain.models import CLOSED_STATUSES, OPEN_STATUSES, PRIORITY_ORDER, Kind, Node, Priority, Status
from .workspace import Workspace


@dataclass
class Progress:
    leaf_total: int = 0
    done: int = 0
    open: int = 0
    estimated_minutes: int = 0
    remaining_minutes: int = 0
    unestimated: int = 0  # task-uri frunza deschise fara estimare

    @property
    def ratio(self) -> float | None:
        counted = self.done + self.open
        return None if counted == 0 else self.done / counted


class Queries:
    def __init__(self, ws: Workspace) -> None:
        self.ws = ws
        self._desc_cache: dict[str, tuple[float, str]] = {}

    # ---- helpers ----------------------------------------------------
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.ws.settings.timezone)

    def today(self) -> date:
        return datetime.now(self.tz()).date()

    def is_archived(self, node: Node) -> bool:
        if node.archived_at is not None:
            return True
        return any(a.archived_at is not None for a in self.ws.ancestors(node.id))

    def tasks(self, include_archived: bool = False) -> list[Node]:
        out = [n for n in self.ws.nodes.values() if n.kind == Kind.TASK]
        if not include_archived:
            out = [n for n in out if not self.is_archived(n)]
        return out

    def tasks_in(self, node_id: str | None, include_archived: bool = False) -> list[Node]:
        """Task-urile din subarborele nodului (toate nivelurile) plus cele referite prin legaturi."""
        if node_id is None:
            return self.tasks(include_archived)
        node = self.ws.get(node_id)
        ids = set(self.ws.subtree_ids(node_id))
        ids.update(i for i in node.related_node_ids if i in self.ws.nodes)
        for n in self.ws.referrers(node_id):
            if node_id in n.related_node_ids:
                ids.add(n.id)
        out = [self.ws.nodes[i] for i in ids if self.ws.nodes[i].kind == Kind.TASK]
        if not include_archived:
            out = [n for n in out if not self.is_archived(n)]
        return out

    def is_blocked(self, node: Node) -> bool:
        return bool(self.ws.unfinished_dependencies(node.id))

    # ---- due / remaining --------------------------------------------
    def due_day(self, node: Node) -> date | None:
        """Termenul ca data calendaristica locala; `due_date` fara ora ramane data."""
        if node.due_date is not None:
            return node.due_date
        if node.due_at is not None:
            return node.due_at.astimezone(self.tz()).date()
        return None

    def is_overdue(self, node: Node) -> bool:
        if node.status in CLOSED_STATUSES:
            return False
        if node.due_at is not None and node.due_date is None:
            return node.due_at < utcnow()
        d = self.due_day(node)
        return d is not None and d < self.today()

    # ---- progress ---------------------------------------------------
    def progress(self, node_id: str) -> Progress:
        """Agregare pe task-urile frunza din subarbore; nu aduna estimarea parintelui cu a copiilor."""
        p = Progress()
        ids = self.ws.subtree_ids(node_id, include_self=True)
        id_set = set(ids)
        has_task_child = {n.parent_id for n in self.ws.nodes.values()
                          if n.kind == Kind.TASK and n.parent_id in id_set}
        for i in ids:
            n = self.ws.nodes[i]
            if n.kind != Kind.TASK or n.id in has_task_child:
                continue
            if n.status == Status.CANCELLED:
                continue
            p.leaf_total += 1
            if n.status == Status.DONE:
                p.done += 1
                continue
            p.open += 1
            if n.estimated_minutes is None and n.remaining_minutes is None:
                p.unestimated += 1
            if n.estimated_minutes is not None:
                p.estimated_minutes += n.estimated_minutes
            rem = n.remaining_minutes if n.remaining_minutes is not None else n.estimated_minutes
            if rem is not None:
                p.remaining_minutes += rem
        return p

    def progress_map(self) -> dict[str, Progress]:
        """`progress` pentru toate nodurile intr-o singura trecere (acelasi rezultat, fara cost patratic)."""
        cmap = self.ws.children_map()
        out: dict[str, Progress] = {}

        def visit(n: Node) -> Progress:
            kids = cmap.get(n.id, [])
            total = Progress()
            for c in kids:
                s = visit(c)
                total.leaf_total += s.leaf_total
                total.done += s.done
                total.open += s.open
                total.estimated_minutes += s.estimated_minutes
                total.remaining_minutes += s.remaining_minutes
                total.unestimated += s.unestimated
            is_leaf_task = n.kind == Kind.TASK and not any(c.kind == Kind.TASK for c in kids)
            if is_leaf_task and n.status != Status.CANCELLED:
                total.leaf_total += 1
                if n.status == Status.DONE:
                    total.done += 1
                else:
                    total.open += 1
                    if n.estimated_minutes is None and n.remaining_minutes is None:
                        total.unestimated += 1
                    if n.estimated_minutes is not None:
                        total.estimated_minutes += n.estimated_minutes
                    rem = n.remaining_minutes if n.remaining_minutes is not None else n.estimated_minutes
                    if rem is not None:
                        total.remaining_minutes += rem
            out[n.id] = total
            return total

        for root in cmap.get(None, []):
            visit(root)
        return out

    # ---- worked time --------------------------------------------------
    def worked_map(self, live: tuple[str, float] | None = None, *, sessions=None) -> dict[str, int]:
        """Secunde lucrate pe nod, inclusiv sesiunile subtask-urilor; `live` = sesiunea activa (nod, secunde)."""
        own: dict[str, float] = {}
        for s in sessions if sessions is not None else self.ws.repo.sessions.list_all():
            if s.actual_seconds > 0:
                own[s.node_id] = own.get(s.node_id, 0) + s.actual_seconds
        if live is not None and live[1] > 0:
            own[live[0]] = own.get(live[0], 0) + live[1]
        total: dict[str, int] = {}
        for node_id, secs in own.items():
            cur = node_id if node_id in self.ws.nodes else None
            while cur is not None:
                total[cur] = total.get(cur, 0) + int(secs)
                cur = self.ws.nodes[cur].parent_id
                if cur not in self.ws.nodes:
                    cur = None
        return total

    def worked_by_day(self, first: date, last: date,
                      live: tuple[str, float] | None = None) -> dict[date, dict[str, int]]:
        """Secunde lucrate pe zi si pe task (doar sesiunile proprii ale task-ului), pentru zilele [first, last]."""
        tz = self.tz()
        out: dict[date, dict[str, int]] = {}

        def add(node_id: str, when: datetime, secs: float) -> None:
            if secs <= 0 or node_id not in self.ws.nodes:
                return
            day = when.astimezone(tz).date()
            if first <= day <= last:
                bucket = out.setdefault(day, {})
                bucket[node_id] = bucket.get(node_id, 0) + int(secs)

        for s in self.ws.repo.sessions.list_all():
            if s.actual_seconds > 0:
                add(s.node_id, s.started_actual_at or s.start_at, s.actual_seconds)
        if live is not None:
            add(live[0], utcnow(), live[1])
        return out

    # ---- smart views ------------------------------------------------
    def view_inbox(self) -> list[Node]:
        return self._sorted(n for n in self.tasks() if n.status == Status.INBOX)

    def view_waiting(self) -> list[Node]:
        return self._sorted(n for n in self.tasks() if n.status == Status.WAITING)

    def view_overdue(self) -> list[Node]:
        return self._sorted(n for n in self.tasks() if n.status in OPEN_STATUSES and self.is_overdue(n))

    def view_today(self) -> list[Node]:
        day = self.today()
        session_nodes = {s.node_id for s in self.sessions_on(day)}
        out = []
        for n in self.tasks():
            if n.status not in OPEN_STATUSES:
                continue
            if n.pinned_today == day or n.id in session_nodes or self.due_day(n) == day:
                out.append(n)
        return self._sorted(out)

    def view_archive(self) -> list[Node]:
        return self._sorted(n for n in self.tasks(include_archived=True) if self.is_archived(n))

    def sessions_on(self, day: date) -> list:
        tz = self.tz()
        start = datetime(day.year, day.month, day.day, tzinfo=tz)
        end = start + timedelta(days=1)
        return sorted(
            (s for s in self.ws.repo.sessions.list_all()
             if s.status in ("planned", "active") and start <= s.start_at.astimezone(tz) < end),
            key=lambda s: s.start_at,
        )

    def pinned_today(self) -> list[Node]:
        day = self.today()
        return self._sorted(n for n in self.ws.nodes.values()
                            if n.pinned_today == day and n.status in OPEN_STATUSES and not self.is_archived(n))

    def _sorted(self, nodes: Iterable[Node]) -> list[Node]:
        far = date.max
        return sorted(
            nodes,
            key=lambda n: (PRIORITY_ORDER.get(n.priority or Priority.NORMAL, 2), self.due_day(n) or far, n.title.lower()),
        )

    # ---- search / filters -------------------------------------------
    def description_text(self, node_id: str) -> str:
        path = self.ws.node_dir(node_id) / "description.md"
        try:
            mtime = os.stat(path).st_mtime
        except OSError:
            return ""
        cached = self._desc_cache.get(node_id)
        if cached and cached[0] == mtime:
            return cached[1]
        try:
            text = path.read_text(encoding="utf-8-sig")
        except OSError:
            text = ""
        self._desc_cache[node_id] = (mtime, text)
        return text

    def search(self, query: str, *, include_archived: bool = False,
               kinds: set[Kind] | None = None) -> list[Node]:
        q = query.strip().lower()
        if not q:
            return []
        terms = q.split()
        out: list[Node] = []
        for n in self.ws.nodes.values():
            if kinds and n.kind not in kinds:
                continue
            if not include_archived and self.is_archived(n):
                continue
            hay = " ".join([n.title, n.next_action or "", " ".join(n.tags), n.waiting_reason or ""]).lower()
            if all(t in hay for t in terms):
                out.append(n)
                continue
            desc = self.description_text(n.id).lower()
            if desc and all(t in hay + " " + desc for t in terms):
                out.append(n)
        return self._sorted(out)

    def filter(self, nodes: Iterable[Node], *, status: Status | None = None, priority: Priority | None = None,
               due: str | None = None, project_id: str | None = None, text: str = "") -> list[Node]:
        """`due`: 'overdue' | 'today' | 'week' | 'none' | None."""
        out = []
        today = self.today()
        text_l = text.strip().lower()
        for n in nodes:
            if status is not None and n.status != status:
                continue
            if priority is not None and n.priority != priority:
                continue
            if project_id is not None:
                proj = self.ws.nearest_project(n.id)
                if proj is None or proj.id != project_id:
                    continue
            if due:
                d = self.due_day(n)
                if due == "overdue" and not self.is_overdue(n):
                    continue
                if due == "today" and d != today:
                    continue
                if due == "week" and (d is None or not (today <= d <= today + timedelta(days=7))):
                    continue
                if due == "none" and d is not None:
                    continue
            if text_l:
                hay = " ".join([n.title, n.next_action or "", " ".join(n.tags)]).lower()
                if not all(t in hay for t in text_l.split()):
                    continue
            out.append(n)
        return out

    def duplicates_candidates(self) -> list[tuple[Node, Node, float]]:
        """Perechi de task-uri cu titluri similare (euristica deterministica, fara merge)."""
        from difflib import SequenceMatcher

        tasks = [n for n in self.tasks() if n.status in OPEN_STATUSES]
        out = []
        for i, a in enumerate(tasks):
            for b in tasks[i + 1:]:
                r = SequenceMatcher(None, a.title.lower(), b.title.lower()).ratio()
                if r >= 0.85:
                    out.append((a, b, r))
        return out
