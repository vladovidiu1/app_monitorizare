from __future__ import annotations

import json
import os

import pytest

from focusdesk.domain.models import Kind, Node, Status
from focusdesk.errors import (
    CycleError, ExternalModificationError, ReadOnlyError, StorageError, ValidationError,
)
from focusdesk.services.workspace import Workspace
from focusdesk.storage import atomic, operations as ops
from focusdesk.storage.paths import physical_dirname, resolve_inside, sanitize_filename, slugify
from focusdesk.storage.repository import WorkspaceRepository
from focusdesk.errors import UnsafePathError


def reopen(root) -> Workspace:
    return Workspace.open(root)


def test_empty_workspace_created_without_demo_data(ws):
    assert ws.nodes == {}
    assert (ws.root / "workspace.json").exists()
    assert (ws.root / "_system" / "settings.json").exists()
    assert ws.repo.meta.demo is False


def test_hierarchy_and_order_persist_across_restart(ws_root):
    ws = Workspace.open(ws_root, create=True)
    proj = ws.create_node(Kind.PROJECT, "Validări XML")
    t1 = ws.create_node(Kind.TASK, "Primul", proj.id)
    t2 = ws.create_node(Kind.TASK, "Al doilea", proj.id)
    sub = ws.create_node(Kind.TASK, "Subtask", t1.id)
    ws.reorder(t2.id, -1)
    ws.set_description(t1.id, "Descriere cu diacritice: ăîșțâ")
    ws.close()

    ws2 = Workspace.open(ws_root)
    assert {n.title for n in ws2.nodes.values()} == {"Validări XML", "Primul", "Al doilea", "Subtask"}
    assert [n.title for n in ws2.children(proj.id)] == ["Al doilea", "Primul"]
    assert ws2.get(sub.id).parent_id == t1.id
    assert ws2.get_description(t1.id) == "Descriere cu diacritice: ăîșțâ"
    ws2.close()


def test_independent_daily_task_and_project_link_without_physical_duplicate(ws):
    daily = ws.create_node(Kind.FOLDER, "Solicitări zilnice")
    proj = ws.create_node(Kind.PROJECT, "Proiect")
    task = ws.create_node(Kind.TASK, "Cerere", daily.id)
    ws.add_related(proj.id, task.id)
    dirs = [p for p in ws.root.rglob("node.json") if json.loads(p.read_text("utf-8"))["id"] == task.id]
    assert len(dirs) == 1
    from focusdesk.services.queries import Queries

    assert task.id in {n.id for n in Queries(ws).tasks_in(proj.id)}
    assert ws.get(task.id).parent_id == daily.id


def test_parent_rules_and_cycles(ws):
    folder = ws.create_node(Kind.FOLDER, "F")
    proj = ws.create_node(Kind.PROJECT, "P", folder.id)
    task = ws.create_node(Kind.TASK, "T", proj.id)
    with pytest.raises(ValidationError):
        ws.create_node(Kind.FOLDER, "x", task.id)
    with pytest.raises(ValidationError):
        ws.create_node(Kind.PROJECT, "p2", proj.id)
    with pytest.raises(CycleError):
        ws.move(folder.id, proj.id)
    with pytest.raises(ValidationError):
        ws.update_node(folder.id, status=Status.TODO)


def test_dependency_cycle_rejected_and_blocked(ws):
    a = ws.create_node(Kind.TASK, "A")
    b = ws.create_node(Kind.TASK, "B")
    c = ws.create_node(Kind.TASK, "C")
    ws.add_dependency(b.id, a.id)
    ws.add_dependency(c.id, b.id)
    with pytest.raises(CycleError):
        ws.add_dependency(a.id, c.id)
    with pytest.raises(CycleError):
        ws.add_dependency(a.id, a.id)
    assert [n.id for n in ws.unfinished_dependencies(b.id)] == [a.id]
    ws.update_node(a.id, status=Status.DONE)
    assert ws.unfinished_dependencies(b.id) == []


