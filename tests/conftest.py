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
