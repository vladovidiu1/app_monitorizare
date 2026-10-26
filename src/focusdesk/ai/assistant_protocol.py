"""Răspunsuri și operații permise; niciun nume de metodă sau comandă arbitrară."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, PrivateAttr


def uuid_text(value: str) -> str:
    if str(UUID(value)) != value:
        raise ValueError("UUID canonic necesar.")
    return value


Id = Annotated[str, AfterValidator(uuid_text)]
Text = Annotated[str, Field(min_length=1, max_length=4000)]
SourceKeys = Annotated[list[str], Field(min_length=1, max_length=12)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CheckItem(StrictModel):
    text: Annotated[str, Field(min_length=1, max_length=300)]
    done: bool = False


class TaskPatch(StrictModel):
    title: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    status: Literal["inbox", "todo", "in_progress", "waiting", "testing", "done", "cancelled"] | None = None
    priority: Literal["urgent", "high", "normal", "low"] | None = None
    next_action: Annotated[str, Field(max_length=2000)] | None = None
    waiting_reason: Annotated[str, Field(max_length=2000)] | None = None
    due_date: str | None = None
    estimated_minutes: Annotated[int, Field(ge=0, le=100000)] | None = None
    remaining_minutes: Annotated[int, Field(ge=0, le=100000)] | None = None
    tags: Annotated[list[str], Field(max_length=20)] | None = None
    checklist: Annotated[list[CheckItem], Field(max_length=30)] | None = None


class Evidence(StrictModel):
    reason: Annotated[str, Field(min_length=1, max_length=1000)]
    sources: SourceKeys


class RequesterSpec(StrictModel):
    name: Annotated[str, Field(min_length=1, max_length=200)]
    email_address: Annotated[str, Field(min_length=3, max_length=320)]


class CreateTask(Evidence):
    kind: Literal["create_task"]
    parent_id: Id | None
    title: Annotated[str, Field(min_length=1, max_length=200)]
    description: Annotated[str, Field(max_length=4000)] = ""
    checklist: Annotated[list[CheckItem], Field(max_length=30)] = Field(default_factory=list)
    due_date: str | None = None
    requested_by: RequesterSpec | None = None


class UpdateTask(Evidence):
    kind: Literal["update_task"]
    node_id: Id
    patch: TaskPatch


class AddNote(Evidence):
    kind: Literal["add_note"]
    node_id: Id
    text: Text


class LinkTasks(Evidence):
    kind: Literal["link_tasks"]
    node_id: Id
    other_id: Id
    relation: Literal["related", "depends_on"]


class AssociateMail(Evidence):
    kind: Literal["associate_mail"]
    node_id: Id
    mail_id: Id


Operation = Annotated[CreateTask | UpdateTask | AddNote | LinkTasks | AssociateMail, Field(discriminator="kind")]


class AnswerPart(StrictModel):
    text: Text
    sources: Annotated[list[str], Field(max_length=12)]


class EmailProposal(Evidence):
    node_id: Id
    subject: Annotated[str, Field(min_length=1, max_length=200)]
    body: Text


class AssistantReply(StrictModel):
    _context_keys: list[str] = PrivateAttr(default_factory=list)
    _usage: dict[str, int] = PrivateAttr(default_factory=dict)
    answer: Annotated[list[AnswerPart], Field(min_length=1, max_length=8)]
    actions: Annotated[list[Operation], Field(max_length=8)] = Field(default_factory=list)
    email: EmailProposal | None = None