def test_rename_keeps_dir_and_uuid(ws):
    t = ws.create_node(Kind.TASK, "Titlu vechi")
    d = ws.node_dir(t.id)
    ws.rename(t.id, "Titlu nou ăâ")
    assert ws.node_dir(t.id) == d
    assert ws.get(t.id).id == t.id
    new_dir = ws.rename_physical(t.id)
    assert new_dir.name == physical_dirname("Titlu nou ăâ", t.id)
    assert (new_dir / "node.json").exists()


def test_move_keeps_uuids_and_children(ws):
    f1 = ws.create_node(Kind.FOLDER, "Sursa")
    f2 = ws.create_node(Kind.FOLDER, "Destinatia")
    t = ws.create_node(Kind.TASK, "Cu copii", f1.id)
    s = ws.create_node(Kind.TASK, "Copil", t.id)
    ws.add_note(t.id, "o notiță")
    (ws.node_dir(t.id) / "files" / "x.txt").write_text("fisier", "utf-8")
    ws.move(t.id, f2.id)
    assert ws.get(t.id).parent_id == f2.id
    assert ws.get(s.id).parent_id == t.id
    assert (ws.node_dir(t.id) / "files" / "x.txt").read_text("utf-8") == "fisier"
    assert ws.node_dir(s.id).parent == ws.node_dir(t.id).parent == ws.repo.nodes_dir  # layout plat: mutarea nu atinge discul
    assert len(ws.list_notes(t.id)) == 1
    ws.reload()
    assert not [i for i in ws.issues if i.severity == "error"]
    assert ws.get(s.id).parent_id == t.id


def test_interrupted_trash_is_rolled_forward(ws_root):
    ws = Workspace.open(ws_root, create=True)
    t = ws.create_node(Kind.TASK, "T")
    s = ws.create_node(Kind.TASK, "S", t.id)
    s_dir = ws.node_dir(s.id)
    ws.trash(t.id)
    op = next(o for o in ws.repo.operations.list_all() if o.type == "trash_node")
    ws.close()
    # Crash simulat dupa mutarea primului director: al doilea ramane in nodes/, jurnalul ramane `pending`.
    import shutil

    shutil.move(str(ws_root / "_system" / "trash" / t.id / "nodes" / s_dir.name), str(ws_root / "nodes" / s_dir.name))
    repo = WorkspaceRepository.open(ws_root)
    op = repo.operations.get(op.id)
    op.state = "pending"
    repo.operations.save(op)
    repo.close()

    ws2 = Workspace.open(ws_root)
    assert any("finalizată" in m for m in ws2.recovery_messages)
    assert t.id not in ws2.nodes and s.id not in ws2.nodes
    assert [e["node_id"] for e in ws2.list_trash()] == [t.id]
    ws2.restore(t.id)
    assert ws2.get(s.id).parent_id == t.id
    ws2.close()


def test_interrupted_move_not_started_is_rolled_back(ws_root):
    ws = Workspace.open(ws_root, create=True)
    f1 = ws.create_node(Kind.FOLDER, "A")
    f2 = ws.create_node(Kind.FOLDER, "B")
    t = ws.create_node(Kind.TASK, "T", f1.id)
    old_dir = ws.node_dir(t.id)
    op = ops._new_op(ws.repo, "move_node", {
        "node_id": t.id, "old_dir": str(old_dir),
        "new_dir": str(ws.node_dir(f2.id) / "children" / old_dir.name), "patch": {"parent_id": f2.id},
    })
    ws.close()
    ws2 = Workspace.open(ws_root)
    assert ws2.get(t.id).parent_id == f1.id
    assert ws2.repo.operations.get(op.id).state == "rolled_back"
    ws2.close()


