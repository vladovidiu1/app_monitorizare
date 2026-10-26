"""Ierarhie de task-uri la orice adancime, mutari de nivel si e-mail din task."""

from __future__ import annotations

import pytest

from focusdesk.domain.models import Kind
from focusdesk.errors import ReadOnlyError, ValidationError
from focusdesk.services.mail import (
    build_draft, clean_subject, default_body, default_subject, journal_text, parse_addresses,
)
from focusdesk.services.queries import Queries
from focusdesk.services.colleagues import import_colleagues, load_colleagues, requester
from focusdesk.services.workspace import Workspace
from openpyxl import Workbook


def chain(ws, depth: int):
    """Proiect > task > subtask > ... pe `depth` niveluri de task-uri."""
    proj = ws.create_node(Kind.PROJECT, "Proiect A")
    parent, nodes = proj, []
    for i in range(depth):
        parent = ws.create_node(Kind.TASK, f"Nivel {i + 1}", parent.id)
        nodes.append(parent)
    return proj, nodes


def test_tasks_nest_to_any_depth_and_subtree_includes_all(ws):
    proj, nodes = chain(ws, 8)
    assert ws.get(nodes[-1].id).parent_id == nodes[-2].id
    assert [n.title for n in ws.ancestors(nodes[-1].id)][:2] == ["Proiect A", "Nivel 1"]
    assert {n.id for n in Queries(ws).tasks_in(proj.id)} == {n.id for n in nodes}
    assert ws.breadcrumb(nodes[-1].id).count("›") == 8


def test_progress_map_matches_progress_for_every_node(ws):
    proj, nodes = chain(ws, 3)
    leaf = ws.create_node(Kind.TASK, "Frunză 2", nodes[0].id, estimated_minutes=30, remaining_minutes=30)
    ws.update_node(nodes[-1].id, status="done")
    q = Queries(ws)
    pm = q.progress_map()
    for n in ws.nodes.values():
        assert pm[n.id] == q.progress(n.id), n.title
    assert pm[proj.id].done == 1 and pm[proj.id].open == 1 and pm[leaf.id].remaining_minutes == 30


def test_indent_and_outdent_via_move_keep_ids(ws):
    proj = ws.create_node(Kind.PROJECT, "P")
    a = ws.create_node(Kind.TASK, "A", proj.id)
    b = ws.create_node(Kind.TASK, "B", proj.id)
    ws.move(b.id, a.id)
    assert ws.get(b.id).parent_id == a.id
    ws.move(b.id, proj.id, ws.get(a.id).sort_order + 5)
    assert ws.get(b.id).parent_id == proj.id
    assert [n.title for n in ws.children(proj.id)] == ["A", "B"]
    with pytest.raises(ValidationError):
        ws.move(proj.id, a.id)  # proiectul nu intra intr-un task


def test_parse_addresses_accepts_separators_names_and_dedupes():
    got = parse_addresses("ana@firma.ro; Ion Pop <ion.pop@firma.ro>,\nANA@firma.ro")
    assert got == ["ana@firma.ro", "ion.pop@firma.ro"]
    assert parse_addresses("  ") == []


@pytest.mark.parametrize("bad", ["fara-arond", "a@b", "a b@c.ro", "x@y.ro;oops", "<>"])
def test_parse_addresses_rejects_invalid(bad):
    with pytest.raises(ValidationError):
        parse_addresses(bad)


def test_build_draft_rules_for_send_and_draft():
    d = build_draft("a@b.ro", "", "Sub\niect", " text ")
    assert d.subject == "Sub iect" and d.body == "text" and d.cc == []
    with pytest.raises(ValidationError):
        build_draft("", "", "S", "t")
    with pytest.raises(ValidationError):
        build_draft("a@b.ro", "", "  ", "t")
    with pytest.raises(ValidationError):
        build_draft("a@b.ro", "", "S", "   ")
    empty = build_draft("", "", "", "", for_send=False)  # ciorna: se accepta goluri
    assert empty.to == [] and empty.body == ""
    assert clean_subject("a\r\nb") == "a b"


