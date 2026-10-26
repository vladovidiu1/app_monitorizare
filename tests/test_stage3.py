from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from focusdesk.domain.models import Kind, Status
from focusdesk.errors import (
    ExternalModificationError, NotFoundError, StorageError, UnsafePathError, ValidationError,
)
from focusdesk.integrations.system import OpenError, is_runnable, open_with_default_app
from focusdesk.services.checkpoints import CheckpointService, SourceChangedDuringCapture
from focusdesk.services.files import FileService, NameConflict
from focusdesk.services.timer import TimerService
from focusdesk.storage.paths import resolve_inside
from focusdesk.storage.ziputil import safe_extract_zip


@pytest.fixture
def code_dir(tmp_path):
    d = tmp_path / "cod"
    (d / "src").mkdir(parents=True)
    (d / "src" / "main.py").write_text("print('salut')\n", "utf-8")
    (d / "README.md").write_text("# Proiect\n", "utf-8")
    for junk in (".git", ".venv", "__pycache__", "node_modules", "dist"):
        (d / junk).mkdir()
        (d / junk / "x.txt").write_text("ignora", "utf-8")
    (d / ".env").write_text("SECRET=1", "utf-8")
    (d / "cheie.pem").write_text("-----BEGIN-----", "utf-8")
    return d


# ---------------- attachments ----------------

def test_managed_attachment_copy_and_conflict(ws, tmp_path):
    t = ws.create_node(Kind.TASK, "T")
    src = tmp_path / "raport.txt"
    src.write_text("v1", "utf-8")
    fs = FileService(ws)
    att = fs.add_managed(t.id, src)
    assert att.mode == "managed" and att.path == "files/raport.txt"
    assert (ws.node_dir(t.id) / "files" / "raport.txt").read_text("utf-8") == "v1"
    src.write_text("v2", "utf-8")
    with pytest.raises(NameConflict):
        fs.add_managed(t.id, src)
    both = fs.add_managed(t.id, src, on_conflict="keep_both")
    assert both.path == "files/raport (2).txt"
    fs.add_managed(t.id, src, on_conflict="replace")
    assert (ws.node_dir(t.id) / "files" / "raport.txt").read_text("utf-8") == "v2"
    assert len(ws.get(t.id).attachments) == 2


def test_external_link_removal_never_deletes_original(ws, tmp_path):
    t = ws.create_node(Kind.TASK, "T")
    ext = tmp_path / "original.docx"
    ext.write_text("important", "utf-8")
    fs = FileService(ws)
    att = fs.add_external(t.id, ext)
    fs.remove_attachment(t.id, att.id, delete_managed_copy=True)
    assert ext.exists()
    assert ws.get(t.id).attachments == []


def test_missing_external_reported_and_relocatable(ws, tmp_path):
    t = ws.create_node(Kind.TASK, "T")
    ext = tmp_path / "a.txt"
    ext.write_text("x", "utf-8")
    fs = FileService(ws)
    att = fs.add_external(t.id, ext)
    ext.unlink()
    assert fs.status(t.id, ws.get(t.id).attachments[0]) == "missing"
    new = tmp_path / "b.txt"
    new.write_text("x", "utf-8")
    fs.relocate(t.id, att.id, new)
    assert fs.status(t.id, ws.get(t.id).attachments[0]) == "ok"
    assert len(ws.get(t.id).attachments) == 1  # referinta nu s-a sters automat


def test_managed_path_cannot_escape_workspace(ws):
    from focusdesk.domain.models import Attachment

    with pytest.raises(ValueError):
        Attachment(name="x", mode="managed", path="../../x")
    with pytest.raises(ValueError):
        Attachment(name="x", mode="managed", path="C:/Windows/x")
    with pytest.raises(ValueError):
        Attachment(name="x", mode="external", path="relativ/x")
    t = ws.create_node(Kind.TASK, "T")
    with pytest.raises(UnsafePathError):
        resolve_inside(ws.node_dir(t.id), "files/../../..")


