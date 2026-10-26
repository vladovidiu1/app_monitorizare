"""Supraveghere neblocantă: spawn, timeout, crash, anulare și eliberare nativă."""

from __future__ import annotations

import multiprocessing as mp
import json
import queue
import threading
import time
from collections.abc import Callable
from multiprocessing.connection import Connection
from uuid import uuid4

from .protocol import MAX_MESSAGE, EngineSettings, Request, Response, Stop, encode
from .assistant_protocol import AssistantReply
from .mail_protocol import MailAnalysis


def worker_main(connection: Connection, settings_data: dict, *, backend_factory=None) -> None:
    """Entry point importabil pentru spawn; nu importă Tk, COM sau Workspace."""
    backend = None
    try:
        settings = EngineSettings.model_validate(settings_data)
        while True:
            data = connection.recv_bytes(MAX_MESSAGE)
            payload = json.loads(data)
            if not isinstance(payload, dict):
                raise ValueError("Mesaj IPC invalid.")
            if payload.get("kind") == "stop":
                Stop.model_validate(payload)
                return
            request = Request.model_validate(payload)
            try:
                if backend is None:
                    connection.send_bytes(encode(Response(request_id=request.request_id, kind="loading")))
                    if backend_factory is None:
                        from .runtime import LocalModel

                        backend_factory = LocalModel
                    backend = backend_factory(settings)
                proposal = backend.generate(request)
                if isinstance(proposal, MailAnalysis):
                    response = Response(request_id=request.request_id, kind="result", mail_analysis=proposal,
                        mail_body_chars=proposal._body_chars, mail_candidate_ids=proposal._candidate_ids, usage=proposal._usage)
                elif isinstance(proposal, AssistantReply):
                    response = Response(request_id=request.request_id, kind="result", assistant=proposal,
                                        context_keys=proposal._context_keys, usage=proposal._usage)
                else:
                    response = Response(request_id=request.request_id, kind="result", proposal=proposal)
                connection.send_bytes(encode(response))
            except Exception as exc:
                connection.send_bytes(encode(Response(
                    request_id=request.request_id, kind="error", error=(f"Analiza locală a mailului a eșuat ({type(exc).__name__}); corpul nu este inclus în diagnostic."
                    if request.action == "analyze_mail" else f"{type(exc).__name__}: {str(exc)[:1000]}"))))
    except (EOFError, OSError, ValueError):
        # Parent closed its end or the protocol was invalid. Never execute arbitrary messages.
        pass
    finally:
        try:
            if backend is not None:
                backend.close()
        finally:
            connection.close()


