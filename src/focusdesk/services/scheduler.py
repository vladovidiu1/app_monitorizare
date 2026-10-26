"""Checkpoint programat: functioneaza doar cat timp aplicatia ruleaza; la repornire raporteaza ora ratata."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from ..domain.settings import Settings
from ..storage.atomic import atomic_write_json, read_json
from .files import FileService
from .workspace import Workspace

log = logging.getLogger(__name__)
LATE_AFTER_MINUTES = 5


@dataclass
class ScheduleDecision:
    run: bool
    missed: bool = False
    note: str | None = None


class CheckpointScheduler:
    def __init__(self, ws: Workspace) -> None:
        self.ws = ws
        self.files = FileService(ws)

    @property
    def path(self):
        return self.ws.repo.system_dir / "scheduler.json"

    def last_run_date(self) -> date | None:
        try:
            data, _, _ = read_json(self.path)
            return date.fromisoformat(data["last_daily_run"])
        except Exception:
            return None

    def mark_ran(self, day: date) -> None:
        if self.ws.read_only:
            return
        atomic_write_json(self.path, {"last_daily_run": day.isoformat()}, keep_backup=False)

    def decide(self, now_local: datetime, settings: Settings | None = None) -> ScheduleDecision:
        cfg = (settings or self.ws.settings).checkpoints
        if not cfg.enabled_daily:
            return ScheduleDecision(False)
        h, m = cfg.daily_time.split(":")
        scheduled = datetime.combine(now_local.date(), time(int(h), int(m)), tzinfo=now_local.tzinfo)
        if now_local < scheduled or self.last_run_date() == now_local.date():
            return ScheduleDecision(False)
        late = now_local - scheduled > timedelta(minutes=LATE_AFTER_MINUTES)
        note = None
        if late:
            note = (f"Ora programată {cfg.daily_time} a fost ratată (aplicația era oprită sau în repaus); "
                    f"checkpoint creat la {now_local:%H:%M} cu starea curentă. Starea istorică din momentul "
                    "în care aplicația era închisă nu poate fi reconstruită.")
        return ScheduleDecision(True, late, note)

    def sources(self) -> list[str]:
        """Un nod pe sursa unica: mai multe task-uri care mostenesc acelasi folder declanseaza o singura data."""
        seen: dict[str, str] = {}
        for node in self.ws.nodes.values():
            if node.source_workspace is None:
                continue
            try:
                src = self.files.effective_source(node.id)
            except Exception:
                continue
            if src is None or not src.path.is_dir():
                continue
            key = os.path.normcase(str(src.path))
            seen.setdefault(key, src.owner_id)
        return list(seen.values())
