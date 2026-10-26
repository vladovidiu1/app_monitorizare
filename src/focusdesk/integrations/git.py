"""Integrare Git locala, optionala: citire status/log/diff si commit manual explicit.

Fara `git add .`, push, reset, stash, checkout sau alte operatii automate. Argumente ca liste, shell=False.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..errors import FocusDeskError
from ..storage.paths import is_within

log = logging.getLogger(__name__)
CREATE_NO_WINDOW = 0x08000000
TIMEOUT_S = 20


class GitError(FocusDeskError):
    pass


@dataclass
class GitStatusEntry:
    code: str  # ex. " M", "??", "A "
    path: str

    @property
    def untracked(self) -> bool:
        return self.code == "??"


@dataclass
class GitCommit:
    hash: str
    when: datetime
    author: str
    subject: str


def find_git() -> str | None:
    return shutil.which("git")


def _run(folder: Path, args: list[str], *, max_output: int = 2_000_000, timeout: int = TIMEOUT_S) -> str:
    exe = find_git()
    if exe is None:
        raise GitError("Git nu a fost găsit în PATH. Proiectele fără Git funcționează complet cu checkpoint-uri.")
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0", LC_ALL="C.UTF-8")
    try:
        res = subprocess.run([exe, "-C", str(folder), *args], capture_output=True, timeout=timeout, shell=False,
                             env=env, creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"Git nu a răspuns în {timeout} s.") from exc
    except OSError as exc:
        raise GitError(f"Git nu a putut fi pornit: {exc}") from exc
    if res.returncode != 0:
        msg = res.stderr.decode("utf-8", errors="replace").strip()
        raise GitError(msg or f"git a ieșit cu codul {res.returncode}")
    return res.stdout[:max_output].decode("utf-8", errors="replace")


def repo_root(folder: Path) -> Path | None:
    try:
        out = _run(folder, ["rev-parse", "--show-toplevel"]).strip()
    except GitError:
        return None
    return Path(out) if out else None


def branch(folder: Path) -> str:
    try:
        return _run(folder, ["rev-parse", "--abbrev-ref", "HEAD"]).strip() or "?"
    except GitError:
        return "(fără commit-uri)"


def status(folder: Path) -> list[GitStatusEntry]:
    out = _run(folder, ["status", "--porcelain=v1", "-z", "--untracked-files=normal"])
    entries: list[GitStatusEntry] = []
    parts = out.split("\0")
    i = 0
    while i < len(parts):
        p = parts[i]
        i += 1
        if len(p) < 4:
            continue
        code, path = p[:2], p[3:]
        if code[0] in "RC":  # rename/copy: urmatorul camp este calea veche
            i += 1
        entries.append(GitStatusEntry(code, path))
    return entries


def log_commits(folder: Path, limit: int = 30) -> list[GitCommit]:
    try:
        out = _run(folder, ["log", f"-n{int(limit)}", "--pretty=format:%H%x1f%aI%x1f%an%x1f%s%x1e"])
    except GitError as exc:
        if "does not have any commits" in str(exc) or "bad default revision" in str(exc):
            return []
        raise
    commits = []
    for rec in out.split("\x1e"):
        rec = rec.strip("\n")
        if not rec:
            continue
        h, d, a, s = (rec.split("\x1f") + ["", "", "", ""])[:4]
        commits.append(GitCommit(h, datetime.fromisoformat(d), a, s))
    return commits


def diff(folder: Path, path: str | None = None, *, max_bytes: int = 200_000) -> str:
    args = ["diff", "--no-color"]
    if path:
        _check_relpath(folder, path)
        args += ["--", path]
    out = _run(folder, args, max_output=max_bytes)
    return out if out else "(Fără diferențe față de ultimul commit.)"


def _check_relpath(folder: Path, rel: str) -> None:
    p = Path(rel)
    if p.is_absolute() or ".." in p.parts or not rel.strip():
        raise GitError(f"Cale invalidă pentru Git: {rel!r}")
    if not is_within(folder, folder / p):
        raise GitError(f"Cale în afara repository-ului: {rel!r}")


def propose_message(task_title: str, summary: str | None = None) -> str:
    msg = task_title.strip()
    if summary:
        msg += "\n\n" + summary.strip()
    return msg


def commit(folder: Path, message: str, files: list[str]) -> str:
    """Commit MANUAL doar pentru fisierele alese explicit; nu se foloseste `-A`/`.`/push/reset/stash/checkout."""
    message = message.strip()
    if not message:
        raise GitError("Mesajul commit-ului este obligatoriu.")
    if not files:
        raise GitError("Alege cel puțin un fișier pentru commit.")
    for f in files:
        _check_relpath(folder, f)
    _run(folder, ["add", "--", *files])
    _run(folder, ["commit", "-m", message, "--", *files])
    return _run(folder, ["rev-parse", "HEAD"]).strip()


def commits_between(commits: list[GitCommit], windows: list[tuple[datetime, datetime]], slack_minutes: int = 5
                    ) -> list[GitCommit]:
    """Commit-urile facute in timpul (sau imediat dupa) sesiunilor de lucru ale unui task."""
    from datetime import timedelta

    slack = timedelta(minutes=slack_minutes)
    out = []
    for c in commits:
        for a, b in windows:
            if a - slack <= c.when <= b + slack:
                out.append(c)
                break
    return out
