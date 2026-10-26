"""Protocol IPC JSON v1: numai date, fără obiecte Tk/Workspace sau pickle primit."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from .assistant_protocol import AssistantReply
from .mail_protocol import MailAnalysis

MAX_MESSAGE = 128 * 1024
LegacyAction = Literal["create_subtask", "add_note", "set_next_action"]
Action = Literal["create_subtask", "add_note", "set_next_action", "assistant", "analyze_mail"]


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class EngineSettings(Message):
    model_path: str = ""
    context: int = Field(default=4096, ge=2048, le=32768)
    threads: int = Field(default=4, ge=1, le=64)
    timeout: int = Field(default=180, ge=5, le=1800)


class Proposal(Message):
    action: LegacyAction
    title: str = Field(max_length=200)
    text: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def semantic_shape(self) -> "Proposal":
        if not self.text.strip() or "\x00" in self.text or "\x00" in self.title:
            raise ValueError("Propunere goală sau cu caractere nepermise.")
        if self.action == "create_subtask":
            if not self.title.strip() or "\n" in self.title or "\r" in self.title:
                raise ValueError("Subtask-ul necesită un titlu pe o singură linie.")
        elif self.title:
            raise ValueError("Titlul trebuie să fie gol pentru această operație.")
        return self


class Request(Message):
    version: Literal[1] = 1
    request_id: str
    action: Action
    intent: Literal["chat", "resume", "steps", "project_summary", "email", "actions"] = "chat"
    instruction: str = Field(min_length=1, max_length=4000)
    context: str = Field(max_length=32000)

    @model_validator(mode="after")
    def valid_id(self) -> "Request":
        UUID(self.request_id)
        return self


class Response(Message):
    version: Literal[1] = 1
    request_id: str
    kind: Literal["loading", "result", "error"]
    proposal: Proposal | None = None
    assistant: AssistantReply | None = None
    mail_analysis: MailAnalysis | None = None
    mail_body_chars: int | None = None
    mail_candidate_ids: list[str] | None = None
    context_keys: list[str] = Field(default_factory=list)
    usage: dict[str, int] = Field(default_factory=dict)
    error: str = ""

    @model_validator(mode="after")
    def valid_payload(self) -> "Response":
        UUID(self.request_id)
        payloads = int(self.proposal is not None) + int(self.assistant is not None) + int(self.mail_analysis is not None)
        if payloads != (1 if self.kind == "result" else 0):
            raise ValueError("Rezultat IPC inconsistent.")
        return self


class Stop(Message):
    version: Literal[1] = 1
    request_id: str
    kind: Literal["stop"] = "stop"

    @model_validator(mode="after")
    def valid_id(self) -> "Stop":
        UUID(self.request_id)
        return self


def encode(message: Message) -> bytes:
    data = message.model_dump_json().encode("utf-8")
    if len(data) > MAX_MESSAGE:
        raise ValueError("Mesajul AI depășește limita IPC.")
    return data
