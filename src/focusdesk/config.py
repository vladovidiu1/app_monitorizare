"""Configuratia aplicatiei (in afara workspace-ului): ultimul workspace, tema, geometrie."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .storage.atomic import atomic_write_json
from .domain.mail import MailSettings

log = logging.getLogger(__name__)


def app_data_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "FocusDesk"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_path(relative: str) -> Path:
    """Cale catre resurse incluse in pachet sau in build-ul PyInstaller."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "focusdesk" / "resources" / relative
    return Path(__file__).parent / "resources" / relative


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    mail: MailSettings = Field(default_factory=MailSettings)

    language: str = "ro"

    @field_validator("language", mode="before")
    @classmethod
    def _language(cls, value):
        return value if value in ("ro", "en", "de", "fr", "es") else "ro"

    last_workspace: str | None = None
    recent_workspaces: list[str] = Field(default_factory=list)
    theme: str = "light"  # "light" | "dark"
    geometry: str | None = None
    show_inspector: bool = True
    show_archived: bool = False
    show_completed: bool = False
    last_view: str = 'today'
    inspector_tab: str = 'details'

    @field_validator('last_view', mode='before')
    @classmethod
    def _navigation(cls, value):
        return value if value in ('today', 'tasks', 'calendar', 'activity') else 'tasks'

    @field_validator('inspector_tab', mode='before')
    @classmethod
    def _tab(cls, value):
        aliases = {'Detalii':'details','Subtaskuri':'subtasks','Subtask-uri':'subtasks',
                   'Activitate':'journal','Jurnal':'journal','Fișiere':'files',
                   'Planificare':'planning','Versiuni':'versions'}
        value = aliases.get(value, value) if isinstance(value,str) else 'details'
        return value if value in ('details','subtasks','journal','files','planning','versions') else 'details'

    sash_left: int | None = None
    sash_right: int | None = None
    long_session_minutes: int = Field(default=240, ge=0)
    session_open: dict[str, bool] = Field(default_factory=dict)

    @classmethod
    def path(cls) -> Path:
        return app_data_dir() / "app.json"

    @classmethod
    def load(cls) -> "AppConfig":
        try:
            return cls.model_validate(json.loads(cls.path().read_text("utf-8")))
        except (OSError, ValueError):
            return cls()

    def save(self) -> None:
        try:
            atomic_write_json(self.path(), self.model_dump(mode="json"), keep_backup=False)
        except Exception:
            log.exception("Configurația aplicației nu a putut fi salvată")

    def remember_workspace(self, path: Path) -> None:
        p = str(path)
        self.last_workspace = p
        self.recent_workspaces = [p, *[r for r in self.recent_workspaces if r != p]][:8]
