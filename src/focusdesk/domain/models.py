"""Modelele nodurilor din workspace (folder, proiect, task)."""

from __future__ import annotations

from ..i18n import tr

from datetime import date
from enum import StrEnum
from pathlib import Path, PureWindowsPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .common import UtcDateTime, is_uuid, new_id, utcnow
from .colleagues import Colleague

SCHEMA_VERSION = 1


class Kind(StrEnum):
    FOLDER = "folder"
    PROJECT = "project"
    TASK = "task"


class Status(StrEnum):
    INBOX = "inbox"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    WAITING = "waiting"
    TESTING = "testing"
    DONE = "done"
    CANCELLED = "cancelled"


class Priority(StrEnum):
    URGENT = "urgent"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


OPEN_STATUSES = frozenset({Status.INBOX, Status.TODO, Status.IN_PROGRESS, Status.WAITING, Status.TESTING})
CLOSED_STATUSES = frozenset({Status.DONE, Status.CANCELLED})
PRIORITY_ORDER = {Priority.URGENT: 0, Priority.HIGH: 1, Priority.NORMAL: 2, Priority.LOW: 3}

# Nume rezervate pentru directoarele din interiorul unui nod (nu pot fi noduri).
NODE_SPECIAL_DIRS = frozenset({"notes", "files", "snapshots", "children"})


class _Base(BaseModel):
    # extra="allow" pastreaza campurile necunoscute la rescriere (compatibilitate viitoare).
    model_config = ConfigDict(extra="allow", validate_assignment=True, use_enum_values=False)


def validate_managed_relpath(path: str) -> str:
    p = PureWindowsPath(path)
    if p.is_absolute() or p.drive or p.root:
        raise ValueError(tr('extra.domain.models.calea_administrata_trebuie_sa_fie_relativa'))
    if any(part in ("..",) for part in p.parts):
        raise ValueError(tr('extra.domain.models.calea_administrata_nu_poate_contine'))
    if not p.parts:
        raise ValueError(tr('extra.domain.models.calea_administrata_este_goala'))
    return path.replace("\\", "/")


def validate_external_path(path: str) -> str:
    if not (PureWindowsPath(path).is_absolute() or Path(path).is_absolute()):
        raise ValueError(tr('extra.domain.models.calea_externa_trebuie_sa_fie_absoluta'))
    return path


class SourceWorkspace(_Base):
    """Folderul de cod asociat unui nod: `external` (cale absoluta) sau `managed` (relativ la nod)."""

    path: str = ""
    mode: Literal["external", "managed", "shared", "disabled"] = "external"
    owner_node_id: str | None = None
    shared_mode: Literal["external", "managed"] | None = None

    @model_validator(mode="after")
    def _check_path(self) -> "SourceWorkspace":
        if self.mode == 'disabled':
            if self.path or self.owner_node_id or self.shared_mode: raise ValueError(tr('extra.domain.models.acces_dezactivat_cu_referinta_invalida'))
        elif self.mode == 'shared':
            if not self.owner_node_id or not is_uuid(self.owner_node_id) or self.shared_mode is None:
                raise ValueError(tr('extra.domain.models.sursa_comuna_necesita_proprietar_uuid_si_mod_explicit'))
            if self.shared_mode == 'managed': validate_managed_relpath(self.path)
            else: validate_external_path(self.path)
        elif self.mode == "managed":
            validate_managed_relpath(self.path)
        else:
            validate_external_path(self.path)
        return self


class Attachment(_Base):
    id: str = Field(default_factory=new_id)
    name: str
    mode: Literal["managed", "external"]
    path: str
    is_dir: bool = False
    added_at: UtcDateTime = Field(default_factory=utcnow)

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not is_uuid(v):
            raise ValueError("id invalid")
        return v

    @model_validator(mode="after")
    def _check_path(self) -> "Attachment":
        if self.mode == "managed":
            validate_managed_relpath(self.path)
        else:
            validate_external_path(self.path)
        return self


class ChecklistItem(_Base):
    text: str
    done: bool = False