def test_trash_and_restore(ws):
    p = ws.create_node(Kind.PROJECT, "P")
    t = ws.create_node(Kind.TASK, "T", p.id)
    s = ws.create_node(Kind.TASK, "S", t.id)
    other = ws.create_node(Kind.TASK, "Other")
    ws.add_related(other.id, s.id)
    ws.trash(t.id)
    assert t.id not in ws.nodes and s.id not in ws.nodes
    assert [e["node_id"] for e in ws.list_trash()] == [t.id]
    ws.restore(t.id)
    assert ws.get(s.id).parent_id == t.id
    assert ws.get(t.id).parent_id == p.id
    assert s.id in ws.get(other.id).related_node_ids
    assert ws.list_trash() == []


def test_restore_when_parent_gone_goes_to_root(ws):
    f = ws.create_node(Kind.FOLDER, "F")
    t = ws.create_node(Kind.TASK, "T", f.id)
    ws.trash(t.id)
    ws.trash(f.id)
    ws.restore(t.id)
    assert ws.get(t.id).parent_id is None


def test_corrupt_json_does_not_block_other_nodes(ws_root):
    ws = Workspace.open(ws_root, create=True)
    a = ws.create_node(Kind.TASK, "A")
    b = ws.create_node(Kind.TASK, "B")
    bad = ws.node_dir(a.id) / "node.json"
    ws.close()
    bad.write_text("{ not json", "utf-8")
    bak = bad.with_name("node.json.bak")
    if bak.exists():
        bak.unlink()
    ws2 = Workspace.open(ws_root)
    assert b.id in ws2.nodes and a.id not in ws2.nodes
    assert any(i.code == "node_corrupt" for i in ws2.issues)
    assert bad.read_text("utf-8") == "{ not json"  # nu s-a sters automat
    ws2.close()


def test_missing_index_loses_nothing(ws_root):
    ws = Workspace.open(ws_root, create=True)
    ws.create_node(Kind.TASK, "A")
    ws.close()
    (ws_root / "_system" / "index.json").unlink()
    ws2 = Workspace.open(ws_root)
    assert len(ws2.nodes) == 1
    assert (ws_root / "_system" / "index.json").exists()
    ws2.close()


def test_interrupted_write_keeps_valid_version(ws, monkeypatch):
    t = ws.create_node(Kind.TASK, "Original")
    path = ws.node_dir(t.id) / "node.json"
    before = path.read_text("utf-8")

    def failing_replace(src, dst):
        raise PermissionError("simulat")

    monkeypatch.setattr(atomic, "_replace_with_retry", failing_replace)
    with pytest.raises(StorageError):
        ws.update_node(t.id, title="Nou")
    monkeypatch.undo()
    assert path.read_text("utf-8") == before
    assert ws.get(t.id).title == "Original"
    assert not list(path.parent.glob(".*.tmp"))


def test_external_edit_not_overwritten_silently(ws):
    t = ws.create_node(Kind.TASK, "T")
    path = ws.node_dir(t.id) / "node.json"
    data = json.loads(path.read_text("utf-8"))
    data["title"] = "Editat extern"
    path.write_text(json.dumps(data), "utf-8")
    with pytest.raises(ExternalModificationError):
        ws.update_node(t.id, next_action="x")
    ws.reload()
    assert ws.get(t.id).title == "Editat extern"
    ws.update_node(t.id, next_action="x")


def test_description_external_edit_detected(ws):
    t = ws.create_node(Kind.TASK, "T")
    ws.set_description(t.id, "a")
    ws.get_description(t.id)
    (ws.node_dir(t.id) / "description.md").write_text("alta", "utf-8")
    with pytest.raises(ExternalModificationError):
        ws.set_description(t.id, "b")


def test_second_instance_is_read_only(ws_root):
    ws1 = Workspace.open(ws_root, create=True)
    ws2 = Workspace.open(ws_root)
    assert ws2.read_only and ws2.repo.lock_conflict
    with pytest.raises(ReadOnlyError):
        ws2.create_node(Kind.TASK, "nu")
    ws2.close()
    ws1.create_node(Kind.TASK, "da")
    ws1.close()


