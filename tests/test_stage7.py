from __future__ import annotations

import os
import subprocess
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from focusdesk.domain.models import Kind
from focusdesk.integrations import git
from focusdesk.services.files import FileService
from focusdesk.services.scheduler import CheckpointScheduler

TZ = ZoneInfo("Europe/Bucharest")
needs_git = pytest.mark.skipif(git.find_git() is None, reason="git indisponibil")


def run_git(folder, *args):
    subprocess.run(["git", "-C", str(folder), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    d = tmp_path / "repo"
    d.mkdir()
    run_git(d, "init", "-q")
    run_git(d, "config", "user.name", "Test")
    run_git(d, "config", "user.email", "t@example.com")
    run_git(d, "config", "commit.gpgsign", "false")
    (d / "a.txt").write_text("a1\n", "utf-8")
    (d / "b.txt").write_text("b1\n", "utf-8")
    run_git(d, "add", "--", "a.txt", "b.txt")
    old = dict(os.environ, GIT_AUTHOR_DATE="2026-01-01T10:00:00+02:00", GIT_COMMITTER_DATE="2026-01-01T10:00:00+02:00")
    subprocess.run(["git", "-C", str(d), "commit", "-q", "-m", "initial"], check=True, capture_output=True, env=old)
    return d


@needs_git
def test_git_status_log_diff(repo):
    (repo / "a.txt").write_text("a2\n", "utf-8")
    (repo / "nou.txt").write_text("n\n", "utf-8")
    st = {e.path: e.code for e in git.status(repo)}
    assert st["a.txt"].strip() == "M" and st["nou.txt"] == "??"
    assert git.repo_root(repo) is not None
    assert git.branch(repo) in ("master", "main")
    commits = git.log_commits(repo)
    assert [c.subject for c in commits] == ["initial"]
    assert "-a1" in git.diff(repo, "a.txt") and "+a2" in git.diff(repo, "a.txt")
    assert git.repo_root(repo.parent) is None  # nu este repository


@needs_git
def test_git_commit_only_chosen_files_and_never_pushes(repo):
    (repo / "a.txt").write_text("a2\n", "utf-8")
    (repo / "b.txt").write_text("b2\n", "utf-8")
    (repo / "nou.txt").write_text("n\n", "utf-8")
    h = git.commit(repo, "Modific doar a", ["a.txt"])
    assert len(h) == 40
    st = {e.path: e.code for e in git.status(repo)}
    assert "a.txt" not in st and st["b.txt"].strip() == "M" and st["nou.txt"] == "??"
    assert git.log_commits(repo)[0].subject == "Modific doar a"
    # operatiile periculoase nu exista in modul
    banned = ("push", "reset", "stash", "checkout", "add_all", "force")
    public = [n for n in dir(git) if not n.startswith("_")]
    assert not [n for n in public if any(b in n.lower() for b in banned)]


@needs_git
def test_git_commit_validation(repo):
    with pytest.raises(git.GitError):
        git.commit(repo, "", ["a.txt"])
    with pytest.raises(git.GitError):
        git.commit(repo, "x", [])
    for bad in ("..\\x", "../x", "C:\\Windows\\x", "/etc/passwd", "."):
        if bad == ".":
            continue
        with pytest.raises(git.GitError):
            git.commit(repo, "x", [bad])


@needs_git
def test_commits_between_session_windows(repo):
    (repo / "a.txt").write_text("a2\n", "utf-8")
    git.commit(repo, "in sesiune", ["a.txt"])
    c = git.log_commits(repo)[0]
    inside = [(c.when - timedelta(minutes=10), c.when + timedelta(minutes=10))]
    outside = [(c.when - timedelta(days=3), c.when - timedelta(days=2))]
    assert [x.subject for x in git.commits_between(git.log_commits(repo), inside)] == ["in sesiune"]
    assert git.commits_between(git.log_commits(repo), outside) == []


def test_git_missing_is_reported_not_fatal(monkeypatch, tmp_path):
    monkeypatch.setattr(git.shutil, "which", lambda _n: None)
    with pytest.raises(git.GitError, match="Git nu a fost găsit"):
        git.status(tmp_path)
    assert git.repo_root(tmp_path) is None


# ---------------- scheduler ----------------

def at(day, h, m):
    return datetime(2026, 11, day, h, m, tzinfo=TZ)


def test_scheduler_decisions_and_missed_report(ws):
    ws.settings.checkpoints.enabled_daily = True
    ws.settings.checkpoints.daily_time = "17:00"
    sch = CheckpointScheduler(ws)
    assert not sch.decide(at(3, 16, 0)).run
    d = sch.decide(at(3, 17, 2))
    assert d.run and not d.missed and d.note is None
    late = sch.decide(at(3, 18, 30))
    assert late.run and late.missed and "ratată" in late.note and "nu poate fi reconstruită" in late.note
    sch.mark_ran(at(3, 17, 2).date())
    assert not sch.decide(at(3, 18, 30)).run  # deja rulat azi
    assert CheckpointScheduler(ws).last_run_date() == at(3, 1, 0).date()  # persistat
    assert sch.decide(at(4, 17, 1)).run
    ws.settings.checkpoints.enabled_daily = False
    assert not sch.decide(at(4, 17, 1)).run


def test_scheduler_dedupes_shared_source(ws, tmp_path):
    code = tmp_path / "cod"
    code.mkdir()
    other = tmp_path / "alt"
    other.mkdir()
    proj = ws.create_node(Kind.PROJECT, "P")
    a = ws.create_node(Kind.TASK, "A", proj.id)
    b = ws.create_node(Kind.TASK, "B", proj.id)
    c = ws.create_node(Kind.TASK, "C")
    fs = FileService(ws)
    fs.set_code_folder(proj.id, code)
    fs.set_code_folder(c.id, other)
    # B isi seteaza explicit ACELASI folder ca proiectul: tot o singura sursa
    fs.set_code_folder(b.id, code)
    missing = ws.create_node(Kind.TASK, "D")
    fs.set_code_folder(missing.id, other)
    sources = CheckpointScheduler(ws).sources()
    assert len(sources) == 2
    import shutil

    shutil.rmtree(other)
    assert len(CheckpointScheduler(ws).sources()) == 1  # folderul lipsa este ignorat, nu sters din referinte
    assert ws.get(c.id).source_workspace is not None
