"""Configuratia aplicatiei (in afara workspace-ului): ultimul workspace, tema, geometrie."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .storage.atomic import atomic_write_json

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

    last_workspace: str | None = None
    recent_workspaces: list[str] = Field(default_factory=list)
    theme: str = "light"  # "light" | "dark"
    geometry: str | None = None
    show_inspector: bool = True
    show_archived: bool = False
    show_completed: bool = True
    last_view: str = 'today'
    inspector_tab: str = 'Detalii'

    @field_validator('last_view', mode='before')
    @classmethod
    def _navigation(cls, value):
        return value if value in ('today', 'tasks', 'calendar', 'activity') else 'tasks'

    @field_validator('inspector_tab', mode='before')
    @classmethod
    def _tab(cls, value):
        if not isinstance(value, str):
            return 'Detalii'
        aliases = {'Jurnal': 'Activitate', 'Subtask-uri': 'Subtaskuri'}
        value = aliases.get(value, value)
        return value if value in ('Detalii','Subtaskuri','Activitate','Fișiere','Planificare','Versiuni') else 'Detalii'

    sash_left: int | None = None
    sash_right: int | None = None
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
