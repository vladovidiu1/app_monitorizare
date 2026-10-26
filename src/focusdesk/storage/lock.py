"""Lock real de proces pentru un workspace (portalocker)."""

from __future__ import annotations

import os
from pathlib import Path

import portalocker

from ..errors import WorkspaceLockedError


class WorkspaceLock:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._fh = None

    @property
    def held(self) -> bool:
        return self._fh is not None

    def acquire(self) -> None:
        if self._fh is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.path, "a+", encoding="utf-8")
        try:
            portalocker.lock(fh, portalocker.LOCK_EX | portalocker.LOCK_NB)
        except (portalocker.LockException, OSError) as exc:
            fh.close()
            raise WorkspaceLockedError(
                "Workspace-ul este deschis în altă instanță FocusDesk."
            ) from exc
        self._fh = fh
        try:
            fh.seek(0)
            fh.truncate()
            fh.write(f"pid={os.getpid()}\n")
            fh.flush()
        except OSError:
            pass

    def release(self) -> None:
        if self._fh is None:
            return
        try:
            portalocker.unlock(self._fh)
        except (portalocker.LockException, OSError, ValueError):
            pass
        finally:
            self._fh.close()
            self._fh = None
