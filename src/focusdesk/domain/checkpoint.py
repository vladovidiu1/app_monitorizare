"""Manifest de checkpoint (versiune de cod)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .common import UtcDateTime, new_id, utcnow
from .models import SCHEMA_VERSION


class CheckpointFile(BaseModel):
    model_config = ConfigDict(extra="allow")

    path: str  # relativ la radacina sursei, separator "/"
    size: int
    sha256: str
    mtime_ns: int = 0


class CheckpointManifest(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: int = SCHEMA_VERSION
    id: str = Field(default_factory=new_id)
    node_id: str
    owner_node_id: str
    project_id: str | None = None
    session_id: str | None = None
    created_at: UtcDateTime = Field(default_factory=utcnow)
    description: str = ""
    trigger: Literal["manual", "session_end", "scheduled", "pre_restore", "startup"] = "manual"
    source_root: str
    complete: bool = True
    files: list[CheckpointFile] = Field(default_factory=list)
    total_size: int = 0
    excluded_count: int = 0
    skipped_large: list[str] = Field(default_factory=list)
    archive: str = ""  # numele fisierului zip din snapshots/
    scheduled_missed: str | None = None

    def signature(self) -> frozenset[tuple[str, str]]:
        return frozenset((f.path, f.sha256) for f in self.files)
