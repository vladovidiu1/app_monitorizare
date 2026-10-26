from __future__ import annotations

import os
import json
from functools import partial
from pathlib import Path
import queue
import time
from uuid import uuid4

import pytest

from focusdesk.ai.process import EngineProcess, worker_main
from focusdesk.ai.protocol import EngineSettings, Proposal, Request, Response, encode


def fake_worker(conn, settings):
    count = 0
    try:
        while True:
            data = conn.recv_bytes()
            if json.loads(data).get("kind") == "stop":
                break
            request = Request.model_validate_json(data)
            count += 1
            if request.instruction == "crash":
                os._exit(9)
            if request.instruction == "hang":
                time.sleep(30)
            if request.instruction == "bad_id":
                conn.send_bytes(encode(Response(request_id=str(uuid4()), kind="error", error="wrong id")))
                continue
            if request.instruction == "error":
                conn.send_bytes(encode(Response(request_id=request.request_id, kind="error", error="backend failure")))
                continue
            conn.send_bytes(encode(Response(request_id=request.request_id, kind="result", proposal=Proposal(
                action=request.action, title="", text=f"pid={os.getpid()},count={count}"))))
    except (EOFError, OSError):
        pass
    finally:
        conn.close()


class FakeBackend:
    def __init__(self, settings):
        self.count = 0
        self.path = Path(settings.model_path)

    def generate(self, request):
        self.count += 1
        return Proposal(action=request.action, title="", text=f"call={self.count}")

    def close(self):
        self.path.write_text("closed", encoding="utf-8")


def no_read_worker(conn, settings):
    time.sleep(30)


def request(instruction="ok"):
    return Request(request_id=str(uuid4()), action="add_note", instruction=instruction, context="context")


def wait_idle(engine, timeout=5):
    deadline = time.monotonic() + timeout
    while engine.busy and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not engine.busy


@pytest.fixture
def engine():
    callbacks = queue.Queue()
    obj = EngineProcess(EngineSettings(), callbacks.put, _target=fake_worker)
    yield obj, callbacks
    obj.close()
    assert obj.wait_closed()


def receive(callbacks, results):
    callbacks.get(timeout=8)()
    assert results
    return results[-1]


def test_spawn_reuses_child_and_callbacks_are_posted(engine):
    obj, callbacks = engine
    results = []
    obj.submit(request(), results.append)
    first = receive(callbacks, results)
    assert first.kind == "result" and f"pid={os.getpid()}," not in first.proposal.text
    wait_idle(obj)
    obj.submit(request(), results.append)
    second = receive(callbacks, results)
    assert first.proposal.text.split(",")[0] == second.proposal.text.split(",")[0]
    assert second.proposal.text.endswith("count=2")


@pytest.mark.parametrize("instruction,expected", [("error", "backend failure"), ("crash", ""), ("bad_id", "ID")])
def test_backend_errors_crash_and_protocol_errors_recover(engine, instruction, expected):
    obj, callbacks = engine
    results = []
    obj.submit(request(instruction), results.append)
    response = receive(callbacks, results)
    assert response.kind == "error" and expected in response.error
    wait_idle(obj)
    obj.submit(request(), results.append)
    assert receive(callbacks, results).kind == "result"


def test_cancel_kills_hung_child_and_suppresses_late_callback(engine):
    obj, callbacks = engine
    results = []
    obj.submit(request("hang"), results.append)
    with pytest.raises(RuntimeError, match="precedentă"):
        obj.submit(request(), results.append)
    time.sleep(0.15)
    obj.cancel()
    wait_idle(obj)
    assert results == []
    obj.submit(request(), results.append)
    assert receive(callbacks, results).kind == "result"


def test_cancel_after_result_queued_does_not_deliver(engine):
    obj, callbacks = engine
    results = []
    obj.submit(request(), results.append)
    callback = callbacks.get(timeout=5)
    obj.cancel()
    callback()
    assert results == []


def test_timeout_stops_process_and_next_request_restarts(engine):
    obj, callbacks = engine
    obj.settings = obj.settings.model_copy(update={"timeout": 5})
    results = []
    obj.submit(request("hang"), results.append)
    assert "timpul" in receive(callbacks, results).error
    wait_idle(obj)
    obj.settings = obj.settings.model_copy(update={"timeout": 5})
    obj.submit(request(), results.append)
    assert receive(callbacks, results).kind == "result"


def test_close_cleans_active_process_and_refuses_more_requests(engine):
    obj, callbacks = engine
    results = []
    obj.submit(request("hang"), results.append)
    obj.close()
    assert obj.wait_closed()
    with pytest.raises(RuntimeError, match="închis"):
        obj.submit(request(), results.append)


def test_real_worker_reports_missing_model_without_loading_native(tmp_path):
    callbacks, results = queue.Queue(), []
    obj = EngineProcess(EngineSettings(model_path=str(tmp_path / "absent.gguf")), callbacks.put)
    try:
        obj.submit(request(), results.append)
        assert receive(callbacks, results).kind == "loading"
        response = receive(callbacks, results)
        assert response.kind == "error" and "absent" in response.error
    finally:
        obj.close()
        assert obj.wait_closed()


def test_production_worker_loads_fake_backend_once_and_closes_it(tmp_path):
    callbacks, results = queue.Queue(), []
    marker = tmp_path / "backend-closed.txt"
    obj = EngineProcess(EngineSettings(model_path=str(marker)), callbacks.put,
                        _target=partial(worker_main, backend_factory=FakeBackend))
    try:
        obj.submit(request(), results.append)
        assert receive(callbacks, results).kind == "loading"
        assert receive(callbacks, results).proposal.text == "call=1"
        wait_idle(obj)
        obj.submit(request(), results.append)
        assert receive(callbacks, results).proposal.text == "call=2"
        wait_idle(obj)
    finally:
        obj.close()
        assert obj.wait_closed()
    assert marker.read_text() == "closed"


def test_cancellation_works_if_child_never_reads_large_request():
    callbacks, results = queue.Queue(), []
    obj = EngineProcess(EngineSettings(), callbacks.put, _target=no_read_worker)
    try:
        large = Request(request_id=str(uuid4()), action="add_note", instruction="x" * 4000, context="x" * 8000)
        obj.submit(large, results.append)
        time.sleep(0.2)
        obj.cancel()
        wait_idle(obj)
        assert results == []
    finally:
        obj.close()
        assert obj.wait_closed()
