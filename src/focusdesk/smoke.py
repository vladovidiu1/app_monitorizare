"""Opt-in application smoke using disposable workspace/profile, never personal data."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile


def run_smoke() -> dict:
    previous = {key: os.environ.get(key) for key in ('APPDATA', 'LOCALAPPDATA')}
    try:
        with tempfile.TemporaryDirectory(prefix='focusdesk-smoke-') as directory:
            base = Path(directory)
            os.environ['APPDATA'] = str(base / 'profile')
            os.environ['LOCALAPPDATA'] = str(base / 'local')
            return _run(base)
    except Exception as exc:
        return {'status': 'error', 'error': f'{type(exc).__name__}: {exc}'}
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _run(base: Path) -> dict:
    import sys
    from datetime import datetime, timedelta, timezone
    from .config import AppConfig
    from .domain.models import Kind
    from .services.sessions import SessionService
    from .services.workspace import Workspace
    from .ui.app import FocusDeskApp
    from .integrations.gmail import GmailTransport,GmailCredentials,mime_message
    from .integrations.credentials import WindowsCredentialStore
    from .services.mail import build_draft
    # Resolve standard-library/native dependencies in the executable without accessing
    # a real credential or contacting any mail server.
    class FakeSmtp:
        def __init__(self,*args,**kwargs):
            context=kwargs['context']
            assert context.check_hostname
        def login(self,address,password):pass
        def quit(self):pass
    assert GmailTransport(smtp_ssl=FakeSmtp).test(GmailCredentials('test@example.invalid','fake-only'))
    assert mime_message(build_draft('to@example.invalid','','Unicode îäéñ','Smoke body'),'test@example.invalid')['Message-ID']
    credential_api_loaded=WindowsCredentialStore().available
    if sys.platform=='win32':assert credential_api_loaded

    config = AppConfig(theme='dark', legacy_marker='preserve-user-settings',
                       ai={'enabled': True, 'model_path': 'old-unused-path'})
    config.save()
    root = base / 'workspace'
    ws = Workspace.open(root, create=True, name='Temporary smoke')
    try:
        settings = ws.settings.model_copy(deep=True)
        settings.backup.daily = False
        settings.mail_monitor = {'enabled': True, 'folders': ['obsolete-settings']}
        ws.update_settings(settings)
    finally:
        ws.close()
    app = FocusDeskApp()
    callbacks = []
    app.root.report_callback_exception = lambda cls, value, tb: callbacks.append(str(value))
    try:
        app.root.withdraw()
        assert app.open_workspace(root)
        project = app.ws.create_node(Kind.PROJECT, 'Local project')
        task = app.ws.create_node(Kind.TASK, 'Manual task', project.id, description='Persistent description')
        child = app.ws.create_node(Kind.TASK, 'Manual subtask', task.id)
        app.ws.add_note(task.id, 'Saved note')
        start = datetime.now(timezone.utc) + timedelta(days=1)
        session = SessionService(app.ws).create(task.id, start, start + timedelta(minutes=30))
        app.refresh_all()
        app.select_node(task.id, reveal=True)
        for view in ('today', 'tasks', 'calendar', 'activity'):
            app.show_view(view, select_sidebar=True)
            app.root.update()
        app.select_node(task.id, reveal=True)
        assert app.open_task_space(task.id)
        app.task_space.editor.text.insert('end', '\nTask space smoke')
        assert app.task_space.save()
        before_timer = app.timer.active
        app.task_space.toggle_focus()
        app.root.update()
        app.task_space.exit_focus()
        assert app.timer.active == before_timer
        assert app.task_space.back()
        assert not callbacks, callbacks
        assert app.config.theme == 'light'
        assert not app.ws.settings.outlook.enabled
        assert not any(name.startswith(('focusdesk.ai', 'focusdesk.integrations.mail_read')) for name in sys.modules)
        app.inspector.revert()
    finally:
        app.on_close()
    with_workspace = Workspace.open(root)
    try:
        assert set(with_workspace.nodes) == {project.id, task.id, child.id}
        assert 'Task space smoke' in with_workspace.get_description(task.id)
        assert with_workspace.list_notes(task.id)[0].text == 'Saved note'
        assert with_workspace.repo.sessions.get(session.id).node_id == task.id
        assert with_workspace.settings.model_extra['mail_monitor']['enabled'] is True
    finally:
        with_workspace.close()
    loaded = AppConfig.load()
    assert loaded.model_extra['legacy_marker'] == 'preserve-user-settings'
    assert loaded.model_extra['ai']['enabled'] is True
    return {'status': 'ok', 'gui_started': True, 'workspace_preserved': True,
            'gmail_modules_loaded':True,'gmail_fake_smtp':True,'gmail_network_used':False,
            'credential_api_loaded':credential_api_loaded,
            'task_space_verified': True, 'settings_preserved': True, 'legacy_settings_ignored': True,
            'outlook_disabled': True, 'python_path': os.environ.get('PATH', ''),
            'frozen': bool(getattr(sys, 'frozen', False))}