class Node(_Base):
    schema_version: int = SCHEMA_VERSION
    revision: int = 1
    id: str = Field(default_factory=new_id)
    kind: Kind
    title: str
    parent_id: str | None = None
    status: Status | None = None
    priority: Priority | None = None
    created_at: UtcDateTime = Field(default_factory=utcnow)
    updated_at: UtcDateTime = Field(default_factory=utcnow)
    due_date: date | None = None
    due_at: UtcDateTime | None = None
    estimated_minutes: int | None = None
    remaining_minutes: int | None = None
    next_action: str | None = None
    waiting_reason: str | None = None
    requested_by: Colleague | None = None
    review_at: UtcDateTime | None = None
    tags: list[str] = Field(default_factory=list)
    continuation_of: str | None = None  # Typed follow-up relation, independent of hierarchy/dependencies.
    creation_operation_id: str | None = None
    meeting_ids: list[str] = Field(default_factory=list)
    related_node_ids: list[str] = Field(default_factory=list)
    depends_on_ids: list[str] = Field(default_factory=list)
    sort_order: int = 0
    archived_at: UtcDateTime | None = None
    completed_at: UtcDateTime | None = None
    pinned_today: date | None = None
    source_workspace: SourceWorkspace | None = None
    checklist: list[ChecklistItem] = Field(default_factory=list)
    attachments: list[Attachment] = Field(default_factory=list)
    recurrence_template_id: str | None = None
    occurrence_date: date | None = None

    @field_validator("id", "parent_id", "continuation_of", "creation_operation_id")
    @classmethod
    def _uuid(cls, v: str | None) -> str | None:
        if v is not None and not is_uuid(v):
            raise ValueError("UUID invalid")
        return v

    @field_validator("related_node_ids", "depends_on_ids", "meeting_ids")
    @classmethod
    def _uuid_list(cls, v: list[str]) -> list[str]:
        for item in v:
            if not is_uuid(item):
                raise ValueError(tr('extra.domain.models.uuid_invalid', item=item))
        return list(dict.fromkeys(v))

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError(tr('extra.domain.models.titlul_nu_poate_fi_gol'))
        if len(v) > 300:
            raise ValueError(tr('extra.domain.models.titlul_este_prea_lung_max_300'))
        return v

    @field_validator("tags")
    @classmethod
    def _tags(cls, v: list[str]) -> list[str]:
        cleaned = [t.strip() for t in v if t and t.strip()]
        return list(dict.fromkeys(cleaned))

    @field_validator("estimated_minutes", "remaining_minutes")
    @classmethod
    def _minutes(cls, v: int | None) -> int | None:
        if v is not None and v < 0:
            raise ValueError(tr('extra.domain.models.durata_nu_poate_fi_negativa'))
        return v

    @model_validator(mode="after")
    def _kind_rules(self) -> "Node":
        if self.kind == Kind.FOLDER:
            forbidden = [
                self.status, self.estimated_minutes, self.remaining_minutes,
                self.due_date, self.due_at, self.waiting_reason,
            ]
            if any(x is not None for x in forbidden) or self.depends_on_ids:
                raise ValueError(tr('extra.domain.models.un_folder_nu_are_status_estimari_termen_sau_dependente'))
        elif self.kind == Kind.PROJECT:
            if self.estimated_minutes is not None or self.remaining_minutes is not None:
                raise ValueError(tr('extra.domain.models.estimarile_unui_proiect_sunt_agregate_nu_se_seteaza_direct'))
        if self.kind == Kind.TASK and self.status is None:
            raise ValueError(tr('extra.domain.models.un_task_are_nevoie_de_status'))
        if self.parent_id is not None and self.parent_id == self.id:
            raise ValueError(tr('extra.domain.models.un_nod_nu_poate_fi_propriul_parinte'))
        if self.continuation_of == self.id: raise ValueError(tr('extra.domain.models.o_cerinta_nu_poate_continua_propriul_task'))
        if self.continuation_of is not None and self.kind != Kind.TASK: raise ValueError(tr('extra.domain.models.numai_taskurile_pot_fi_cerinte_ulterioare'))
        if self.id in self.related_node_ids or self.id in self.depends_on_ids:
            raise ValueError(tr('extra.domain.models.un_nod_nu_poate_face_referire_la_sine'))
        return self

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES

    @property
    def is_task(self) -> bool:
        return self.kind == Kind.TASK


class WorkspaceMeta(_Base):
    schema_version: int = SCHEMA_VERSION
    id: str = Field(default_factory=new_id)
    name: str = "FocusDesk"
    created_at: UtcDateTime = Field(default_factory=utcnow)
    demo: bool = False


class NoteEntry(_Base):
    """Notita datata din jurnal; fisier `notes/<uuid>.json`."""

    schema_version: int = SCHEMA_VERSION
    id: str = Field(default_factory=new_id)
    node_id: str
    at: UtcDateTime = Field(default_factory=utcnow)
    kind: Literal["note", "progress", "action", "session"] = "note"
    text: str
    session_id: str | None = None
    minutes: int | None = None


class HistoryEvent(_Base):
    schema_version: int = SCHEMA_VERSION
    id: str = Field(default_factory=new_id)
    node_id: str | None = None
    at: UtcDateTime = Field(default_factory=utcnow)
    type: str
    data: dict = Field(default_factory=dict)
