"""Timer global unic pentru sesiuni de lucru.

Durata activa se aduna din tick-uri masurate cu ceas monoton. Un interval mare intre tick-uri
(suspendare Windows, UI blocat) nu este numarat ca munca: apare ca `pending_gap` si cere reconciliere.
Timpul planificat nu este timp lucrat; doar `actual_seconds` conteaza.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid5
from datetime import timedelta
from typing import Callable, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..domain.common import UtcDateTime, fmt_utc, new_id, utcnow
from ..domain.models import Kind, Status, CLOSED_STATUSES, NoteEntry, HistoryEvent
from ..domain.session import SessionRecord
from ..errors import NotFoundError, ValidationError, ExternalModificationError, StorageError
from ..storage.atomic import atomic_write_json, read_json, sha256_file
from .workspace import Workspace

log = logging.getLogger(__name__)

GAP_THRESHOLD_SECONDS = 20.0
PERSIST_EVERY_SECONDS = 20.0


class TimerState(BaseModel):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)
    session_id: str
    node_id: str
    state: Literal["running","paused"] = "running"  # running | paused
    accumulated_seconds: float = Field(default=0.0, ge=0)
    started_at: UtcDateTime = Field(default_factory=utcnow)
    heartbeat_at: UtcDateTime = Field(default_factory=utcnow)
    gaps: list[dict] = Field(default_factory=list)
    session_draft: dict | None = None
    session_before: dict | None = None
    finalization: dict | None = None


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
        self.recovery_error = None
        self._digest = None
        self._last_stopped = None
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
        if self.state and self.state.finalization:return float(self.state.finalization['seconds'])
        return self.state.accumulated_seconds if self.state else 0.0

    # ---- persistence ------------------------------------------------
    def _load_existing(self) -> None:
        if not self.path.exists():
            return
        try:
            data, self._digest, _ = read_json(self.path)
            st = TimerState.model_validate(data)
        except Exception as exc:
            self.recovery_error='Fișierul timerului este nevalid: '+str(exc)
            log.warning("timer.json invalid: %s", exc)
            return
        self.state=st
        node=self.ws.nodes.get(st.node_id)
        self.recovered=Recovered(st,node.title if node else 'Task indisponibil')
        try:
            if st.session_draft and not self.ws.read_only:self._ensure_start()
            session=self.ws.repo.sessions.get(st.session_id)
            if session.status!='active' and st.finalization is None and not st.session_draft:
                if not self.ws.read_only:self._clear_file()
                self.state=None;self.recovered=None
        except Exception as exc:
            self.recovery_error=str(exc)
            log.warning('Timer de recuperat: %s',exc)

    def _ensure_start(self):
        st=self.state
        if not st or not st.session_draft:return
        self.ws.repo._require_writable()
        draft=SessionRecord.model_validate(st.session_draft)
        if draft.id!=st.session_id or draft.node_id!=st.node_id:
            raise ValidationError('Planul timerului nu corespunde sesiunii. Verifică fișierul salvat.')
        try:current=self.ws.repo.sessions.get(st.session_id)
        except NotFoundError:current=None
        if current is None:self.ws.repo.sessions.save(draft)
        elif current.status=='planned' and current.model_dump(mode='json')==st.session_before:
            self.ws.repo.sessions.save(draft)
        elif current.status!='active' or current.started_actual_at!=st.started_at:
            raise ExternalModificationError('Sesiunea a fost modificată după pornirea întreruptă. Nu o suprascriu.')
        st.session_draft=None;st.session_before=None
        self.recovery_error=None

    def _persist(self) -> None:
        if self.state is None or self.ws.read_only:
            return
        self.ws.repo._require_writable()
        if self.path.exists() and self._digest != sha256_file(self.path):
            raise ExternalModificationError('Timerul a fost modificat extern. Reîncarcă workspace-ul.')
        if self._digest is not None and not self.path.exists():
            raise ExternalModificationError('Fișierul timerului a fost eliminat extern.')
        candidate = self.state.model_copy(deep=True)
        candidate.heartbeat_at = utcnow()
        atomic_write_json(self.path, candidate.model_dump(mode="json"), keep_backup=False)
        self._digest = sha256_file(self.path)
        self.state.heartbeat_at = candidate.heartbeat_at
        self._last_persist = self._mono()

    def _clear_file(self) -> None:
        try:
            self.ws.repo._require_writable()
            if self.path.exists() and self._digest != sha256_file(self.path):
                raise ExternalModificationError('Timer modificat extern; nu îl șterg.')
            self.path.unlink(missing_ok=True)
            self._digest = None
        except OSError as exc:
            raise StorageError('Timerul nu a putut fi închis pe disc. Reia salvarea.') from exc

    # ---- control ----------------------------------------------------
    def start(self, node_id: str, planned_session_id: str | None = None) -> SessionRecord:
        self.ws.repo._require_writable()
        if self.state is not None:
            if self.active and not self.state.finalization and self.state.node_id == node_id and (planned_session_id is None or planned_session_id == self.state.session_id):
                return self.ws.repo.sessions.get(self.state.session_id)
            raise ValidationError("Există deja o sesiune curentă, inclusiv în pauză. Încheie-o înainte să începi alta.")
        if self.path.exists():
            raise ValidationError('Există un timer salvat de recuperat. Reîncarcă workspace-ul.')
        node = self.ws.get(node_id)
        if node.kind != Kind.TASK:
            raise ValidationError("Sesiunile se pornesc doar pentru task-uri.")
        if node.status in CLOSED_STATUSES:
            raise ValidationError('Redeschide taskul înainte de a începe lucrul.')
        now = utcnow()
        session_before=None
        blockers = self.ws.unfinished_dependencies(node_id)
        if blockers:
            log.info("Task cu dependente nefinalizate pornit explicit: %s", [b.title for b in blockers])
        if planned_session_id:
            session = self.ws.repo.sessions.get(planned_session_id)
            if session.node_id != node_id:
                raise ValidationError("Sesiunea planificată aparține altui task.")
            if session.status != 'planned':
                raise ValidationError('Poate fi pornită doar o rezervare programată, o singură dată.')
            session_before=session.model_dump(mode='json')
            session.status = "active"
        else:
            session = SessionRecord(node_id=node_id, workspace_id=self.ws.id, start_at=now,
                                    end_at=now + timedelta(minutes=1), origin="timer", status="active",
                                    tz=self.ws.settings.timezone)
        session.started_actual_at = now
        self.state = TimerState(session_id=session.id, node_id=node_id, started_at=now,
                                session_draft=session.model_dump(mode='json'),session_before=session_before)
        self._last_tick = self._mono()
        self.pending_gap = 0.0
        try:
            self._persist()  # durable start intent precedes the session write
        except Exception:
            self.state = None; self._last_tick = None
            raise
        try:
            self.ws.repo.sessions.save(session)
        except Exception:
            self.recovered = Recovered(self.state, node.title)
            raise
        self.state.session_draft=None;self.state.session_before=None
        try:self._persist()
        except Exception:
            self.recovered=Recovered(self.state,node.title)
            raise
        self._last_stopped = None
        if node.status in (Status.TODO, Status.INBOX):
            try:
                self.ws.update_node(node_id, status=Status.IN_PROGRESS)
            except Exception:
                log.exception("Statusul task-ului nu a putut fi actualizat la pornirea sesiunii")
        self.ws.emit("timer_changed")
        return session

    def tick(self) -> float:
        """Apelat periodic din UI. Intoarce secundele active acumulate."""
        if self.state is None or self.recovered is not None or self.state.finalization is not None:
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
                self.state.accumulated_seconds += max(0,delta)
        self._last_tick = now
        if now - self._last_persist >= PERSIST_EVERY_SECONDS and self.state is not None:
            self._persist()
        return self.seconds

    def pause(self) -> None:
        self.ws.repo._require_writable()
        if self.recovered or (self.state and self.state.finalization): return
        if self.state is None or self.state.state != "running":
            return
        self.tick()
        before = self.state.model_copy(deep=True)
        if self.state.state == "running":
            self.state.state = "paused"
        try: self._persist()
        except Exception:
            self.state = before
            raise
        self.ws.emit("timer_changed")

    def resume(self, *, count_gap_seconds: float = 0.0) -> None:
        """Continua; timpul din pauza/suspendare NU se adauga, decat daca utilizatorul il confirma explicit."""
        self.ws.repo._require_writable()
        if self.recovered or (self.state and self.state.finalization): return
        if self.state is None or self.state.state != "paused":
            return
        before=self.state.model_copy(deep=True);gap=self.pending_gap
        if count_gap_seconds > 0:
            self.state.accumulated_seconds += min(count_gap_seconds, self.pending_gap or count_gap_seconds)
        self.pending_gap = 0.0
        self.state.state = "running"
        self._last_tick = self._mono()
        try: self._persist()
        except Exception:
            self.state=before;self.pending_gap=gap
            raise
        self.ws.emit("timer_changed")

    def add_manual_seconds(self, seconds: float) -> None:
        self.ws.repo._require_writable()
        if self.recovered or (self.state and self.state.finalization):return
        if self.state is not None and seconds > 0:
            before=self.state.accumulated_seconds
            self.state.accumulated_seconds += seconds
            try:self._persist()
            except Exception:
                self.state.accumulated_seconds=before
                raise

    def stop(self, *, summary="", next_action=None, remaining_minutes=None,
             keep_remaining=True, new_status=None, stopped_at=None):
        self.ws.repo._require_writable()
        if self.state is None:
            if self._last_stopped is not None: return self._last_stopped.model_copy(deep=True)
            raise ValidationError('Nu există o sesiune curentă.')
        st=self.state
        if st.finalization is None:
            self.tick()
            now=stopped_at or utcnow()
            if now < st.started_at or now > utcnow():
                raise ValidationError('Ora încheierii trebuie să fie între început și momentul curent.')
            seconds=int(st.accumulated_seconds)
            if seconds > (now-st.started_at).total_seconds():
                # Explicit recovered end caps saved work to the selected wall interval.
                if stopped_at is not None: seconds=max(0,int((now-st.started_at).total_seconds()))
            self._ensure_start()
            previous=self.ws.repo.sessions.get(st.session_id)
            base={key:previous.model_dump(mode='json')[key] for key in ('status','actual_seconds','started_actual_at','stopped_actual_at','summary')}
            st.finalization=dict(base=base,at=now.isoformat(),seconds=seconds,summary=summary.strip(),
                next_action=next_action,remaining_minutes=remaining_minutes,keep_remaining=keep_remaining,
                new_status=new_status.value if new_status is not None else None)
            st.state='paused'
            try: self._persist()
            except Exception:
                st.finalization=None
                raise
        plan=st.finalization;now=datetime.fromisoformat(plan['at'])
        self._ensure_start()
        session=self.ws.repo.sessions.get(st.session_id)
        current={key:session.model_dump(mode='json')[key] for key in ('status','actual_seconds','started_actual_at','stopped_actual_at','summary')}
        # JSON UTC timestamps may serialize as Z instead of +00:00; compare instants below.
        matches_done=(session.status=='done' and session.actual_seconds==plan['seconds'] and session.stopped_actual_at==now
                      and session.summary==(plan['summary'] or None) and session.started_actual_at==st.started_at)
        if plan.get('base') is not None and current!=plan['base'] and not matches_done:
            raise ExternalModificationError('Timpul sau starea sesiunii au fost modificate extern. Nu suprascriu corecția.')
        session.status='done';session.actual_seconds=plan['seconds'];session.stopped_actual_at=now
        if session.origin=='timer':session.end_at=max(now,session.start_at+timedelta(minutes=1))
        session.summary=plan['summary'] or None
        self.ws.repo.sessions.save(session)
        if st.node_id in self.ws.nodes:
            changes={}
            if plan['next_action'] is not None:changes['next_action']=plan['next_action'].strip() or None
            if not plan['keep_remaining']:changes['remaining_minutes']=plan['remaining_minutes']
            if plan['new_status'] is not None:changes['status']=Status(plan['new_status'])
            if changes:self.ws.update_node(st.node_id,**changes)
            if plan['summary']:
                store=self.ws.repo.notes_store(st.node_id);nid=str(uuid5(UUID(st.session_id),'summary'))
                if nid not in store.ids():
                    store.save(NoteEntry(id=nid,node_id=st.node_id,at=now,kind='session',text=plan['summary'],session_id=st.session_id))
        eid=str(uuid5(UUID(st.session_id),'stopped'))
        if eid not in self.ws.repo.history.ids():
            self.ws.repo.history.save(HistoryEvent(id=eid,node_id=st.node_id,at=now,type='session_stopped',
                data=dict(session_id=session.id,seconds=session.actual_seconds)))
        self._clear_file()
        self._last_stopped=session.model_copy(deep=True)
        self.state=None;self.recovered=None;self._last_tick=None;self.pending_gap=0.0
        self.ws.emit('timer_changed');self.ws.emit('session_finished',node_id=session.node_id,session_id=session.id)
        return session

    def recover_session(self,session_id):
        """Explicitly adopt an orphan active record, never infer elapsed work."""
        self.ws.repo._require_writable()
        if self.state or self.path.exists():raise ValidationError('Rezolvă mai întâi timerul curent.')
        session=self.ws.repo.sessions.get(session_id)
        if session.status!='active':raise ValidationError('Selectează o înregistrare activă fără timer.')
        self.state=TimerState(session_id=session.id,node_id=session.node_id,state='paused',
            accumulated_seconds=session.actual_seconds,started_at=session.started_actual_at or session.start_at)
        try:self._persist()
        except Exception:
            self.state=None
            raise
        node=self.ws.nodes.get(session.node_id)
        self.recovered=Recovered(self.state,node.title if node else 'Task indisponibil')
        self.ws.emit('timer_changed')

    def continue_recovered(self):
        self.ws.repo._require_writable()
        if not self.recovered or not self.state:return
        if self.state.finalization:
            self.stop();return
        self.ws.get(self.state.node_id)
        self._ensure_start()
        # Offline time is never added, regardless of the last saved running state.
        self.state.state='paused'
        self._persist()
        self.recovered=None
        self.resume()

    def discard(self) -> None:
        """Renunta la sesiune fara timp inregistrat (sesiunea ad-hoc se anuleaza)."""
        self.ws.repo._require_writable()
        if self.state is None:
            return
        if self.state.finalization:
            raise ValidationError('Încheierea a început deja. Reia salvarea, fără a elimina timpul salvat.')
        try:
            session = self.ws.repo.sessions.get(self.state.session_id)
            session.status = "cancelled" if session.origin == "timer" else "planned"
            self.ws.repo.sessions.save(session)
        except NotFoundError:
            pass
        self._clear_file()
        self.state = None
        self.recovered = None
        self.ws.emit("timer_changed")

    # ---- recuperare dupa crash --------------------------------------
    def finalize_recovered(self, seconds: float, summary: str = "", *, stopped_at=None) -> SessionRecord | None:
        """Inchide sesiunea ramasa dupa un crash cu durata aleasa de utilizator (implicit, cea salvata)."""
        if self.state is None or self.recovered is None:
            return None
        self.ws.repo._require_writable()
        before=self.state.model_copy(deep=True);rec=self.recovered
        self.state.accumulated_seconds=max(0.0,seconds);self.state.state='paused'
        try:
            result=self.stop(summary=summary,stopped_at=stopped_at)
            return result
        except Exception:
            if not self.state.finalization:self.state=before
            self.recovered=rec
            raise
