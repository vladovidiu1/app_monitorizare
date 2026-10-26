"""Smoke opțional: procesul real, modelul real, fără UI și fără workspace."""

import queue
import time
from pathlib import Path
from uuid import uuid4

from .process import EngineProcess
from .protocol import EngineSettings, Request


def run_smoke(path: Path, timeout: int = 300) -> dict:
    callbacks, results = queue.Queue(), []
    engine = EngineProcess(EngineSettings(model_path=str(path), timeout=timeout), callbacks.put)
    started = time.monotonic()
    report = {"status": "error", "error": "Test incomplet"}
    try:
        engine.submit(Request(request_id=str(uuid4()), action="add_note", instruction="Scrie o notiță foarte scurtă: Salut!",
                              context="Test real de inferență locală pe CPU."), results.append)
        while not results or results[-1].kind == "loading":
            callbacks.get(timeout=timeout + 5)()
        response = results[-1]
        if response.kind != "result":
            raise RuntimeError(response.error)
        report = {"status": "ok", "proposal": response.proposal.model_dump(),
                  "seconds": round(time.monotonic() - started, 2), "request_id": response.request_id}
    except Exception as exc:
        report = {"status": "error", "error": str(exc)}
    finally:
        engine.close()
        if not engine.wait_closed():
            report = {"status": "error", "error": "Procesul AI nu s-a oprit."}
    return report


def run_assistant_smoke(path: Path, mode: str = "answer", timeout: int = 300) -> dict:
    """Aceeași cale în surse și executabil: date temporare, niciodată aplicare automată."""
    import tempfile
    from ..domain.models import Kind
    from ..services.assistant_context import build_context
    from ..services.assistant_proposals import ProposalBatch
    from ..services.workspace import Workspace

    callbacks, messages = queue.Queue(), []
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="focusdesk-assistant-") as directory:
        ws = Workspace.open(Path(directory) / "data", create=True)
        engine = EngineProcess(EngineSettings(model_path=str(path), timeout=timeout), callbacks.put)
        report = {"status": "error", "error": "Test incomplet"}
        try:
            task = ws.create_node(Kind.TASK, "Validare raport", description="Verificarea datelor raportului.",
                                  next_action="Cere confirmarea solicitantului")
            ws.add_note(task.id, "Am verificat intrările. Aștept confirmarea solicitantului.")
            question = {"answer": "Unde am rămas? Rezumă foarte scurt, cu surse, fără propuneri de modificare.",
                "steps": "Propune un singur subtask concret pentru descrierea taskului selectat și un checklist scurt pentru el. Nu aplica nimic.",
                "email": "Pregătește un e-mail foarte scurt pentru clarificarea confirmării solicitate, cu surse. Nu trimite nimic."}[mode]
            intent = {"answer": "resume", "steps": "steps", "email": "email"}[mode]
            bundle = build_context(ws, "task", task.id, question)
            engine.submit(Request(request_id=str(uuid4()), action="assistant", intent=intent, instruction=question,
                                  context=bundle.wire()), messages.append)
            while not messages or messages[-1].kind == "loading":
                callbacks.get(timeout=timeout + 5)()
            response = messages[-1]
            if response.kind != "result":
                raise RuntimeError(response.error)
            ProposalBatch.prepare(ws, bundle, response.assistant, response.context_keys, intent)
            if mode == "steps" and not response.assistant.actions:
                raise RuntimeError("Nu s-au generat propuneri structurate.")
            if mode == "email" and not response.assistant.email:
                raise RuntimeError("Nu s-a generat ciorna structurată.")
            if response.usage["prompt_tokens"] + 1024 + 16 > 4096:
                raise RuntimeError("Bugetul de tokeni nu a fost respectat.")
            if len(ws.list_notes(task.id)) != 1 or len(ws.nodes) != 1:
                raise RuntimeError("Smoke-ul nu trebuie să aplice propuneri.")
            report = {"status": "ok", "mode": mode, "reply": response.assistant.model_dump(), "usage": response.usage,
                "sources_used": response.context_keys, "writes_applied": 0, "seconds": round(time.monotonic() - started, 2)}
        except Exception as exc:
            report = {"status": "error", "error": str(exc)}
        finally:
            engine.close()
            if not engine.wait_closed():
                report = {"status": "error", "error": "Procesul AI nu s-a oprit."}
            ws.close()
    return report
