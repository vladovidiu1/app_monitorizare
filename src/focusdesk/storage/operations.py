"""Operatii pe disc cu pasi recuperabili: mutare, coș, restaurare, redenumire fizica, aplatizarea layout-ului vechi.

Ierarhia logica este in `parent_id`; directoarele nodurilor stau toate direct in `nodes/`, deci o mutare nu atinge discul
in afara de `node.json`, iar adancimea ierarhiei nu mai e limitata de lungimea caii Windows.
"""

from __future__ import annotations

import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any

from ..domain.common import fmt_utc, utcnow
from ..domain.models import Kind
from ..domain.session import OperationRecord
from ..errors import CycleError, NotFoundError, StorageError, ValidationError
from .atomic import atomic_write_json, read_json
from .paths import MAX_PATH, clean_abs, ensure_path_fits, is_reparse_point, physical_dirname, walk_no_links
from .repository import WorkspaceRepository

log = logging.getLogger(__name__)


# ---- helpers ---------------------------------------------------------

def descendants(repo: WorkspaceRepository, node_id: str, include_self: bool = True) -> list[str]:
    children: dict[str | None, list[str]] = {}
    for n in repo.nodes.values():
        children.setdefault(n.parent_id, []).append(n.id)
    out: list[str] = [node_id] if include_self else []
    stack = list(children.get(node_id, []))
    seen = {node_id}
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        out.append(cur)
        stack.extend(children.get(cur, []))
    return out


def _max_relative_length(directory: Path) -> int:
    longest = 0
    base = clean_abs(directory)
    for dirpath, _dirs, files in walk_no_links(directory):
        rel_dir = len(clean_abs(dirpath)) - len(base)
        longest = max(longest, rel_dir)
        for f in files:
            longest = max(longest, rel_dir + 1 + len(f))
    return longest


def _apply_node_patch(node_dir: Path, patch: dict[str, Any] | None) -> None:
    """Idempotent: aplica campurile din `patch` peste node.json daca nu sunt deja acolo."""
    if not patch:
        return
    path = node_dir / "node.json"
    data, _, _ = read_json(path)
    if all(data.get(k) == v for k, v in patch.items()):
        return
    data.update(patch)
    data["revision"] = int(data.get("revision", 1)) + 1
    data["updated_at"] = fmt_utc(utcnow())
    atomic_write_json(path, data)


def _new_op(repo: WorkspaceRepository, op_type: str, data: dict[str, Any]) -> OperationRecord:
    op = OperationRecord(type=op_type, data=data)
    repo.operations.save(op)
    return op


def _step(repo: WorkspaceRepository, op: OperationRecord, name: str) -> None:
    op.steps_done.append(name)
    op.updated_at = utcnow()
    repo.operations.save(op)


def _finish(repo: WorkspaceRepository, op: OperationRecord, state: str = "done", error: str | None = None) -> None:
    op.state = state  # type: ignore[assignment]
    op.error = error
    op.updated_at = utcnow()
    repo.operations.save(op)


