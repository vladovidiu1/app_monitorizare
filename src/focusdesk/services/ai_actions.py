"""Propuneri AI: ținta este stabilită de UI; aplicare explicită prin Workspace."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from uuid import uuid4

from ..ai.protocol import Action, Proposal
from ..domain.models import Kind
from ..errors import ValidationError
from .workspace import Workspace


@dataclass(frozen=True)
class ActionContext:
    workspace_id: str
    node_id: str
    revision: int
    action: Action
    source_hash: str
    application_id: str = field(default_factory=lambda: str(uuid4()))

    @staticmethod
    def fingerprint(ws: Workspace, node_id: str) -> str:
        directory = ws.repo.dirs[node_id]
        digest = hashlib.sha256((directory / "node.json").read_bytes())
        description = directory / "description.md"
        digest.update(b"\x00description\x00")
        digest.update(description.read_bytes() if description.exists() else b"")
        return digest.hexdigest()

    @classmethod
    def capture(cls, ws: Workspace, node_id: str, action: Action) -> "ActionContext":
        node = ws.get(node_id)
        if ws.read_only or node.archived_at:
            raise ValidationError("AI necesită un nod activ într-un workspace editabil.")
        return cls(ws.id, node.id, node.revision, action, cls.fingerprint(ws, node.id))


def validate_proposal(ws: Workspace, context: ActionContext, proposal: Proposal) -> None:
    # Revalidate even when the caller passed an already constructed Pydantic object.
    Proposal.model_validate(proposal.model_dump())
    if ws.id != context.workspace_id or ws.read_only:
        raise ValidationError("Workspace-ul s-a schimbat sau este doar pentru citire.")
    node = ws.get(context.node_id)
    if (node.revision != context.revision or node.archived_at
            or ActionContext.fingerprint(ws, node.id) != context.source_hash):
        raise ValidationError("Nodul s-a schimbat. Generează o propunere nouă.")
    if proposal.action != context.action:
        raise ValidationError("AI a propus o altă operație decât cea solicitată.")
    if proposal.action == "set_next_action" and node.kind != Kind.TASK:
        raise ValidationError("Următorul pas se stabilește doar pentru task-uri.")


def apply_proposal(ws: Workspace, context: ActionContext, proposal: Proposal) -> None:
    """Apelată exclusiv de UI după previzualizare și confirmare; o singură operație."""
    validate_proposal(ws, context, proposal)
    # Compatibility for the original dialog, using the same persistent receipt path as chat.
    from ..ai.assistant_protocol import AssistantReply
    from .assistant_context import ContextBundle, Guard, Source
    from .assistant_proposals import ProposalBatch

    key = f"task:{context.node_id}"
    bundle = ContextBundle(ws.id, "task", context.node_id)
    bundle.guards[context.node_id] = Guard(context.revision, context.source_hash)
    bundle.sources[key] = Source(key, "task", context.node_id, context.node_id, context.source_hash,
                                {"title": ws.get(context.node_id).title})
    common = {"reason": "Propunere confirmată în dialogul AI.", "sources": [key]}
    if proposal.action == "create_subtask":
        operation = {**common, "kind": "create_task", "parent_id": context.node_id,
                     "title": proposal.title.strip(), "description": proposal.text.strip()}
    elif proposal.action == "add_note":
        operation = {**common, "kind": "add_note", "node_id": context.node_id, "text": proposal.text.strip()}
    else:
        operation = {**common, "kind": "update_task", "node_id": context.node_id,
                     "patch": {"next_action": proposal.text.strip()}}
    reply = AssistantReply.model_validate({"answer": [{"text": "Propunere", "sources": [key]}], "actions": [operation]})
    batch = ProposalBatch.prepare(ws, bundle, reply, [key])
    batch.items[0].id = context.application_id
    result = batch.apply(ws)[0]
    if result["state"] != "applied":
        raise ValidationError(f"Propunerea nu a fost reaplicată: {result['state']} — {result['detail']}")
