"""Estimări AI distincte de câmpurile confirmate; fără adrese/date/încredere inventate."""

from typing import Literal
from pydantic import Field, PrivateAttr
from .assistant_protocol import Id, StrictModel


class MailAnalysis(StrictModel):
    _candidate_ids: list[str] = PrivateAttr(default_factory=list)
    _body_chars: int = PrivateAttr(default=0)
    _usage: dict[str, int] = PrivateAttr(default_factory=dict)
    classification: Literal["informational", "request", "update", "clarify"]
    summary: str = Field(min_length=1, max_length=1500)
    evidence_quote: str = Field(min_length=1, max_length=1000)
    task_title: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=3000)
    requester_is_sender: bool = False
    deadline_quote: str | None = Field(default=None, max_length=500)
    target_task_id: Id | None = None
    status: Literal["todo", "in_progress", "waiting", "done", "cancelled"] | None = None
    status_quote: str | None = Field(default=None, max_length=500)
    waiting_reason: str | None = Field(default=None, max_length=1000)
    next_action: str | None = Field(default=None, max_length=1000)
    journal_update: str | None = Field(default=None, max_length=2000)
    clarification: str | None = Field(default=None, max_length=1000)
