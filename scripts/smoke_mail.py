"""Smoke opțional: transport Outlook FALS prin ComWorker + model GGUF REAL; fără aplicare."""

import json
import multiprocessing
from pathlib import Path
import queue
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


class Poster:
    def __init__(self):
        self.queue = queue.Queue()
    def post(self, callback):
        self.queue.put(callback)
    def schedule(self, ms, callback):
        timer = threading.Timer(ms / 1000, lambda: self.post(callback))
        timer.daemon = True
        timer.start()


def main():
    from focusdesk.ai.models import default_model_path
    from focusdesk.ai.process import EngineProcess
    from focusdesk.ai.protocol import EngineSettings, Request
    from focusdesk.domain.settings import MailMonitorSettings
    from focusdesk.integrations.mail_fake import FakeMailBackend
    from focusdesk.services.mail_monitor import MailMonitorService
    from focusdesk.services.mail_analysis import build_mail_context, project_analysis
    from focusdesk.services.workspace import Workspace
    from focusdesk.workers.com_worker import ComWorker

    now = datetime.now(timezone.utc)
    stamp = (now - timedelta(minutes=1)).isoformat()
    data = {"header": {"store_id": "fake", "folder_id": "inbox", "entry_id": "entry", "internet_id": "<smoke@example.org>",
        "search_key": "key", "conversation_id": "thread", "subject": "Verificare raport", "sender_name": "Ana Test",
        "sender_smtp": "ana@example.org", "sent_at": stamp, "received_at": stamp, "modified_at": stamp},
        "body": "Te rog verifică raportul până mâine.", "attachments": [{"filename": "raport.xlsx", "size": 123, "type": 1}]}
    poster = Poster()
    worker = ComWorker(poster, lambda: FakeMailBackend([data]), use_com=False)
    engine = EngineProcess(EngineSettings(model_path=str(default_model_path()), timeout=300), poster.post)
    def com_call(fn):
        results, errors = [], []
        worker.submit(fn, results.append, errors.append, timeout_s=10)
        while not results and not errors:
            poster.queue.get(timeout=15)()
        if errors:
            raise RuntimeError("Transport fals indisponibil")
        return results[0]
    try:
        with tempfile.TemporaryDirectory(prefix="focusdesk-mail-smoke-") as directory:
            ws = Workspace.open(Path(directory) / "workspace", create=True)
            try:
                settings = ws.settings.model_copy(deep=True)
                settings.mail_monitor = MailMonitorSettings(enabled=True, store_id="fake", folders=[{"store_id": "fake", "folder_id": "inbox"}])
                ws.update_settings(settings)
                service = MailMonitorService(ws)
                plan = service.plan(now)
                page = com_call(lambda backend: backend.scan_mail_page(plan))
                locators = service.details_needed(plan, page)
                details = com_call(lambda backend: backend.read_mail_details(locators))
                service.commit(plan, page, details)
                message = ws.mail_records()[0]
                bundle, payload = build_mail_context(ws, message.id)
                responses = []
                engine.submit(Request(request_id=str(uuid4()), action="analyze_mail", instruction="Analiză locală cu dovezi.", context=json.dumps(payload)), responses.append)
                while not responses or responses[-1].kind == "loading":
                    poster.queue.get(timeout=310)()
                response = responses[-1]
                if response.kind != "result":
                    raise RuntimeError("Inferență indisponibilă")
                batch = project_analysis(ws, message.id, response.mail_analysis, bundle, response.mail_candidate_ids, response.mail_body_chars)
                if ws.nodes:
                    raise RuntimeError("Smoke-ul nu poate aplica propuneri.")
                print(json.dumps({"status": "ok", "outlook_backend": "FAKE", "inference": "GGUF REAL CPU",
                    "classification": response.mail_analysis.classification, "proposals": len(batch.items),
                    "quote_validated": True, "usage": response.usage, "tasks_created": 0, "messages_sent": 0}))
            finally:
                ws.close()
    except Exception as exc:
        print(json.dumps({"status": "error", "error_type": type(exc).__name__, "content": "omitted"}))
        return 1
    finally:
        engine.close()
        engine.wait_closed()
        worker.shutdown()
    return 0


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