def test_default_mail_text_contains_task_context(ws):
    proj, nodes = chain(ws, 2)
    ws.set_description(nodes[1].id, "Descriere importantă")
    node = ws.update_node(nodes[1].id, next_action="Cere clarificări")
    assert default_subject(node) == "Nelămuriri: Nivel 2"
    body = default_body(ws, node)
    assert "Nivel 2" in body and "Proiect A › Nivel 1 › Nivel 2" in body
    assert "Cere clarificări" in body and "Descriere importantă" in body
    d = build_draft("x@y.ro", "z@y.ro", "S", "t")
    assert "x@y.ro" in journal_text(d) and "CC: z@y.ro" in journal_text(d)


def write_colleagues(path, rows):
    book = Workbook()
    for row in rows:
        book.active.append(row)
    book.save(path)
    book.close()


def test_colleagues_import_task_persistence_and_monthly_replace(ws, tmp_path):
    source = tmp_path / "colegi.xlsx"
    write_colleagues(source, [("Nume complet", "Cod"), ("Pintilie Vlad Ovidiu", "V13275"), ("Ana Pop", "A123")])
    people = import_colleagues(ws, source)
    person = next(person for person in people if person.code == "v13275")
    task = ws.create_node(Kind.TASK, "Solicitare", requested_by=person)
    assert requester(ws, task).email == "v13275@eon.com"
    root = ws.root
    ws.close()
    reopened = Workspace.open(root)
    try:
        saved = reopened.get(task.id)
        assert saved.requested_by == person
        assert load_colleagues(reopened) == people
        write_colleagues(source, [("Vlad Pintilie", "v13275")])
        import_colleagues(reopened, source)
        assert requester(reopened, saved).name == "Vlad Pintilie"
        write_colleagues(source, [("Alt coleg", "alt123")])
        import_colleagues(reopened, source)
        assert requester(reopened, saved).email == "v13275@eon.com"
        assert len(load_colleagues(reopened)) == 1
    finally:
        reopened.close()


@pytest.mark.parametrize("rows", [[], [("Nume", "Cod")], [("Ana", None)], [("Ana", "a@b.ro")],
                                  [("Ana", "abc"), ("Ion", "ABC")], [("Ana", "=A1")]])
def test_invalid_colleagues_import_preserves_previous_list(ws, tmp_path, rows):
    source = tmp_path / "colegi.xlsx"
    write_colleagues(source, [("Ana", "abc")])
    original = import_colleagues(ws, source)
    write_colleagues(source, rows)
    with pytest.raises(ValidationError):
        import_colleagues(ws, source)
    assert load_colleagues(ws) == original


def test_old_tasks_and_read_only_colleagues(ws, tmp_path):
    assert ws.create_node(Kind.TASK, "Vechi").requested_by is None
    source = tmp_path / "colegi.xlsx"
    write_colleagues(source, [("Ana", "abc")])
    readonly = Workspace.open(ws.root, read_only=True)
    try:
        with pytest.raises(ReadOnlyError):
            import_colleagues(readonly, source)
    finally:
        readonly.close()


def test_colleagues_headerless_blank_rows_duplicate_names_and_backup(ws, tmp_path):
    from zipfile import ZipFile
    from focusdesk.services.backup import create_backup

    source = tmp_path / "colegi.xlsx"
    write_colleagues(source, [(None, None), (" Ana  Pop ", "ABC"), (None, None), ("Ana Pop", "xyz")])
    people = import_colleagues(ws, source)
    source.unlink()
    assert [person.label for person in load_colleagues(ws)] == ["Ana Pop (abc)", "Ana Pop (xyz)"]
    assert len(people) == 2
    backup = create_backup(ws)
    with ZipFile(backup.path) as archive:
        assert "_system/colleagues.xlsx" in archive.namelist()


def test_corrupt_excel_preserves_colleagues(ws, tmp_path):
    source = tmp_path / "colegi.xlsx"
    write_colleagues(source, [("Ana", "abc")])
    original = import_colleagues(ws, source)
    source.write_bytes(b"not an Excel workbook")
    with pytest.raises(ValidationError, match="Excel invalid"):
        import_colleagues(ws, source)
    assert load_colleagues(ws) == original