def _move_dir(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    # Antivirus/OneDrive/indexarea pot bloca scurt un director proaspat scris: reincercam cu pauze mici.
    last: OSError | None = None
    for attempt in range(8):
        try:
            os.rename(src, dst)
            return
        except PermissionError as exc:
            last = exc
            time.sleep(0.05 * (attempt + 1))
        except OSError as exc:
            raise StorageError(f"Mutarea directorului a eșuat: {exc}") from exc
    raise StorageError(f"Mutarea directorului a eșuat (acces refuzat, posibil blocat de alt proces): {last}") from last


# ---- move ------------------------------------------------------------

def move_node(repo: WorkspaceRepository, node_id: str, new_parent_id: str | None,
              sort_order: int | None = None) -> None:
    repo._require_writable()
    node = repo.nodes.get(node_id)
    if node is None:
        raise NotFoundError("Nodul nu există.")
    if new_parent_id is not None and new_parent_id not in repo.nodes:
        raise NotFoundError("Destinația nu există.")
    if new_parent_id in descendants(repo, node_id):
        raise CycleError("Nu poți muta un nod în interiorul propriilor descendenți.")
    changes: dict[str, Any] = {"parent_id": new_parent_id}
    if sort_order is not None:
        changes["sort_order"] = sort_order
    if all(getattr(node, k) == v for k, v in changes.items()):
        return
    repo.write_node(node.model_copy(update=changes))  # o singura scriere atomica; nimic de recuperat


# ---- trash -----------------------------------------------------------

def _rollback_moves(done: list[tuple[str, str]]) -> None:
    for src, dst in reversed(done):
        try:
            _move_dir(Path(dst), Path(src))
        except Exception:  # best effort: ramane jurnalul operatiei pentru recuperare
            log.exception("Anularea mutarii %s -> %s a eșuat", dst, src)


def trash_node(repo: WorkspaceRepository, node_id: str) -> None:
    repo._require_writable()
    node = repo.nodes.get(node_id)
    if node is None:
        raise NotFoundError("Nodul nu există.")
    ids = descendants(repo, node_id)
    entry = repo.trash_dir / node_id
    moves = [(str(repo.dirs[i]), str(entry / "nodes" / repo.dirs[i].name)) for i in ids]
    for i, (_src, dst) in zip(ids, moves):
        ensure_path_fits(dst, reserve=_max_relative_length(repo.dirs[i]))
    manifest = {
        "node_id": node_id, "title": node.title, "kind": node.kind.value, "parent_id": node.parent_id,
        "layout": "flat", "dirname": repo.dirs[node_id].name, "dirnames": {i: repo.dirs[i].name for i in ids},
        "trashed_at": fmt_utc(utcnow()), "node_ids": ids, "titles": {i: repo.nodes[i].title for i in ids},
    }
    op = _new_op(repo, "trash_node", {"node_id": node_id, "moves": moves, "manifest_dir": str(entry)})
    done: list[tuple[str, str]] = []
    try:
        atomic_write_json(entry / "manifest.json", manifest, keep_backup=False)
        _step(repo, op, "manifest_written")
        for src, dst in moves:
            _move_dir(Path(src), Path(dst))
            done.append((src, dst))
        _step(repo, op, "dirs_moved")
    except Exception as exc:
        _rollback_moves(done)
        shutil.rmtree(entry, ignore_errors=True)
        _finish(repo, op, "failed", str(exc))
        raise
    repo.forget_subtree(ids)
    _finish(repo, op)


def _trash_dirs(entry: Path, data: dict[str, Any]) -> dict[str, Path]:
    """Directoarele nodurilor dintr-o intrare de coș: layout plat (nou) sau subarbore imbricat (vechi)."""
    if data.get("layout") == "flat":
        return {i: entry / "nodes" / name for i, name in data["dirnames"].items()}
    return {data["node_id"]: entry / data["dirname"]}


def list_trash(repo: WorkspaceRepository) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not repo.trash_dir.exists():
        return out
    for entry in sorted(repo.trash_dir.iterdir()):
        mf = entry / "manifest.json"
        if entry.is_dir() and mf.is_file():
            try:
                data, _, _ = read_json(mf)
                if all(d.exists() for d in _trash_dirs(entry, data).values()):
                    out.append(data)
            except Exception as exc:  # manifest corupt: raportat, nu sters
                log.warning("Manifest coș invalid %s: %s", mf, exc)
    return out


def restore_node(repo: WorkspaceRepository, node_id: str, new_parent_id: str | None = ...) -> str | None:  # type: ignore[assignment]
    """Restaureaza din cos. Intoarce parintele efectiv (originalul daca mai exista, altfel radacina)."""
    repo._require_writable()
    entry = repo.trash_dir / node_id
    data, _, _ = read_json(entry / "manifest.json")
    if new_parent_id is ...:
        new_parent_id = data.get("parent_id")
    if new_parent_id is not None and new_parent_id not in repo.nodes:
        new_parent_id = None
    clash = [i for i in data["node_ids"] if i in repo.nodes]
    if clash:
        raise ValidationError("Există deja noduri cu aceleași UUID-uri în workspace.")
    sources = _trash_dirs(entry, data)
    moves = [(str(src), str(repo.nodes_dir / src.name)) for src in sources.values()]
    for src, dst in moves:
        if Path(dst).exists():
            raise StorageError("La destinație există deja un director cu același nume.")
        if len(clean_abs(dst)) + _max_relative_length(Path(src)) > MAX_PATH:
            raise StorageError("Restaurarea ar depăși limita de cale Windows.")
    root_dst = repo.nodes_dir / data["dirname"]
    patch = {"parent_id": new_parent_id}
    op = _new_op(repo, "restore_node", {
        "node_id": node_id, "moves": moves, "patch_dir": str(root_dst), "patch": patch, "manifest_dir": str(entry),
    })
    done: list[tuple[str, str]] = []
    try:
        for src, dst in moves:
            _move_dir(Path(src), Path(dst))
            done.append((src, dst))
        _step(repo, op, "dirs_moved")
        _apply_node_patch(root_dst, patch)
        _step(repo, op, "json_updated")
    except Exception as exc:
        if "json_updated" not in op.steps_done:
            _rollback_moves(done)
        _finish(repo, op, "failed", str(exc))
        raise
    shutil.rmtree(entry, ignore_errors=True)
    loaded = [Path(dst) for _src, dst in moves]
    if data.get("layout") != "flat":
        loaded += flatten_subtree(repo, root_dst)  # intrare veche din coș: subarbore imbricat
    for d in loaded:
        repo.load_node_dir(d)
    _finish(repo, op)
    return new_parent_id


def purge_trash_entry(repo: WorkspaceRepository, node_id: str) -> None:
    repo._require_writable()
    shutil.rmtree(repo.trash_dir / node_id)


# ---- layout vechi (children/) -----------------------------------------

def flatten_subtree(repo: WorkspaceRepository, node_dir: Path) -> list[Path]:
    """Muta copiii imbricati (layout vechi `children/`) direct în `nodes/`. Intoarce directoarele mutate."""
    moved: list[Path] = []
    stack = [node_dir]
    while stack:
        children = stack.pop() / "children"
        if not children.is_dir() or is_reparse_point(children):
            continue
        for child in sorted(children.iterdir()):
            if (not child.is_dir() or is_reparse_point(child) or child.name.startswith(".")
                    or not (child / "node.json").is_file()):
                continue
            dst = repo.nodes_dir / child.name
            if dst.exists():
                log.warning("Nu pot aplatiza %s: %s exista deja; ramane imbricat.", child, dst)
                continue
            _move_dir(child, dst)
            moved.append(dst)
            stack.append(dst)
        try:
            children.rmdir()  # doar daca e gol
        except OSError:
            pass
    return moved


def flatten_layout(repo: WorkspaceRepository) -> int:
    """Aduce un workspace cu layout vechi (noduri in `children/`) la layout plat. Idempotent; intoarce nr. de directoare."""
    if repo.read_only or not repo.nodes_dir.exists():
        return 0
    total = 0
    for top in sorted(repo.nodes_dir.iterdir()):
        if top.is_dir() and not is_reparse_point(top) and not top.name.startswith("."):
            total += len(flatten_subtree(repo, top))
    return total


# ---- redenumire fizica explicita -------------------------------------

def rename_physical_dir(repo: WorkspaceRepository, node_id: str) -> Path:
    """Aliniaza numele directorului cu titlul curent (UUID-ul ramane neschimbat)."""
    repo._require_writable()
    node = repo.nodes[node_id]
    old_dir = repo.dirs[node_id]
    new_dir = old_dir.parent / physical_dirname(node.title, node.id)
    if os.path.normcase(str(new_dir)) == os.path.normcase(str(old_dir)):
        return old_dir
    if new_dir.exists():
        raise StorageError("Există deja un director cu acest nume.")
    deepest = len(clean_abs(new_dir)) + _max_relative_length(old_dir)
    if deepest > MAX_PATH:
        raise StorageError("Redenumirea ar depăși limita de cale Windows.")
    op = _new_op(repo, "rename_dir", {"node_id": node_id, "old_dir": str(old_dir), "new_dir": str(new_dir)})
    try:
        _move_dir(old_dir, new_dir)
        _step(repo, op, "dir_moved")
    except Exception as exc:
        _finish(repo, op, "failed", str(exc))
        raise
    repo.note_dir_relocated(node_id, new_dir)
    _finish(repo, op)
    return new_dir


# ---- recuperare la pornire -------------------------------------------

def _recover_multi_move(repo: WorkspaceRepository, op: OperationRecord) -> str:
    """Coș/restaurare cu mai multe directoare: anuleaza daca nimic nu s-a mutat, altfel termina mutarile ramase."""
    d = op.data
    pairs = [(Path(s), Path(t)) for s, t in d["moves"]]
    pending = [(s, t) for s, t in pairs if s.exists() and not t.exists()]
    moved = [(s, t) for s, t in pairs if t.exists() and not s.exists()]
    if len(pending) + len(moved) != len(pairs):
        _finish(repo, op, "failed", "stare ambiguă (ambele directoare există sau lipsesc)")
        return f"Operația {op.type} necesită verificare manuală: stare ambiguă."
    if not moved:
        if op.type == "trash_node" and d.get("manifest_dir"):
            shutil.rmtree(d["manifest_dir"], ignore_errors=True)
        _finish(repo, op, "rolled_back", "directoarele nu fuseseră mutate")
        return f"Operația {op.type} întreruptă a fost anulată (nimic mutat)."
    for s, t in pending:
        _move_dir(s, t)
    if op.type == "restore_node":
        _apply_node_patch(Path(d["patch_dir"]), d.get("patch"))
        if d.get("manifest_dir"):
            shutil.rmtree(d["manifest_dir"], ignore_errors=True)
    _finish(repo, op)
    return f"Operația {op.type} întreruptă a fost finalizată."


def recover_pending(repo: WorkspaceRepository) -> list[str]:
    """Finalizeaza sau anuleaza sigur operatiile intrerupte. Ruleaza INAINTE de `repo.load()`."""
    messages: list[str] = []
    if repo.read_only:
        return messages
    for op in repo.operations.list_all():
        if op.state != "pending":
            continue
        if op.type not in {"move_node", "trash_node", "restore_node", "rename_dir"}:
            continue  # alte tipuri (calendar) sunt reconciliate de serviciile lor
        d = op.data
        try:
            if "moves" in d:
                messages.append(_recover_multi_move(repo, op))
                continue
            old_dir, new_dir = Path(d.get("old_dir", "")), Path(d.get("new_dir", ""))
            if not d.get("old_dir"):
                _finish(repo, op, "failed", "operație fără directoare")
                continue
            old_exists, new_exists = old_dir.exists(), new_dir.exists()
            if new_exists and not old_exists:
                _apply_node_patch(new_dir, d.get("patch"))
                if op.type == "restore_node" and d.get("manifest_dir"):
                    shutil.rmtree(d["manifest_dir"], ignore_errors=True)
                _finish(repo, op)
                messages.append(f"Operația {op.type} întreruptă a fost finalizată.")
            elif old_exists and not new_exists:
                if op.type == "trash_node" and d.get("manifest_dir"):
                    shutil.rmtree(d["manifest_dir"], ignore_errors=True)
                _finish(repo, op, "rolled_back", "directorul nu fusese mutat")
                messages.append(f"Operația {op.type} întreruptă a fost anulată (nimic mutat).")
            else:
                _finish(repo, op, "failed", "stare ambiguă (ambele directoare există sau lipsesc)")
                messages.append(f"Operația {op.type} necesită verificare manuală: stare ambiguă.")
        except Exception as exc:
            log.exception("Recuperarea operației %s a eșuat", op.id)
            _finish(repo, op, "failed", str(exc))
            messages.append(f"Recuperarea operației {op.type} a eșuat: {exc}")
    return messages