@pytest.mark.skipif(sys.platform != "win32", reason="junction Windows")
def test_junction_not_followed(ws, tmp_path):
    t = ws.create_node(Kind.TASK, "T")
    outside = tmp_path / "afara"
    outside.mkdir()
    (outside / "secret.txt").write_text("s", "utf-8")
    link = ws.node_dir(t.id) / "files" / "link"
    res = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True)
    if res.returncode != 0:
        pytest.skip("mklink /J indisponibil")
    with pytest.raises(UnsafePathError):
        resolve_inside(ws.node_dir(t.id), "files/link/secret.txt")
    # copierea recursiva a unui folder cu junction nu urmeaza linkul
    src = tmp_path / "sursa"
    src.mkdir()
    (src / "ok.txt").write_text("ok", "utf-8")
    subprocess.run(["cmd", "/c", "mklink", "/J", str(src / "j"), str(outside)], capture_output=True)
    FileService(ws).add_managed(t.id, src)
    copied = ws.node_dir(t.id) / "files" / "sursa"
    assert (copied / "ok.txt").exists() and not (copied / "j").exists()


def test_scripts_are_not_opened_automatically(tmp_path):
    f = tmp_path / "run.py"
    f.write_text("print(1)", "utf-8")
    assert is_runnable(f)
    with pytest.raises(OpenError):
        open_with_default_app(f)
    with pytest.raises(OpenError):
        open_with_default_app(tmp_path / "lipsa.txt")


def test_code_folder_inheritance(ws, code_dir):
    proj = ws.create_node(Kind.PROJECT, "P")
    t = ws.create_node(Kind.TASK, "T", proj.id)
    sub = ws.create_node(Kind.TASK, "S", t.id)
    fs = FileService(ws)
    fs.set_code_folder(proj.id, code_dir)
    eff = fs.effective_source(sub.id)
    assert eff.path == code_dir and eff.inherited and eff.owner_id == proj.id
    other = code_dir.parent / "alt"
    other.mkdir()
    fs.set_code_folder(t.id, other)
    assert fs.effective_source(sub.id).path == other
    with pytest.raises(ValidationError):
        fs.set_code_folder(t.id, "relativ")


# ---------------- checkpoints ----------------

def _service(ws, code_dir):
    t = ws.create_node(Kind.TASK, "T")
    FileService(ws).set_code_folder(t.id, code_dir)
    return t, CheckpointService(ws)


def test_checkpoint_manifest_excludes_and_hashes(ws, code_dir):
    t, cs = _service(ws, code_dir)
    m = cs.create(t.id, "prim")
    assert m is not None
    paths = {f.path for f in m.files}
    assert paths == {"src/main.py", "README.md"}
    assert all(len(f.sha256) == 64 for f in m.files)
    snap = ws.node_dir(t.id) / "snapshots" / m.archive
    with zipfile.ZipFile(snap) as zf:
        assert "manifest.json" in zf.namelist()
        assert "files/src/main.py" in zf.namelist()
        stored = json.loads(zf.read("manifest.json"))
        assert stored["id"] == m.id and stored["complete"] is True


def test_checkpoint_deduplicates_when_unchanged(ws, code_dir):
    t, cs = _service(ws, code_dir)
    assert cs.create(t.id) is not None
    assert cs.create(t.id) is None
    (code_dir / "README.md").write_text("# Nou\n", "utf-8")
    assert cs.create(t.id) is not None
    assert len(cs.list_for_node(t.id)) == 2
    # doar mtime schimbat: continutul identic -> tot fara checkpoint nou
    p = code_dir / "README.md"
    os.utime(p, (p.stat().st_atime, p.stat().st_mtime + 100))
    assert cs.create(t.id) is None
    assert cs.create(t.id, force=True) is not None


def test_checkpoint_inherited_by_subtasks_dedupes_across_tasks(ws, code_dir):
    proj = ws.create_node(Kind.PROJECT, "P")
    a = ws.create_node(Kind.TASK, "A", proj.id)
    b = ws.create_node(Kind.TASK, "B", proj.id)
    FileService(ws).set_code_folder(proj.id, code_dir)
    cs = CheckpointService(ws)
    assert cs.create(a.id) is not None
    assert cs.create(b.id) is None  # aceeasi sursa, neschimbata
    assert [m.node_id for m in cs.list_for_node(b.id)] == [a.id]