def test_duplicate_uuid_reported(ws_root):
    ws = Workspace.open(ws_root, create=True)
    a = ws.create_node(Kind.TASK, "A")
    src = ws.node_dir(a.id)
    ws.close()
    import shutil

    shutil.copytree(src, src.parent / "copie--ffffffff")
    ws2 = Workspace.open(ws_root)
    assert len(ws2.nodes) == 1
    assert any(i.code == "duplicate_id" for i in ws2.issues)
    ws2.close()


def test_special_dirs_are_not_nodes(ws):
    t = ws.create_node(Kind.TASK, "T")
    d = ws.node_dir(t.id)
    fake = d / "files" / "fals--12345678"
    fake.mkdir()
    (fake / "node.json").write_text("{}", "utf-8")
    ws.reload()
    assert list(ws.nodes) == [t.id]


def test_windows_names_and_paths(ws):
    assert slugify("CON").startswith("_")
    assert slugify("  ... ") == "nod"
    assert slugify("Ștefan și țara") == "stefan-si-tara"
    assert sanitize_filename('a<b>:c.txt') == "a_b__c.txt"
    assert sanitize_filename("NUL.txt").startswith("_")
    assert sanitize_filename("nume. ") == "nume"
    t = ws.create_node(Kind.TASK, "CON")
    assert ws.node_dir(t.id).exists()
    with pytest.raises(UnsafePathError):
        resolve_inside(ws.root, "../x")
    with pytest.raises(UnsafePathError):
        resolve_inside(ws.root, "C:/Windows")


def test_deep_hierarchy_keeps_paths_short_and_survives_restart(ws_root):
    ws = Workspace.open(ws_root, create=True)
    cur = ws.create_node(Kind.PROJECT, "Proiect")
    ids = [cur.id]
    for i in range(40):
        cur = ws.create_node(Kind.TASK, "titlu foarte lung pentru a depasi limita " * 2 + str(i), cur.id)
        ids.append(cur.id)
    assert {ws.node_dir(i).parent for i in ids} == {ws.repo.nodes_dir}
    assert len(str(ws.node_dir(ids[-1]))) < len(str(ws_root)) + 60
    ws.close()
    ws2 = Workspace.open(ws_root)
    assert len(ws2.nodes) == 41 and len(ws2.ancestors(ids[-1])) == 40
    assert not [i for i in ws2.issues if i.severity == "error"]
    ws2.close()


def test_legacy_nested_layout_is_flattened_on_open(ws_root):
    import shutil

    ws = Workspace.open(ws_root, create=True)
    p = ws.create_node(Kind.PROJECT, "P")
    t = ws.create_node(Kind.TASK, "T", p.id)
    s = ws.create_node(Kind.TASK, "S", t.id)
    ws.set_description(s.id, "pastrata")
    d_p, d_t, d_s = ws.node_dir(p.id), ws.node_dir(t.id), ws.node_dir(s.id)
    ws.close()
    # Layout vechi: fiecare copil in `children/` al parintelui.
    (d_p / "children").mkdir()
    shutil.move(str(d_t), str(d_p / "children" / d_t.name))
    (d_p / "children" / d_t.name / "children").mkdir()
    shutil.move(str(d_s), str(d_p / "children" / d_t.name / "children" / d_s.name))

    ws2 = Workspace.open(ws_root)
    assert any("Structura" in m for m in ws2.recovery_messages)
    assert {ws2.node_dir(i).parent for i in (p.id, t.id, s.id)} == {ws2.repo.nodes_dir}
    assert ws2.get(s.id).parent_id == t.id and ws2.get(t.id).parent_id == p.id
    assert ws2.get_description(s.id) == "pastrata"
    assert not (d_p / "children").exists()
    assert not [i for i in ws2.issues if i.severity == "error"]
    ws2.close()
    ws3 = Workspace.open(ws_root)
    assert ws3.recovery_messages == []  # idempotent
    ws3.close()


