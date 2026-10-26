"""Executa lucrari lungi in thread-uri si livreaza rezultatul pe thread-ul Tk prin root.after."""

from __future__ import annotations

import logging
import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

log = logging.getLogger(__name__)


class Cancelled(Exception):
    pass


class CancelToken:
    """Anulare cooperativa: lucrul trebuie sa verifice periodic `check()`."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def check(self) -> None:
        if self._event.is_set():
            raise Cancelled()


class Job:
    def __init__(self, name: str) -> None:
        self.name = name
        self.token = CancelToken()
        self.done = False

    def cancel(self) -> None:
        self.token.cancel()


class UiBridge:
    """Nicio actualizare Tk din thread-uri secundare: rezultatele trec printr-o coada golita de `after`."""

    def __init__(self, root: Any, poll_ms: int = 80, max_workers: int = 4) -> None:
        self._root = root
        self._poll_ms = poll_ms
        self._q: queue.Queue[Callable[[], None]] = queue.Queue()
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="focusdesk")
        self._closed = False
        self._after_id: str | None = None
        self._poll()

    def post(self, fn: Callable[[], None]) -> None:
        """Poate fi apelata din orice thread."""
        if not self._closed:
            self._q.put(fn)

    def schedule(self, ms: int, fn: Callable[[], None]) -> None:
        """Programeaza `fn` pe thread-ul UI; apelata doar din thread-ul UI."""
        if not self._closed:
            self._root.after(ms, fn)

    def submit(self, work: Callable[[CancelToken], Any], on_done: Callable[[Any], None] | None = None,
               on_error: Callable[[BaseException], None] | None = None, name: str = "job") -> Job:
        job = Job(name)

        def run() -> None:
            try:
                result = work(job.token)
            except Cancelled:
                self.post(lambda: setattr(job, "done", True))
                return
            except BaseException as exc:  # noqa: BLE001 - raportat catre UI
                log.exception("Job %s a esuat", name)

                def fail(exc=exc) -> None:
                    job.done = True
                    if job.token.cancelled:
                        return
                    if on_error:
                        on_error(exc)
                self.post(fail)
                return

            def ok() -> None:
                job.done = True
                # Un rezultat sosit dupa anulare nu se mai aplica.
                if job.token.cancelled:
                    return
                if on_done:
                    on_done(result)
            self.post(ok)

        self._pool.submit(run)
        return job

    def _poll(self) -> None:
        if self._closed:
            return
        try:
            while True:
                fn = self._q.get_nowait()
                try:
                    fn()
                except Exception:
                    log.exception("Eroare in callback UI")
        except queue.Empty:
            pass
        try:
            self._after_id = self._root.after(self._poll_ms, self._poll)
        except Exception:
            self._closed = True

    def close(self) -> None:
        self._closed = True
        if self._after_id:
            try:
                self._root.after_cancel(self._after_id)
            except Exception:
                pass
        self._pool.shutdown(wait=False, cancel_futures=True)
