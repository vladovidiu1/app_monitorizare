"""Thread dedicat pentru COM: CoInitialize/CoUninitialize, obiecte COM care nu parasesc thread-ul, timeout in UI.

Un apel COM blocat NU poate fi anulat fortat in siguranta: dupa timeout, rezultatul intarziat este ignorat si
noile cereri sunt refuzate pana cand apelul blocat se termina (sau pana la repornirea aplicatiei).
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Any, Callable, Protocol

log = logging.getLogger(__name__)


class Poster(Protocol):
    def post(self, fn: Callable[[], None]) -> None: ...

    def schedule(self, ms: int, fn: Callable[[], None]) -> None: ...


class ComTimeout(Exception):
    pass


class ComBlocked(Exception):
    pass


class ComTask:
    def __init__(self, fn: Callable[[Any], Any], name: str) -> None:
        self.fn = fn
        self.name = name
        self.finished = threading.Event()
        self.timed_out = False
        self.started = threading.Event()


class ComWorker:
    def __init__(self, poster: Poster, backend_factory: Callable[[], Any], *, use_com: bool = True) -> None:
        self._poster = poster
        self._factory = backend_factory
        self._use_com = use_com
        self._q: queue.Queue[ComTask | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._running: ComTask | None = None
        self._stopped = False

    # ---- state ------------------------------------------------------
    @property
    def blocked(self) -> bool:
        """Un apel anterior depasit ca timp inca ruleaza in thread-ul COM."""
        t = self._running
        return t is not None and t.timed_out and not t.finished.is_set()

    @property
    def busy(self) -> bool:
        return (self._running is not None and not self._running.finished.is_set()) or not self._q.empty()

    # ---- submit -----------------------------------------------------
    def submit(self, fn: Callable[[Any], Any], on_done: Callable[[Any], None],
               on_error: Callable[[BaseException], None], *, timeout_s: float = 30.0, name: str = "outlook") -> ComTask | None:
        """`fn(backend)` ruleaza in thread-ul COM; `on_done/on_error` pe thread-ul UI. Rezultatele trebuie sa fie primitive."""
        if self._stopped:
            on_error(ComBlocked("Worker-ul COM este oprit."))
            return None
        if self.blocked:
            on_error(ComBlocked("Un apel anterior către Outlook nu s-a terminat (posibil blocat de un dialog sau de "
                                "Outlook). Închide dialogurile din Outlook sau repornește Outlook/FocusDesk."))
            return None
        self._ensure_thread()
        task = ComTask(fn, name)

        def deliver_timeout() -> None:
            if task.finished.is_set() or task.timed_out:
                return
            task.timed_out = True
            on_error(ComTimeout(f"Outlook nu a răspuns în {int(timeout_s)} s. Apelul poate fi blocat; rezultatul "
                                "tardiv va fi ignorat."))

        task._on_done = on_done  # type: ignore[attr-defined]
        task._on_error = on_error  # type: ignore[attr-defined]
        self._poster.schedule(int(timeout_s * 1000), deliver_timeout)
        self._q.put(task)
        return task

    # ---- thread -----------------------------------------------------
    def _ensure_thread(self) -> None:
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._loop, name="focusdesk-com", daemon=True)
                self._thread.start()

    def _loop(self) -> None:
        pythoncom = None
        if self._use_com:
            try:
                import pythoncom  # type: ignore

                pythoncom.CoInitialize()
            except Exception:
                log.exception("CoInitialize a esuat")
                pythoncom = None
        backend = None
        try:
            while True:
                task = self._q.get()
                if task is None:
                    break
                if task.timed_out:
                    task.finished.set()
                    continue
                self._running = task
                task.started.set()
                try:
                    if backend is None:
                        backend = self._factory()
                    result = task.fn(backend)
                    err: BaseException | None = None
                except BaseException as exc:  # noqa: BLE001
                    result, err = None, exc
                    log.exception("Apel COM esuat (%s)", task.name)
                task.finished.set()
                if task.timed_out:
                    continue  # rezultat tardiv: ignorat
                on_done, on_error = task._on_done, task._on_error  # type: ignore[attr-defined]
                if err is not None:
                    self._poster.post(lambda e=err, cb=on_error, t=task: None if t.timed_out else cb(e))
                else:
                    self._poster.post(lambda r=result, cb=on_done, t=task: None if t.timed_out else cb(r))
        finally:
            backend = None
            if pythoncom is not None:
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

    def shutdown(self) -> None:
        self._stopped = True
        self._q.put(None)
