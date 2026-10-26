"""Upgrade safety: obsolete settings are inert, existing ordinary data survives."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys

from focusdesk.config import AppConfig
from focusdesk.domain.models import ChecklistItem, Kind, HistoryEvent
from focusdesk.domain.settings import Settings
from focusdesk.services.sessions import SessionService
from focusdesk.services.workspace import Workspace
from focusdesk.ui.settings_dialog import SettingsDialog

ROOT = Path(__file__).resolve().parents[1]


def test_legacy_app_settings_preserve_current_and_unknown_fields(tmp_path, monkeypatch):
    monkeypatch.setenv('APPDATA', str(tmp_path))
    data = {'geometry': '1200x800', 'ai': {'enabled': True, 'context': 'obsolete-value'},
            'recent_workspaces': ['C:/PersonalData'], 'custom': 42}
    AppConfig.path().parent.mkdir(parents=True)
    AppConfig.path().write_text(json.dumps(data))
    config = AppConfig.load()
    assert config.geometry == '1200x800'
    assert 'ai' not in AppConfig.model_fields
    config.save()
    assert AppConfig.load().model_dump()['ai'] == data['ai']
    assert AppConfig.load().model_extra['custom'] == 42


def test_legacy_workspace_settings_are_not_validated_or_activated():
    old = {'mail_monitor': {'enabled': True, 'folders': 'obsolete', 'interval_seconds': -1},
           'timezone': 'Europe/Bucharest'}
    settings = Settings.model_validate(old)
    assert 'mail_monitor' not in Settings.model_fields
    assert settings.model_dump()['mail_monitor'] == old['mail_monitor']
    assert not settings.outlook.enabled


def test_previously_created_data_and_mail_cache_survive_restart(ws):
    project = ws.create_node(Kind.PROJECT, 'Proiect existent')
    task = ws.create_node(Kind.TASK, 'Task creat anterior', project.id, description='Descriere păstrată',
                          checklist=[ChecklistItem(text='Pas existent', done=True)])
    child = ws.create_node(Kind.TASK, 'Subtask existent', task.id)
    note = ws.add_note(task.id, 'Notiță existentă')
    start = datetime.now(timezone.utc) + timedelta(days=1)
    session = SessionService(ws).create(child.id, start, start + timedelta(minutes=30))
    history = HistoryEvent(type='ai_proposal', node_id=task.id, data={'state': 'applied'})
    ws.repo.history.save(history)
    cache = ws.root / '_system' / 'mail' / 'messages' / 'old.json'
    cache.parent.mkdir(parents=True)
    cache.write_bytes(b'legacy unparsed data')
    before = cache.read_bytes()
    settings = ws.settings.model_copy(deep=True)
    settings.mail_monitor = {'enabled': True, 'folders': 'obsolete'}
    ws.update_settings(settings)
    root = ws.root
    ws.close()
    reopened = Workspace.open(root)
    try:
        assert set(reopened.nodes) == {project.id, task.id, child.id}
        assert reopened.get(task.id).checklist[0].done
        assert reopened.repo.read_description(task.id) == 'Descriere păstrată'
        assert reopened.list_notes(task.id)[0].id == note.id
        assert reopened.repo.sessions.get(session.id).node_id == child.id
        assert reopened.repo.history.get(history.id).data['state'] == 'applied'
        assert cache.read_bytes() == before
        assert not hasattr(reopened, 'mail_records')
    finally:
        reopened.close()


def test_ui_has_no_retired_services_pages_or_controls(ui):
    assert not any(hasattr(ui, name) for name in ('ai', 'mail_watch', 'assistant_btn', 'mail_page'))
    assert 'mail_review' not in ui.sidebar.views.get_children()
    assert 'Asistent' not in [tab.title for tab in ui.inspector.tabs]
    dialog = SettingsDialog(ui.root, ui)
    try:
        names = [dialog.nb.tab(tab, 'text') for tab in dialog.nb.tabs()]
        assert 'AI' not in names and 'Mailuri' not in names
        assert 'Outlook' in names and 'Colegi' in names
    finally:
        dialog.destroy()
    ui._tick()


def test_application_smoke_without_optional_engines_or_outlook(tmp_path):
    # A separate interpreter with an import blocker makes this independent of
    # packages left in the developer's environment. Real Tk and real services run.
    code = '''
import importlib.abc, sys, json
class Unavailable(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'llama_cpp', 'numpy', 'jinja2', 'diskcache', 'win32com', 'pythoncom', 'pywintypes'}:
            raise ModuleNotFoundError('Unavailable in smoke: ' + fullname)
sys.meta_path.insert(0, Unavailable())
from focusdesk.smoke import run_smoke
report = run_smoke()
print(json.dumps(report))
raise SystemExit(0 if report['status'] == 'ok' else 1)
'''
    import os
    env = {**os.environ, 'PYTHONPATH': str(ROOT / 'src')}
    result = subprocess.run([sys.executable, '-c', code], env=env, cwd=tmp_path,
                            capture_output=True, text=True, timeout=45)
    if 'no display name' in result.stdout or 'couldn\'t connect to display' in result.stdout:
        import pytest
        pytest.skip('Tk display indisponibil')
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)['legacy_settings_ignored']