def test_diff_new_modified_deleted_and_text_diff(ws, code_dir):
    t, cs = _service(ws, code_dir)
    m = cs.create(t.id)
    (code_dir / "src" / "main.py").write_text("print('altceva')\n", "utf-8")
    (code_dir / "nou.txt").write_text("n", "utf-8")
    (code_dir / "README.md").unlink()
    d = cs.diff_current(m)
    assert d == {"new": ["nou.txt"], "modified": ["src/main.py"], "deleted": ["README.md"]}
    text = cs.text_diff(m, "src/main.py")
    assert "-print('salut')" in text and "+print('altceva')" in text
    assert "limită" in cs.text_diff(m, "src/main.py", max_bytes=3) or "prea mare" in cs.text_diff(m, "src/main.py", max_bytes=3)


def test_restore_goes_to_separate_folder_and_does_not_touch_source(ws, code_dir, tmp_path):
    t, cs = _service(ws, code_dir)
    m = cs.create(t.id)
    (code_dir / "src" / "main.py").write_text("MODIFICAT\n", "utf-8")
    dest = tmp_path / "restaurat"
    cs.restore(m, dest)
    assert (dest / "src" / "main.py").read_text("utf-8") == "print('salut')\n"
    assert (code_dir / "src" / "main.py").read_text("utf-8") == "MODIFICAT\n"
    with pytest.raises(ValidationError):
        cs.restore(m, dest)  # destinatia nu mai este goala
    with pytest.raises(ValidationError):
        cs.restore(m, code_dir / "sub")  # in interiorul sursei


def test_restore_overwrite_makes_safety_checkpoint(ws, code_dir):
    t, cs = _service(ws, code_dir)
    m = cs.create(t.id)
    (code_dir / "src" / "main.py").write_text("MODIFICAT\n", "utf-8")
    cs.restore(m, code_dir, overwrite_source=True)
    assert (code_dir / "src" / "main.py").read_text("utf-8") == "print('salut')\n"
    triggers = [x.trigger for x in cs.list_for_node(t.id)]
    assert "pre_restore" in triggers


def test_source_changed_during_capture_is_not_kept(ws, code_dir, monkeypatch):
    t, cs = _service(ws, code_dir)
    original = CheckpointService._add_file

    def sabotage(zf, rel, path, st0):
        res = original(zf, rel, path, st0)
        if rel == "README.md":
            (code_dir / "adaugat-in-timpul.txt").write_text("x", "utf-8")
        return res

    monkeypatch.setattr(CheckpointService, "_add_file", staticmethod(sabotage))
    with pytest.raises(SourceChangedDuringCapture):
        cs.create(t.id)
    monkeypatch.undo()
    assert cs.list_for_node(t.id) == []
    assert not list((ws.node_dir(t.id) / "snapshots").glob("*"))


def test_zip_path_traversal_rejected(tmp_path):
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("../evil.txt", "x")
    with pytest.raises(UnsafePathError):
        safe_extract_zip(bad, tmp_path / "out")
    assert not (tmp_path / "evil.txt").exists()
    bad2 = tmp_path / "bad2.zip"
    with zipfile.ZipFile(bad2, "w") as zf:
        zf.writestr("ok.txt", "y")
        zf.writestr("C:/Windows/evil.txt", "x")
    with pytest.raises(UnsafePathError):
        safe_extract_zip(bad2, tmp_path / "out2")
    assert not (tmp_path / "out2" / "ok.txt").exists()  # nu se extrage nimic partial


def test_restore_rejects_malicious_manifest_archive(ws, code_dir, tmp_path):
    t, cs = _service(ws, code_dir)
    m = cs.create(t.id)
    snap = ws.node_dir(t.id) / "snapshots" / m.archive
    with zipfile.ZipFile(snap, "a") as zf:
        zf.writestr("files/../../evil.txt", "x")
    with pytest.raises(UnsafePathError):
        cs.restore(m, tmp_path / "r")
    assert not (tmp_path / "evil.txt").exists()


