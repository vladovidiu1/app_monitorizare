from __future__ import annotations

import pytest

from focusdesk.services.workspace import Workspace


@pytest.fixture
def ws(tmp_path):
    w = Workspace.open(tmp_path / "FocusDeskData", create=True, name="Test")
    yield w
    w.close()


@pytest.fixture
def ws_root(tmp_path):
    return tmp_path / "FocusDeskData"


@pytest.fixture
def ui(ws, tmp_path, monkeypatch):
    """Real Tk application using only disposable data and ordinary task services."""
    import tkinter as tk
    from focusdesk.domain.models import Kind
    from focusdesk.ui.app import FocusDeskApp

    monkeypatch.setenv('APPDATA', str(tmp_path / 'appdata'))
    try:
        app = FocusDeskApp()
    except tk.TclError as exc:
        pytest.skip(f'Tk display indisponibil: {exc}')
    app.root.withdraw()
    ws.close()
    assert app.open_workspace(ws.root)
    node = app.ws.create_node(Kind.TASK, 'Task local', description='Descriere locală')
    app.refresh_all()
    app.select_node(node.id, reveal=True)
    yield app
    app.inspector.revert()
    if app.timer and app.timer.state:
        app.timer.discard()
    app.on_close()
