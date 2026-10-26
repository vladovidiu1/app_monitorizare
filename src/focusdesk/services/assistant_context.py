"""Recuperare limitată și surse verificabile. Numai citiri, potrivită pentru UiBridge."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from uuid import UUID

from ..domain.models import Kind, Node
from ..domain.labels import STATUS_LABELS, PRIORITY_LABELS
from ..errors import ValidationError
from .ai_actions import ActionContext
from .queries import Queries
from .sessions import SessionService


def digest(record) -> str:
    return hashlib.sha256(record.model_dump_json().encode()).hexdigest()


@dataclass(frozen=True)
class Guard:
    revision: int
    fingerprint: str


@dataclass(frozen=True)
class Source:
    key: str
    kind: str
    node_id: str
    record_id: str
    fingerprint: str
    data: dict

    def wire(self) -> dict:
        return {"key": self.key, "kind": self.kind, "node_id": self.node_id, "record_id": self.record_id, "data": self.data}


@dataclass
class ContextBundle:
    workspace_id: str
    scope: str
    anchor: str | None
    sources: dict[str, Source] = field(default_factory=dict)
    guards: dict[str, Guard] = field(default_factory=dict)
    matched: int = 0
    truncated: bool = False

    def wire(self) -> str:
        return json.dumps({"scope": self.scope, "anchor": self.anchor, "matched_tasks": self.matched,
            "partial": self.truncated, "records": [s.wire() for s in self.sources.values()]}, ensure_ascii=False)


def node_guard(ws, node_id: str) -> Guard:
    node = ws.get(node_id)
    disk = Node.model_validate_json((ws.node_dir(node_id) / "node.json").read_bytes())
    if disk.model_dump() != node.model_dump():
        raise ValidationError("Nod modificat extern; rescanează workspace-ul înainte de a cere o propunere.")
    return Guard(node.revision, ActionContext.fingerprint(ws, node_id))


def validate_source(ws, source: Source, guards: dict[str, Guard], cache=None, progress_expected=None, blockers_expected=None) -> None:
    cache = cache if cache is not None else {}
    if source.kind == "report":
        from datetime import date
        from .ai_productivity import activity_report, report_fingerprint
        data = activity_report(ws, date.fromisoformat(source.data["first"]), date.fromisoformat(source.data["last"]))
        if report_fingerprint(data) != source.fingerprint:
            raise ValidationError("Datele raportului s-au schimbat; recalculează.")
        return
    if source.kind == "mail":
        from .mail_monitor import mail_fingerprint
        record = ws.mail_get(source.record_id)
        if (record is None or mail_fingerprint(record) != source.fingerprint or record.state in ("ignored", "rejected", "handled")
                or record.header.conversation_key in ws.mail_state().ignored_conversations):
            raise ValidationError("Mailul s-a schimbat, a fost tratat sau conversația este ignorată. Reanalizează.")
        return
    UUID(source.node_id)
    UUID(source.record_id)
    guard_key = "guard:" + source.node_id
    if guard_key not in cache:
        cache[guard_key] = node_guard(ws, source.node_id)
    if cache[guard_key] != guards.get(source.node_id):
        raise ValidationError("Sursa s-a schimbat; recalculează răspunsul.")
    if source.kind == "task":
        q = Queries(ws)
        if source.data.get("today", q.today().isoformat()) != q.today().isoformat() or source.data.get("timezone", ws.settings.timezone) != ws.settings.timezone:
            raise ValidationError("Ziua sau fusul s-a schimbat; recalculează prioritățile.")
        blockers = [item.title for item in ws.unfinished_dependencies(source.node_id)]
        if "blocker_titles" in source.data and blockers != (source.data["blocker_titles"] if blockers_expected is None else blockers_expected):
            raise ValidationError("Blocajele s-au schimbat; recalculează răspunsul.")
        if "worked" not in cache:
            cache["worked"] = q.worked_map()
        current_seconds = cache["worked"].get(source.node_id, 0)
        if source.data.get("actual_seconds", current_seconds) != current_seconds:
            raise ValidationError("Sesiunile citate în totalul de timp s-au schimbat; recalculează.")
        if "progress" in source.data:
            progress = q.progress(source.node_id)
            current = {"done_leaves": progress.done, "open_leaves": progress.open, "unestimated": progress.unestimated}
            if current != (progress_expected if progress_expected is not None else source.data["progress"]):
                raise ValidationError("Progresul proiectului s-a schimbat; recalculează.")
        return
    if source.kind == "note":
        record = ws.repo.notes_store(source.node_id).get(source.record_id)
    elif source.kind == "session":
        record = ws.repo.sessions.get(source.record_id)
    elif source.kind == "history":
        record = ws.repo.history.get(source.record_id)
    else:
        raise ValidationError("Tip de sursă nepermis.")
    if record.node_id != source.node_id or digest(record) != source.fingerprint:
        raise ValidationError("Înregistrarea citată s-a schimbat sau aparține altui task.")


def build_context(ws, scope: str, selected_id: str | None, question: str, token=None) -> ContextBundle:
    def check():
        if token:
            token.check()
    check()
    q = Queries(ws)
    if scope not in ("task", "project", "workspace"):
        raise ValidationError("Context necunoscut.")
    anchor = selected_id
    if scope != "workspace":
        if not anchor or anchor not in ws.nodes:
            raise ValidationError("Selectează un nod pentru acest context.")
        if scope == "project":
            project = ws.nearest_project(anchor)
            if not project:
                raise ValidationError("Nodul selectat nu aparține unui proiect.")
            anchor = project.id
    else:
        anchor = None
    bundle = ContextBundle(ws.id, scope, anchor)
    candidates = q.assistant_candidates(question, anchor)
    bundle.matched = len(candidates)
    ids = ([anchor] if anchor else []) + [n.id for n in candidates]
    # Task scope includes its hierarchy, project scope its tasks, workspace scope ranked matches.
    selected = list(dict.fromkeys(ids))[:8]
    for node_id in list(selected):
        for dep in ws.get(node_id).depends_on_ids:
            if dep in ws.nodes and dep not in selected and len(selected) < 12:
                selected.append(dep)
    bundle.truncated = len(set(ids)) > len(selected)
    sessions = SessionService(ws).all(check=check) if selected else []
    worked = q.worked_map(sessions=sessions)
    # Main task/project facts precede activity details so budget reduction retains identity.
    for node_id in selected:
        check()
        n = ws.get(node_id).model_copy(deep=True)
        guard = node_guard(ws, node_id)
        data = {k: n.model_dump(mode="json")[k] for k in (
            "title", "kind", "status", "priority", "due_date", "due_at", "next_action", "waiting_reason",
            "requested_by", "depends_on_ids", "related_node_ids")}
        data["description"] = q.description_text(node_id)[:900]
        data["status_label"] = STATUS_LABELS.get(n.status, "")
        data["priority_label"] = PRIORITY_LABELS.get(n.priority, "")
        data["blocker_titles"] = [item.title for item in ws.unfinished_dependencies(node_id)]
        data["checklist"] = [item.model_dump() for item in n.checklist[:12]]
        data["actual_seconds"] = worked.get(node_id, 0)
        if n.kind == Kind.PROJECT:
            progress = q.progress(node_id)
            data["progress"] = {"done_leaves": progress.done, "open_leaves": progress.open,
                                "unestimated": progress.unestimated}
        source = Source(f"task:{node_id}", "task", node_id, node_id, guard.fingerprint, data)
        bundle.guards[node_id] = guard
        bundle.sources[source.key] = source
    activity = []
    for node_id in selected:
        check()
        for note in ws.list_notes(node_id, check=check)[:3]:
            data = {"at": note.at.isoformat(), "text": note.text[:800], "kind": note.kind}
            activity.append((note.at, Source(f"note:{note.id}", "note", node_id, note.id, digest(note), data)))
        recent = sorted((s for s in sessions if s.node_id == node_id), key=lambda s: s.start_at, reverse=True)[:3]
        for s in recent:
            data = {k: s.model_dump(mode="json").get(k) for k in (
                "start_at", "end_at", "status", "actual_seconds", "summary", "note")}
            for key in ("summary", "note"):
                if data[key]:
                    data[key] = data[key][:800]
            activity.append((s.start_at, Source(f"session:{s.id}", "session", node_id, s.id, digest(s), data)))
    for event in ws.list_history(check=check):
        if event.node_id in selected and event.type == "status_changed":
            activity.append((event.at, Source(f"history:{event.id}", "history", event.node_id, event.id,
                digest(event), {"at": event.at.isoformat(), "type": event.type, "data": event.data})))
    for _, source in sorted(activity, key=lambda pair: pair[0], reverse=True)[:12]:
        bundle.sources[source.key] = source
    if anchor:
        lead = [s for s in bundle.sources.values() if s.node_id == anchor]
        rest = [s for s in bundle.sources.values() if s.node_id != anchor]
        bundle.sources = {s.key: s for s in [*lead, *rest]}
    # IPC bound and a modest retrieval cap. Exact token accounting happens in the model process.
    while len(bundle.wire().encode("utf-8")) > 24000 and bundle.sources:
        bundle.sources.pop(next(reversed(bundle.sources)))
        bundle.truncated = True
    check()
    return bundle