class EngineProcess:
    """Un singur request activ; un singur model încărcat per proces.

    Toate operațiile Pipe/join rulează în supervisor, niciodată în callback Tk.
    `post` este UiBridge.post în aplicație; callback-urile nu rulează în worker.
    Anularea/timeout-ul omoară procesul nativ (inclusiv în timpul încărcării).
    O cerere ulterioară pornește automat un proces nou.
    """

    def __init__(self, settings: EngineSettings, post: Callable, *, _target=worker_main) -> None:
        self.settings = settings.model_copy(deep=True)
        self._post = post
        self._target = _target
        self._ctx = mp.get_context("spawn")
        self._commands: queue.Queue = queue.Queue(maxsize=1)
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._closed = threading.Event()
        self._busy = False
        self._process = None
        self._connection = None
        self._thread = threading.Thread(target=self._run, name="focusdesk-ai-supervisor", daemon=True)
        self._thread.start()

    @property
    def busy(self) -> bool:
        with self._lock:
            return self._busy

    def submit(self, request: Request, on_message: Callable[[Response], None]) -> str:
        data = encode(request)
        with self._lock:
            if self._closed.is_set():
                raise RuntimeError("Motorul AI este închis.")
            if self._busy:
                raise RuntimeError("Motorul AI finalizează cererea precedentă. Reîncearcă în câteva momente.")
            self._busy = True
            self._cancel = threading.Event()
            self._commands.put_nowait((request, data, self._cancel, on_message))
        return request.request_id

    def cancel(self) -> None:
        self._cancel.set()

    def close(self) -> None:
        self._closed.set()
        self.cancel()

    def wait_closed(self, timeout: float = 3) -> bool:
        """Pentru teste/CLI; UI nu așteaptă finalizarea procesului."""
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def _start(self) -> None:
        if self._process is not None and self._process.is_alive():
            return
        self._stop()
        parent, child = self._ctx.Pipe(duplex=True)
        process = self._ctx.Process(target=self._target, args=(child, self.settings.model_dump()),
                                    name="FocusDesk-AI", daemon=True)
        try:
            process.start()
        except BaseException:
            parent.close()
            child.close()
            raise
        child.close()
        self._process, self._connection = process, parent

    def _stop(self, graceful: bool = False) -> None:
        connection, self._connection = self._connection, None
        process = self._process
        self._process = None
        if process is None:
            if connection:
                connection.close()
            return
        if graceful and process.is_alive() and connection:
            try:
                connection.send_bytes(encode(Stop(request_id=str(uuid4()))))
            except (OSError, EOFError):
                pass
            process.join(0.5)
        if process.is_alive():
            process.terminate()
        process.join(0.5)
        if process.is_alive():
            process.kill()
            process.join(0.5)
        if not process.is_alive():
            process.close()
        if connection:
            connection.close()

    def _deliver(self, response: Response, callback: Callable, cancelled: threading.Event) -> None:
        def deliver() -> None:
            if not cancelled.is_set() and not self._closed.is_set():
                callback(response)
        self._post(deliver)

    def _run(self) -> None:
        try:
            while not self._closed.is_set():
                try:
                    request, data, cancelled, callback = self._commands.get(timeout=0.05)
                except queue.Empty:
                    continue
                try:
                    deadline = time.monotonic() + self.settings.timeout
                    if cancelled.is_set() or self._closed.is_set():
                        continue
                    self._start()
                    # A child stuck during spawn must not trap the supervisor in a
                    # blocking Pipe write of a large prompt. Killing it unblocks this sender.
                    send_errors = queue.Queue()
                    connection = self._connection
                    def send(connection=connection, data=data, errors=send_errors):
                        try:
                            connection.send_bytes(data)
                        except (OSError, EOFError) as exc:
                            errors.put(exc)
                    sender = threading.Thread(target=send, name="focusdesk-ai-ipc", daemon=True)
                    sender.start()
                    while True:
                        if cancelled.is_set() or self._closed.is_set():
                            self._stop()
                            break
                        if time.monotonic() >= deadline:
                            raise TimeoutError("AI a depășit timpul alocat; procesul a fost oprit.")
                        if not send_errors.empty():
                            raise RuntimeError("Comunicarea cu procesul AI s-a întrerupt.") from send_errors.get_nowait()
                        if self._connection.poll(0.05):
                            response = Response.model_validate_json(self._connection.recv_bytes(MAX_MESSAGE))
                            if response.request_id != request.request_id:
                                raise ValueError("ID de cerere IPC incorect.")
                            if response.proposal and response.proposal.action != request.action:
                                raise ValueError("Operația propusă nu corespunde cererii.")
                            if response.kind == "result" and (request.action == "assistant") != (response.assistant is not None):
                                raise ValueError("Tip de răspuns IPC incorect.")
                            if response.kind == "result" and (request.action == "analyze_mail") != (response.mail_analysis is not None):
                                raise ValueError("Tip de răspuns mail IPC incorect.")
                            self._deliver(response, callback, cancelled)
                            if response.kind != "loading":
                                break
                        elif not self._process.is_alive():
                            raise RuntimeError(f"Procesul AI s-a închis neașteptat (cod {self._process.exitcode}).")
                except Exception as exc:
                    error = str(exc) or f"Procesul AI s-a închis fără răspuns ({type(exc).__name__})."
                    self._stop()
                    self._deliver(Response(request_id=request.request_id, kind="error", error=error[:1000]),
                                  callback, cancelled)
                finally:
                    with self._lock:
                        self._busy = False
        finally:
            self._stop(graceful=True)