def test_checkpoint_size_limits_and_retention(ws, code_dir):
    t, cs = _service(ws, code_dir)
    ws.settings.checkpoints.retention = 2
    for i in range(4):
        (code_dir / "README.md").write_text(f"v{i}", "utf-8")
        assert cs.create(t.id) is not None
    assert len(cs.list_for_node(t.id)) == 2
    ws.settings.checkpoints.max_total_mb = 0
    (code_dir / "README.md").write_text("mare", "utf-8")
    with pytest.raises(StorageError):
        cs.create(t.id)


# ---------------- timer ----------------

class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_timer_counts_only_active_time_and_single_active(ws):
    clock = FakeClock()
    t = ws.create_node(Kind.TASK, "T")
    t2 = ws.create_node(Kind.TASK, "T2")
    timer = TimerService(ws, mono=clock)
    timer.start(t.id)
    with pytest.raises(ValidationError):
        timer.start(t2.id)
    for _ in range(10):
        clock.t += 1
        timer.tick()
    timer.pause()
    clock.t += 500  # pauza nu se numara
    timer.resume()
    for _ in range(5):
        clock.t += 1
        timer.tick()
    s = timer.stop(summary="am lucrat", next_action="pasul 2")
    assert s.actual_seconds == 15 and s.status == "done"
    assert ws.get(t.id).next_action == "pasul 2"
    assert ws.get(t.id).status == Status.IN_PROGRESS
    assert any(n.text == "am lucrat" for n in ws.list_notes(t.id))
    assert not (ws.repo.system_dir / "timer.json").exists()


def test_timer_sleep_gap_is_not_counted_as_work(ws):
    clock = FakeClock()
    t = ws.create_node(Kind.TASK, "T")
    timer = TimerService(ws, mono=clock)
    timer.start(t.id)
    for _ in range(5):
        clock.t += 1
        timer.tick()
    clock.t += 3 * 3600  # PC in repaus
    timer.tick()
    assert timer.state.state == "paused"
    assert timer.pending_gap >= 3 * 3600
    assert timer.seconds == 5
    timer.resume()  # fara confirmare explicita
    assert timer.seconds == 5
    s = timer.stop()
    assert s.actual_seconds == 5


def test_timer_gap_can_be_partially_confirmed(ws):
    clock = FakeClock()
    t = ws.create_node(Kind.TASK, "T")
    timer = TimerService(ws, mono=clock)
    timer.start(t.id)
    clock.t += 600
    timer.tick()
    assert timer.pending_gap == 600
    timer.resume(count_gap_seconds=120)
    assert timer.seconds == 120


def test_timer_crash_recovery_does_not_invent_time(ws_root):
    from focusdesk.services.workspace import Workspace

    clock = FakeClock()
    ws = Workspace.open(ws_root, create=True)
    t = ws.create_node(Kind.TASK, "T")
    timer = TimerService(ws, mono=clock)
    timer.start(t.id)
    for _ in range(30):
        clock.t += 1
        timer.tick()
    timer._persist()
    ws.close()  # simulam inchiderea bruta: timer.json ramane

    ws2 = Workspace.open(ws_root)
    timer2 = TimerService(ws2, mono=clock)
    assert timer2.recovered is not None and not timer2.active
    assert timer2.recovered.state.accumulated_seconds == 30
    s = timer2.finalize_recovered(30)
    assert s.actual_seconds == 30
    assert not (ws2.repo.system_dir / "timer.json").exists()
    ws2.close()


def test_planned_time_is_not_worked_time(ws):
    from datetime import timedelta
    from focusdesk.domain.common import utcnow
    from focusdesk.domain.session import SessionRecord

    t = ws.create_node(Kind.TASK, "T")
    start = utcnow() + timedelta(hours=1)
    s = SessionRecord(node_id=t.id, start_at=start, end_at=start + timedelta(hours=2))
    ws.repo.sessions.save(s)
    assert ws.repo.sessions.get(s.id).actual_seconds == 0
    assert s.planned_minutes == 120


def test_timer_requires_writable_workspace(ws_root):
    from focusdesk.errors import ReadOnlyError
    from focusdesk.services.workspace import Workspace

    ws1 = Workspace.open(ws_root, create=True)
    t = ws1.create_node(Kind.TASK, "T")
    ws2 = Workspace.open(ws_root)
    with pytest.raises(ReadOnlyError):
        TimerService(ws2).start(t.id)
    ws2.close()
    ws1.close()
