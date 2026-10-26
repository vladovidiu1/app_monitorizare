"""DTO-uri și stare locală pentru citire Outlook. Nu conțin obiecte COM."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FolderChoice(BaseModel):
    store_id: str
    folder_id: str
    mailbox: str = ""
    path: str = ""


class AttachmentMeta(BaseModel):
    filename: str
    size: int = 0
    type: int = 0


class MailHeader(BaseModel):
    model_config = ConfigDict(extra="forbid")
    store_id: str
    folder_id: str
    entry_id: str
    internet_id: str = ""
    search_key: str = ""
    conversation_id: str = ""
    subject: str = ""
    sender_name: str = ""
    sender_smtp: str | None = None
    sent_at: datetime
    received_at: datetime
    modified_at: datetime

    @field_validator("sent_at", "received_at", "modified_at")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError("Data mailului necesită fus explicit.")
        return value

    @property
    def identity(self) -> str:
        stable = "internet:" + self.internet_id.strip() if self.internet_id.strip() else (
            "search:" + self.search_key if self.search_key else "entry:" + self.entry_id)
        return str(uuid5(NAMESPACE_URL, "focusdesk-mail:" + self.store_id + ":" + stable))

    @property
    def conversation_key(self) -> str:
        return str(uuid5(NAMESPACE_URL, "focusdesk-conversation:" + self.store_id + ":" +
                         (self.conversation_id or self.identity)))


class MailRecord(BaseModel):
    id: str
    header: MailHeader
    body: str = ""
    body_truncated: bool = False
    body_loaded: bool = False
    attachments: list[AttachmentMeta] = Field(default_factory=list)
    content_version: int = 1
    content_hash: str = ""
    state: Literal["pending", "proposed", "clarify", "informational", "handled", "rejected", "ignored", "error"] = "pending"
    suspended_state: Literal["pending", "proposed", "clarify", "informational", "handled", "rejected", "error"] | None = None
    confirmed_task_ids: list[str] = Field(default_factory=list)
    analysis: dict | None = None
    projection: dict | None = None
    context_snapshot: dict | None = None
    included_keys: list[str] = Field(default_factory=list)
    proposal_ids: list[str] = Field(default_factory=list)
    edited_items: list[bool] = Field(default_factory=list)
    analysis_generation: str = ""
    clarification: list[str] = Field(default_factory=list)


class FolderCursor(BaseModel):
    cutover: str
    initial_from: str
    initial_to: str
    initial_count: int = 0
    initial_done: bool = False
    watermark: str
    window_from: str | None = None
    window_to: str | None = None
    offset: int = 0
    limit_reached: bool = False


class MailMonitorState(BaseModel):
    cursors: dict[str, FolderCursor] = Field(default_factory=dict)
    ignored_conversations: list[str] = Field(default_factory=list)
    next_folder: int = 0
