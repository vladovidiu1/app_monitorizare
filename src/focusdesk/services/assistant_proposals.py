"""Validare, before/after, write-ahead și rezultate parțiale ale propunerilor."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import json
import re
import threading
from uuid import uuid4

from pydantic import TypeAdapter

from ..ai.assistant_protocol import AddNote, AssociateMail, AssistantReply, CreateTask, LinkTasks, Operation, UpdateTask
from ..domain.models import Kind, Node
from ..errors import ValidationError
from .assistant_context import ContextBundle, Guard, node_guard, validate_source
from .queries import Queries

operation_adapter = TypeAdapter(Operation)


def operation_ids(operation) -> set[str]:
    if isinstance(operation, CreateTask):
        return {operation.parent_id} if operation.parent_id else set()
    ids = {operation.node_id}
    if isinstance(operation, LinkTasks):
        ids.add(operation.other_id)
    return ids


def patch_values(operation: UpdateTask, node=None) -> dict:
    values = operation.patch.model_dump(exclude_unset=True)
    if not values:
        raise ValidationError("Actualizarea nu conține niciun câmp.")
    if "due_date" in values and values["due_date"] is not None:
        values["due_date"] = date.fromisoformat(values["due_date"])
        values["due_at"] = None
    if "checklist" in values and values["checklist"] is not None and node is not None:
        existing = {item.text.casefold() for item in node.checklist}
        values["checklist"] = [item.model_dump() for item in node.checklist] + [
            item for item in values["checklist"] if item["text"].casefold() not in existing]
    return values


def simulate(ws, operations: list, allowed: set[str]) -> list[dict]:
    """Preflight secvențial fără scrieri, inclusiv cicluri între acțiuni din același lot."""
    # Never mutate Node instances: proposed replacements are new validated objects.
    virtual = dict(ws.nodes)
    previews = []
    q = Queries(ws)
    for operation in operations:
        operation = operation_adapter.validate_python(operation.model_dump(exclude_unset=True))
        ids = operation_ids(operation)
        if not ids <= allowed:
            raise ValidationError("Ținta sau legătura nu a fost inclusă în context. Recalculează cu contextul potrivit.")
        for node_id in ids:
            if node_id not in virtual or q.is_archived(virtual[node_id]):
                raise ValidationError("Țintă inexistentă sau arhivată.")
        if isinstance(operation, CreateTask):
            ws.check_parent(Kind.TASK, operation.parent_id)
            node = Node(kind=Kind.TASK, title=operation.title, parent_id=operation.parent_id,
                        status="todo", priority="normal", due_date=date.fromisoformat(operation.due_date) if operation.due_date else None,
                        requested_by={"name": operation.requested_by.name, "code": "", "email_address": operation.requested_by.email_address} if operation.requested_by else None,
                        checklist=operation.checklist and
                        [v.model_dump() for v in operation.checklist] or [])
            previews.append({"before": None, "after": {"title": node.title, "parent_id": node.parent_id,
                "description": operation.description, "due_date": operation.due_date,
                "requested_by": node.requested_by.model_dump() if node.requested_by else None,
                "checklist": [v.model_dump() for v in operation.checklist]}})
        elif isinstance(operation, AddNote):
            if not operation.text.strip():
                raise ValidationError("Notiță goală.")
            previews.append({"before": None, "after": {"node_id": operation.node_id, "note": operation.text}})
        elif isinstance(operation, AssociateMail):
            message = ws.mail_get(operation.mail_id)
            if message is None or virtual[operation.node_id].kind != Kind.TASK:
                raise ValidationError("Asocierea necesită un mail și un task existent.")
            previews.append({"before": {"confirmed_task_ids": message.confirmed_task_ids},
                             "after": {"confirmed_task_ids": list(dict.fromkeys([*message.confirmed_task_ids, operation.node_id]))}})
        else:
            node = virtual[operation.node_id]
            if node.kind != Kind.TASK:
                raise ValidationError("Actualizările și legăturile AI se aplică doar taskurilor.")
            if isinstance(operation, UpdateTask):
                values = patch_values(operation, node)
            else:
                if virtual[operation.other_id].kind != Kind.TASK:
                    raise ValidationError("Legăturile propuse de AI necesită două taskuri existente.")
                if operation.node_id == operation.other_id:
                    raise ValidationError("Un task nu se poate lega de sine.")
                key = "depends_on_ids" if operation.relation == "depends_on" else "related_node_ids"
                values = {key: list(dict.fromkeys([*getattr(node, key), operation.other_id]))}
                if operation.relation == "depends_on":
                    seen, stack = set(), [operation.other_id]
                    while stack:
                        current = stack.pop()
                        if current == node.id:
                            raise ValidationError("Dependențele ar forma un ciclu.")
                        if current not in seen and current in virtual:
                            seen.add(current)
                            stack.extend(virtual[current].depends_on_ids)
            updated = Node.model_validate({**node.model_dump(), **values})
            previews.append({"before": {k: node.model_dump(mode="json")[k] for k in values},
                             "after": {k: updated.model_dump(mode="json")[k] for k in values}})
            virtual[node.id] = updated
    return previews


def validate_reply(ws, bundle: ContextBundle, reply: AssistantReply, included: list[str], intent=None) -> None:
    AssistantReply.model_validate(reply.model_dump(exclude_unset=True))
    if ws.id != bundle.workspace_id:
        raise ValidationError("Workspace-ul s-a schimbat.")
    if intent in ("chat", "resume", "project_summary") and (reply.actions or reply.email):
        raise ValidationError("Cererea este numai pentru consultare, nu pentru modificări sau e-mail.")
    if intent == "steps" and (reply.email or any(not isinstance(op, (CreateTask, UpdateTask)) for op in reply.actions)):
        raise ValidationError("Propune pași permite numai subtaskuri și actualizări de câmpuri/checklist.")
    if intent == "steps" and any(isinstance(op, UpdateTask) and not op.patch.model_fields_set <= {"checklist", "next_action"} for op in reply.actions):
        raise ValidationError("Propune pași nu modifică statusul, termenele sau alte câmpuri.")
    if intent == "email" and reply.actions:
        raise ValidationError("Pregătirea e-mailului nu modifică taskuri.")
    available = set(included)
    if not available <= bundle.sources.keys():
        raise ValidationError("Motorul a returnat surse necunoscute.")
    cache = {}
    for key in available:
        validate_source(ws, bundle.sources[key], bundle.guards, cache)
    evidence = [*reply.answer, *reply.actions, *([reply.email] if reply.email else [])]
    for part in evidence:
        if not set(part.sources) <= available or (available and not part.sources):
            raise ValidationError("Răspuns fără surse sau cu ID de sursă inventat.")
    # Numbers in activity prose must occur in the cited records, not in UUIDs.
    factual_parts = [(part.text, part.sources) for part in reply.answer]
    if reply.email:
        factual_parts.append((reply.email.subject + " " + reply.email.body, reply.email.sources))
    for text, sources in factual_parts:
        facts = json.dumps([bundle.sources[key].data for key in sources], ensure_ascii=False)
        numbers = set(re.findall(r"(?<!\w)\d+(?:[.,:]\d+)*(?!\w)", facts))
        checked_text = re.sub(rf"\b{bundle.matched}\s+taskuri\b", "taskuri", text, flags=re.IGNORECASE)
        if reply.actions:
            checked_text = re.sub(rf"\b{len(reply.actions)}\s+(?:propuneri|subtaskuri|pași|acțiuni)\b", "propuneri", checked_text, flags=re.IGNORECASE)
        claims = set(re.findall(r"(?<!\w)\d+(?:[.,:]\d+)*(?!\w)", checked_text))
        if not claims <= numbers:
            raise ValidationError("Răspunsul conține numere/timpi/termene fără suport în sursele citate.")
        if re.search(r"(?<!nu )am\s+(?:analizat|citit|verificat|rulat|testat)\s+codul|codul\s+(?:este corect|funcționează|nu are erori)", text.casefold()):
            raise ValidationError("Asistentul nu a primit cod; afirmația despre verificarea lui este respinsă.")
    allowed = {bundle.sources[key].node_id for key in available if bundle.sources[key].kind != "mail"}
    for op in reply.actions:
        if not operation_ids(op) <= {bundle.sources[key].node_id for key in op.sources if bundle.sources[key].kind != "mail"}:
            raise ValidationError("Țintele propunerii nu sunt susținute de sursele ei.")
        if isinstance(op, AssociateMail) and f"mail:{op.mail_id}" not in op.sources:
            raise ValidationError("Asociere fără sursa mail validată.")
        proposed_checks = op.checklist if isinstance(op, CreateTask) else op.patch.checklist if isinstance(op, UpdateTask) else []
        if proposed_checks and any(item.done for item in proposed_checks):
            raise ValidationError("AI nu poate declara pași nou propuși deja finalizați.")
    if bundle.scope != "workspace" and any(isinstance(op, CreateTask) and op.parent_id is None for op in reply.actions):
        raise ValidationError("Crearea la rădăcină necesită contextul Întreg workspace.")
    simulate(ws, reply.actions, allowed)
    if reply.email:
        if (reply.email.node_id not in allowed or "\n" in reply.email.subject or "\r" in reply.email.subject
                or reply.email.node_id not in {bundle.sources[key].node_id for key in reply.email.sources}):
            raise ValidationError("Ciornă e-mail cu țintă sau subiect invalid.")
    if not available and (reply.actions or reply.email):
        raise ValidationError("Nu se propun operații fără surse.")


@dataclass
class ProposalItem:
    operation: object
    id: str = field(default_factory=lambda: str(uuid4()))
    state: str = "pending"
    detail: str = ""
    edited: bool = False


@dataclass
class ProposalBatch:
    bundle: ContextBundle
    included: list[str]
    items: list[ProposalItem]
    guards: dict[str, Guard]
    progress_expected: dict = field(default_factory=dict)
    blockers_expected: dict = field(default_factory=dict)
    intent: str | None = None
    id: str = field(default_factory=lambda: str(uuid4()))

    @classmethod
    def prepare(cls, ws, bundle, reply, included, intent=None):
        validate_reply(ws, bundle, reply, included, intent)
        return cls(bundle=bundle, included=list(included), items=[ProposalItem(op.model_copy(deep=True)) for op in reply.actions],
                   guards=dict(bundle.guards), intent=intent,
                   progress_expected={key: source.data["progress"] for key, source in bundle.sources.items() if "progress" in source.data},
                   blockers_expected={key: source.data["blocker_titles"] for key, source in bundle.sources.items() if "blocker_titles" in source.data})

    def allowed(self) -> set[str]:
        return {self.bundle.sources[key].node_id for key in self.included if self.bundle.sources[key].kind != "mail"}

    def check(self, ws) -> None:
        if ws.id != self.bundle.workspace_id or ws.read_only:
            raise ValidationError("Workspace diferit sau doar pentru citire.")
        cache = {}
        for key in self.included:
            validate_source(ws, self.bundle.sources[key], self.guards, cache, self.progress_expected.get(key), self.blockers_expected.get(key))

    def preview(self, ws, items=None) -> list[dict]:
        self.check(ws)
        pending = items if items is not None else [i for i in self.items if i.state == "pending"]
        return simulate(ws, [i.operation for i in pending], self.allowed())

    def edit(self, ws, index: int, payload: dict) -> None:
        item = self.items[index]
        if item.state != "pending" or ws.ai_receipt(item.id):
            raise ValidationError("Propunerea înregistrată nu se modifică; cere una nouă.")
        operation = operation_adapter.validate_python(payload)
        if self.intent == "steps" and not isinstance(operation, (CreateTask, UpdateTask)):
            raise ValidationError("Păstrează tipul de operație permis pentru pași.")
        if self.intent == "steps" and isinstance(operation, UpdateTask) and not operation.patch.model_fields_set <= {"checklist", "next_action"}:
            raise ValidationError("Pentru pași modifică doar checklistul sau următorul pas.")
        if isinstance(operation, CreateTask) and operation.parent_id is None and self.bundle.scope != "workspace":
            raise ValidationError("Păstrează părintele în contextul selectat.")
        if not set(operation.sources) <= set(self.included):
            raise ValidationError("Surse modificate nepermis.")
        if not operation_ids(operation) <= {self.bundle.sources[key].node_id for key in operation.sources if self.bundle.sources[key].kind != "mail"}:
            raise ValidationError("Țintele modificate necesită surse corespunzătoare.")
        if isinstance(operation, AssociateMail) and f"mail:{operation.mail_id}" not in operation.sources:
            raise ValidationError("Asociere fără sursa mail validată.")
        self.check(ws)
        planned = [operation if i is item else i.operation for i in self.items if i.state == "pending"]
        simulate(ws, planned, self.allowed())
        item.operation = operation
        item.edited = True

    def reject(self, ws, index: int) -> None:
        if ws.id != self.bundle.workspace_id:
            raise ValidationError("Workspace-ul s-a schimbat.")
        item = self.items[index]
        if item.state != "pending":
            return
        self._claim(ws, item)
        ws.finish_ai_action(item.id, "rejected", "Respins explicit de utilizator.")
        item.state, item.detail = "rejected", "Respins de utilizator."

    def _claim(self, ws, item, preview=None) -> None:
        if ws.id != self.bundle.workspace_id:
            raise ValidationError("Workspace-ul s-a schimbat.")
        op = item.operation
        target = op.parent_id if isinstance(op, CreateTask) else op.node_id
        ws.claim_ai_action(item.id, target, {
            "batch_id": self.id, "operation": op.model_dump(mode="json", exclude_unset=True), "preview": preview, "edited": item.edited})

    def clarification_issue(self, item):
        for key in item.operation.sources:
            source = self.bundle.sources[key]
            if source.kind != "mail":
                continue
            if source.data.get("deadline_ambiguous") and isinstance(item.operation, (CreateTask, UpdateTask)):
                value = item.operation.due_date if isinstance(item.operation, CreateTask) else item.operation.patch.due_date
                if not item.edited or not value:
                    return "Clarifică termenul în Modifică înainte de acceptare."
            if source.data.get("requester_unresolved") and isinstance(item.operation, CreateTask) and not item.operation.requested_by:
                return "Completează solicitantul/adresa SMTP confirmată în Modifică."
        return None

    def apply(self, ws, indices: list[int] | None = None) -> list[dict]:
        if threading.current_thread() is not threading.main_thread():
            raise ValidationError("Aplicarea AI este permisă doar pe firul UI.")
        selected = [self.items[i] for i in (indices if indices is not None else range(len(self.items)))]
        results = []
        for item in selected:
            try:
                receipt = ws.ai_receipt(item.id)
            except Exception as exc:
                item.state, item.detail = "uncertain", f"Istoricul nu poate fi citit; nu se execută/repetă operația: {exc}"
                results.append({"id": item.id, "state": item.state, "detail": item.detail})
                results.extend({"id": later.id, "state": "not_run", "detail": "Oprit: istoricul nu poate fi verificat."}
                               for later in selected[selected.index(item) + 1:] if later.state == "pending")
                break
            if receipt:
                state = receipt.data.get("state", "started")
                item.state = "uncertain" if state == "started" else state
                results.append({"id": item.id, "state": "already_recorded", "detail": item.state})
                continue
            if item.state != "pending":
                results.append({"id": item.id, "state": item.state, "detail": item.detail})
                continue
            issue = self.clarification_issue(item)
            if issue:
                results.append({"id": item.id, "state": "needs_clarification", "detail": issue})
                continue
            try:
                preview = self.preview(ws, [item])[0]
            except Exception as exc:
                item.state, item.detail = "conflict", f"Recalculare necesară: {exc}"
                try:
                    self._claim(ws, item)
                    ws.finish_ai_action(item.id, "conflict", item.detail)
                except Exception:
                    pass  # Never log a conflict into a different/read-only workspace.
                results.append({"id": item.id, "state": item.state, "detail": item.detail})
                continue
            try:
                self._claim(ws, item, preview)
            except Exception as exc:
                item.state, item.detail = "failed", f"Nu s-a executat: istoricul nu poate fi rezervat: {exc}"
                results.append({"id": item.id, "state": item.state, "detail": item.detail})
                continue
            try:
                op = item.operation
                if isinstance(op, CreateTask):
                    created = ws.create_node(Kind.TASK, op.title, op.parent_id, description=op.description,
                                             due_date=date.fromisoformat(op.due_date) if op.due_date else None,
                                             requested_by={"name": op.requested_by.name, "code": "", "email_address": op.requested_by.email_address} if op.requested_by else None,
                                             checklist=[v.model_dump() for v in op.checklist])
                    for key in op.sources:
                        if self.bundle.sources[key].kind == "mail":
                            ws.confirm_mail_link(self.bundle.sources[key].record_id, created.id)
                    detail = f"Task creat: {created.id}"
                elif isinstance(op, UpdateTask):
                    ws.update_node(op.node_id, **patch_values(op, ws.get(op.node_id)))
                    detail = "Câmpuri actualizate."
                elif isinstance(op, AddNote):
                    note = ws.add_note(op.node_id, op.text)
                    detail = f"Notiță adăugată: {note.id}"
                elif isinstance(op, LinkTasks):
                    fn = ws.add_dependency if op.relation == "depends_on" else ws.add_related
                    fn(op.node_id, op.other_id)
                    detail = "Legătură adăugată."
                elif isinstance(op, AssociateMail):
                    ws.confirm_mail_link(op.mail_id, op.node_id)
                    detail = "Asociere mail–task confirmată explicit."
                from dataclasses import asdict
                after_guards = {node_id: asdict(node_guard(ws, node_id)) for node_id in operation_ids(op)}
                ws.finish_ai_action(item.id, "applied", detail, after_guards=after_guards)
                item.state, item.detail = "applied", detail
            except Exception as exc:
                # Even an exception may occur AFTER a Workspace write. Never claim rollback.
                item.state, item.detail = "uncertain", f"Rezultat incert; verifică datele și istoricul: {exc}"
                try:
                    ws.finish_ai_action(item.id, "uncertain", item.detail)
                except Exception:
                    pass  # The persisted 'started' receipt still prevents replay.
            if item.state == "applied":
                try:
                    for node_id in operation_ids(op):
                        self.guards[node_id] = node_guard(ws, node_id)
                    for key in self.progress_expected:
                        progress = Queries(ws).progress(self.bundle.sources[key].node_id)
                        self.progress_expected[key] = {"done_leaves": progress.done, "open_leaves": progress.open,
                                                       "unestimated": progress.unestimated}
                    for key in self.blockers_expected:
                        self.blockers_expected[key] = [node.title for node in ws.unfinished_dependencies(self.bundle.sources[key].node_id)]
                except Exception as exc:
                    item.detail += f" Surse schimbate după aplicare; recalculează: {exc}"
            results.append({"id": item.id, "state": item.state, "detail": item.detail})
            if item.state == "uncertain":
                results.extend({"id": later.id, "state": "not_run", "detail": "Oprit după un rezultat incert."}
                               for later in selected[selected.index(item) + 1:] if later.state == "pending")
                break
        return results