def test_legacy_trash_entry_is_restored_flat(ws):
    import shutil

    p = ws.create_node(Kind.PROJECT, "P")
    t = ws.create_node(Kind.TASK, "T", p.id)
    s = ws.create_node(Kind.TASK, "S", t.id)
    ws.trash(t.id)
    entry = ws.repo.trash_dir / t.id
    mf = json.loads((entry / "manifest.json").read_text("utf-8"))
    t_name, s_name = mf["dirname"], mf["dirnames"][s.id]
    # Transformam intrarea in formatul vechi: subarbore imbricat sub directorul radacina.
    shutil.move(str(entry / "nodes" / t_name), str(entry / t_name))
    (entry / t_name / "children").mkdir()
    shutil.move(str(entry / "nodes" / s_name), str(entry / t_name / "children" / s_name))
    shutil.rmtree(entry / "nodes")
    for k in ("layout", "dirnames"):
        mf.pop(k)
    (entry / "manifest.json").write_text(json.dumps(mf), "utf-8")
    assert [e["node_id"] for e in ws.list_trash()] == [t.id]
    ws.restore(t.id)
    assert ws.get(t.id).parent_id == p.id and ws.get(s.id).parent_id == t.id
    assert ws.node_dir(s.id).parent == ws.repo.nodes_dir
    assert ws.list_trash() == []


def test_trash_dir_recovery_for_interrupted_trash(ws_root, monkeypatch):
    ws = Workspace.open(ws_root, create=True)
    t = ws.create_node(Kind.TASK, "T")
    old = ws.node_dir(t.id)
    monkeypatch.setattr(ops, "_move_dir", lambda s, d: (_ for _ in ()).throw(OSError("simulat")))
    with pytest.raises(Exception):
        ws.trash(t.id)
    monkeypatch.undo()
    assert old.exists()
    ws.close()


def test_aggregate_progress_uses_leaves_and_counts_unestimated(ws):
    from focusdesk.services.queries import Queries

    p = ws.create_node(Kind.PROJECT, "P")
    parent_task = ws.create_node(Kind.TASK, "Părinte", p.id, estimated_minutes=600)
    ws.create_node(Kind.TASK, "c1", parent_task.id, estimated_minutes=30)
    c2 = ws.create_node(Kind.TASK, "c2", parent_task.id)
    c3 = ws.create_node(Kind.TASK, "c3", parent_task.id, estimated_minutes=60)
    ws.update_node(c3.id, status=Status.DONE)
    prog = Queries(ws).progress(p.id)
    assert prog.leaf_total == 3 and prog.done == 1 and prog.open == 2
    assert prog.estimated_minutes == 30  # doar frunze deschise; estimarea parintelui nu se aduna
    assert prog.unestimated == 1
    ws.update_node(c2.id, status=Status.DONE)
    assert ws.get(parent_task.id).status != Status.DONE  # nu se finalizeaza automat


def test_today_priority_limit(ws):
    from focusdesk.services.queries import Queries

    q = Queries(ws)
    day = q.today()
    tasks = [ws.create_node(Kind.TASK, f"t{i}") for i in range(4)]
    for t in tasks[:3]:
        ws.update_node(t.id, pinned_today=day)
    with pytest.raises(ValidationError):
        ws.update_node(tasks[3].id, pinned_today=day)
    assert len(q.pinned_today()) == 3


def test_archive_requires_choice_for_future_sessions(ws):
    from datetime import timedelta
    from focusdesk.domain.common import utcnow
    from focusdesk.domain.session import SessionRecord

    t = ws.create_node(Kind.TASK, "T")
    start = utcnow() + timedelta(days=1)
    s = SessionRecord(node_id=t.id, start_at=start, end_at=start + timedelta(hours=1))
    ws.repo.sessions.save(s)
    with pytest.raises(ValidationError):
        ws.archive(t.id)
    ws.archive(t.id, future_sessions="cancel")
    assert ws.repo.sessions.get(s.id).status == "cancelled"
    assert ws.get(t.id).archived_at is not None
