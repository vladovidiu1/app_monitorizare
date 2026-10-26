"""Timer global unic pentru sesiuni de lucru.

Durata activa se aduna din tick-uri masurate cu ceas monoton. Un interval mare intre tick-uri
(suspendare Windows, UI blocat) nu este numarat ca munca: apare ca `pending_gap` si cere reconciliere.
Timpul planificat nu este timp lucrat; doar `actual_seconds` conteaza.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import timedelta
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field

from ..domain.common import UtcDateTime, fmt_utc, new_id, utcnow
from ..domain.models import Kind, Status
from ..domain.session import SessionRecord
from ..errors import NotFoundError, ValidationError
from ..storage.atomic import atomic_write_json, read_json
from .workspace import Workspace

log = logging.getLogger(__name__)

GAP_THRESHOLD_SECONDS = 20.0
PERSIST_EVERY_SECONDS = 20.0


class TimerState(BaseModel):
    model_config = ConfigDict(extra="allow")
    session_id: str
    node_id: str
    state: str = "running"  # running | paused
    accumulated_seconds: float = 0.0
    started_at: UtcDateTime = Field(default_factory=utcnow)
    heartbeat_at: UtcDateTime = Field(default_factory=utcnow)
    gaps: list[dict] = Field(default_factory=list)


@dataclass
class Recovered:
    state: TimerState
    node_title: str


class TimerService:
    def __init__(self, ws: Workspace, *, mono: Callable[[], float] = time.monotonic) -> None:
        self.ws = ws
        self._mono = mono
        self.state: TimerState | None = None
        self._last_tick: float | None = None
        self._last_persist: float = 0.0
        self.pending_gap: float = 0.0
        self.recovered: Recovered | None = None
        self._load_existing()

    @property
    def path(self):
        return self.ws.repo.system_dir / "timer.json"

    # ---- queries ----------------------------------------------------
    @property
    def active(self) -> bool:
        return self.state is not None and self.recovered is None

    @property
    def running(self) -> bool:
        return self.active and self.state.state == "running"  # type: ignore[union-attr]

    @property
    def node_id(self) -> str | None:
        return self.state.node_id if self.state else None

    @property
    def seconds(self) -> float:
        return self.state.accumulated_seconds if self.state else 0.0

    # ---- persistence ------------------------------------------------
    def _load_existing(self) -> None:
        if not self.path.exists():
            return
        try:
            data, _, _ = read_json(self.path)
            st = TimerState.model_validate(data)
        except Exception as exc:
            log.warning("timer.json invalid: %s", exc)
            return
        node = self.ws.nodes.get(st.node_id)
        self.state = st
        self.recovered = Recovered(st, node.title if node else "(nod inexistent)")

    def _persist(self) -> None:
        if self.state is None or self.ws.read_only:
            return
        self.state.heartbeat_at = utcnow()
        atomic_write_json(self.path, self.state.model_dump(mode="json"), keep_backup=False)
        self._last_persist = self._mono()

    def _clear_file(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            log.warning("timer.json nu a putut fi sters")

    # ---- control ----------------------------------------------------
    def start(self, node_id: str, planned_session_id: str | None = None) -> SessionRecord:
        self.ws.repo._require_writable()
        if self.state is not None:
            raise ValidationError("Există deja o sesiune activă. Oprește-o înainte să începi alta.")
        node = self.ws.get(node_id)
        if node.kind != Kind.TASK:
            raise ValidationError("Sesiunile se pornesc doar pentru task-uri.")
        now = utcnow()
        blockers = self.ws.unfinished_dependencies(node_id)
        if blockers:
            log.info("Task cu dependente nefinalizate pornit explicit: %s", [b.title for b in blockers])
        if planned_session_id:
            session = self.ws.repo.sessions.get(planned_session_id)
            if session.node_id != node_id:
                raise ValidationError("Sesiunea planificată aparține altui task.")
            session.status = "active"
        else:
            session = SessionRecord(node_id=node_id, workspace_id=self.ws.id, start_at=now,
                                    end_at=now + timedelta(minutes=1), origin="timer", status="active",
                                    tz=self.ws.settings.timezone)
        session.started_actual_at = now
        self.ws.repo.sessions.save(session)
        self.state = TimerState(session_id=session.id, node_id=node_id, started_at=now)
        self._last_tick = self._mono()
        self.pending_gap = 0.0
        self._persist()
        if node.status in (Status.TODO, Status.INBOX):
            try:
                self.ws.update_node(node_id, status=Status.IN_PROGRESS)
            except Exception:
                log.exception("Statusul task-ului nu a putut fi actualizat la pornirea sesiunii")
        self.ws.emit("timer_changed")
        return session

    def tick(self) -> float:
        """Apelat periodic din UI. Intoarce secundele active acumulate."""
        if self.state is None or self.recovered is not None:
            return self.seconds
        now = self._mono()
        if self.state.state == "running" and self._last_tick is not None:
            delta = now - self._last_tick
            if delta > GAP_THRESHOLD_SECONDS:
                self.pending_gap += delta
                self.state.gaps.append({"seconds": round(delta), "at": fmt_utc(utcnow())})
                self.state.state = "paused"
                self._persist()
                self.ws.emit("timer_gap", seconds=delta)
            else:
                self.state.accumulated_seconds += delta
        self._last_tick = now
        if now - self._last_persist >= PERSIST_EVERY_SECONDS and self.state is not None:
            self._persist()
        return self.seconds

    def pause(self) -> None:
        if self.state is None or self.state.state != "running":
            return
        self.tick()
        if self.state.state == "running":
            self.state.state = "paused"
        self._persist()
        self.ws.emit("timer_changed")

    def resume(self, *, count_gap_seconds: float = 0.0) -> None:
        """Continua; timpul din pauza/suspendare NU se adauga, decat daca utilizatorul il confirma explicit."""
        if self.state is None or self.state.state != "paused":
            return
        if count_gap_seconds > 0:
            self.state.accumulated_seconds += min(count_gap_seconds, self.pending_gap or count_gap_seconds)
        self.pending_gap = 0.0
        self.state.state = "running"
        self._last_tick = self._mono()
        self._persist()
        self.ws.emit("timer_changed")

    def add_manual_seconds(self, seconds: float) -> None:
        if self.state is not None and seconds > 0:
            self.state.accumulated_seconds += seconds
            self._persist()

    def stop(self, *, summary: str = "", next_action: str | None = None, remaining_minutes: int | None = None,
             keep_remaining: bool = True, new_status: Status | None = None) -> SessionRecord:
        if self.state is None:
            raise ValidationError("Nu există o sesiune activă.")
        self.tick()
        st = self.state
        now = utcnow()
        session = self.ws.repo.sessions.get(st.session_id)
        session.status = "done"
        session.actual_seconds = int(st.accumulated_seconds)
        session.stopped_actual_at = now
        if session.origin == "timer":
            session.end_at = max(now, session.start_at + timedelta(minutes=1))
        session.summary = summary.strip() or None
        self.ws.repo.sessions.save(session)
        node_id = st.node_id
        if node_id in self.ws.nodes:
            changes: dict = {}
            if next_action is not None:
                changes["next_action"] = next_action.strip() or None
            if not keep_remaining:
                changes["remaining_minutes"] = remaining_minutes
            if new_status is not None:
                changes["status"] = new_status
            if changes:
                self.ws.update_node(node_id, **changes)
            if summary.strip():
                self.ws.add_note(node_id, summary, "session", session_id=session.id)
        self.ws.record_event("session_stopped", node_id, {"session_id": session.id, "seconds": session.actual_seconds})
        self.state = None
        self._last_tick = None
        self.pending_gap = 0.0
        self._clear_file()
        self.ws.emit("timer_changed")
        self.ws.emit("session_finished", node_id=node_id, session_id=session.id)
        return session

    def discard(self) -> None:
        """Renunta la sesiune fara timp inregistrat (sesiunea ad-hoc se anuleaza)."""
        if self.state is None:
            return
        try:
            session = self.ws.repo.sessions.get(self.state.session_id)
            session.status = "cancelled" if session.origin == "timer" else "planned"
            self.ws.repo.sessions.save(session)
        except NotFoundError:
            pass
        self.state = None
        self.recovered = None
        self._clear_file()
        self.ws.emit("timer_changed")

    # ---- recuperare dupa crash --------------------------------------
    def finalize_recovered(self, seconds: float, summary: str = "") -> SessionRecord | None:
        """Inchide sesiunea ramasa dupa un crash cu durata aleasa de utilizator (implicit, cea salvata)."""
        if self.state is None or self.recovered is None:
            return None
        self.state.accumulated_seconds = max(0.0, seconds)
        self.recovered = None
        self.state.state = "paused"
        return self.stop(summary=summary)
