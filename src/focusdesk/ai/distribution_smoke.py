"""Explicit distribution diagnostics. Writes ONLY a newly created temporary workspace."""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import tempfile
import time


def _run_distribution_smoke(model: Path, *, missing=False, timeout=600):
    # No Python network calls, even during the test. CI additionally blocks the EXE
    # at Windows Firewall level (including the identical spawned executable).
    def offline(*args, **kwargs):
        raise RuntimeError('Network disabled during offline distribution smoke')
    socket.create_connection = offline
    socket.socket.connect = offline
    socket.socket.connect_ex = offline
    from ..config import AppConfig
    from ..domain.models import Kind
    from ..services.ai_actions import ActionContext, apply_proposal
    from ..services.workspace import Workspace
    from ..ui.app import FocusDeskApp
    from .models import default_model_path
    app = engine = child = None
    report = {'status': 'error', 'case': 'missing' if missing else 'real', 'python_path': os.environ.get('PATH','')}
    try:
        config = AppConfig.load()
        config.distribution_smoke_marker = 'keep-user-settings'
        config.ai.enabled = True
        config.ai.model_path = str(model.resolve())
        config.ai.threads = 2
        config.ai.timeout = timeout
        config.save()
        with tempfile.TemporaryDirectory(prefix='focusdesk-distribution-data-') as folder:
            root = Path(folder)/'workspace'
            workspace = Workspace.open(root, create=True, name='Temporary distribution smoke')
            task = workspace.create_node(Kind.TASK, 'Verificare distribuție', description='Date temporare de diagnostic, fără date personale.')
            workspace.close()
            app = FocusDeskApp()
            app.root.withdraw()
            errors = []
            app.root.report_callback_exception = lambda cls,error,tb: errors.append(str(error))
            assert app.open_workspace(root)
            assert not app.ws.settings.mail_monitor.enabled
            assert not app.ws.settings.outlook.enabled
            context = ActionContext.capture(app.ws, task.id, 'create_subtask')
            messages = []
            app.ai.request(config.ai, 'create_subtask', 'Propune un subtask foarte scurt pentru verificarea distribuției locale. Titlu și o singură propoziție.',
                'Task: verificare distribuție locală. Numai date temporare.', messages.append)
            engine = app.ai.engine
            until = time.monotonic() + timeout + 15
            while (not messages or messages[-1].kind == 'loading') and time.monotonic() < until:
                app.root.update()
                time.sleep(.02)
            assert messages and messages[-1].kind in ('result','error'), 'Frozen AI timed out'
            response = messages[-1]
            child = engine._process
            assert child and child.pid != os.getpid(), 'No separate AI process'
            report.update(parent_pid=os.getpid(), child_pid=child.pid, default_model_beside_executable=default_model_path().parent.name=='models',
                outlook_required=False, gui_started=True)
            if missing:
                assert response.kind == 'error', 'Missing model unexpectedly loaded'
                # Application remains editable after the error.
                app.ws.create_node(Kind.TASK, 'Aplicația rămâne utilizabilă')
                report['missing_model_controlled'] = True
            else:
                assert response.kind == 'result' and response.proposal, response.error
                assert response.proposal.title.strip() and response.proposal.text.strip()
                apply_proposal(app.ws, context, response.proposal)
                assert len(app.ws.nodes) == 2
                report.update(real_gguf_inference=True, task_proposal_applied=True)
            expected = set(app.ws.nodes)
            assert not errors, errors
            app.on_close()
            app = None
            assert engine.wait_closed(15), 'AI supervisor still running after application exit'
            # The supervisor joins then closes the Process handle. A closed handle
            # is only permitted by multiprocessing after that process has stopped.
            if not getattr(child, '_closed', False):
                child.join(3)
                assert not child.is_alive(), 'AI child survived application exit'
            report['ai_child_stopped'] = True
            reopened = Workspace.open(root)
            try:
                assert set(reopened.nodes) == expected
            finally:
                reopened.close()
            loaded = AppConfig.load()
            assert loaded.model_extra['distribution_smoke_marker'] == 'keep-user-settings'
            assert loaded.ai.threads == 2
            report.update(workspace_preserved=True, settings_preserved=True, status='ok')
    except Exception as exc:
        report['error'] = f'{type(exc).__name__}: {exc}'
    finally:
        if app:
            try:
                app.inspector.revert()
                app.on_close()
            except Exception:
                if engine:
                    engine.close()
        if engine:
            engine.close()
            engine.wait_closed(15)
    return report


def run_distribution_smoke(model: Path, *, missing=False, timeout=600):
    """Even a direct CLI invocation must never read or replace a personal profile."""
    original={key:os.environ.get(key) for key in ('APPDATA','LOCALAPPDATA')}
    network=(socket.create_connection,socket.socket.connect,socket.socket.connect_ex)
    with tempfile.TemporaryDirectory(prefix='focusdesk-distribution-profile-') as folder:
        try:
            os.environ['APPDATA']=str(Path(folder)/'roaming')
            os.environ['LOCALAPPDATA']=str(Path(folder)/'local')
            return _run_distribution_smoke(model,missing=missing,timeout=timeout)
        finally:
            socket.create_connection,socket.socket.connect,socket.socket.connect_ex=network
            for key,value in original.items():
                if value is None:os.environ.pop(key,None)
                else:os.environ[key]=value
