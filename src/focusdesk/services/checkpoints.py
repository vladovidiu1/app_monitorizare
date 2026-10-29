"""Checkpoint-uri de fisiere: ZIP + manifest SHA-256, diff si restaurare sigura."""

from __future__ import annotations

from ..i18n import tr

import difflib
import fnmatch
import hashlib
import logging
import os
import time
import uuid
import zipfile
from pathlib import Path
from typing import Callable

from ..domain.checkpoint import CheckpointFile, CheckpointManifest
from ..domain.common import fmt_utc, utcnow
from ..domain.models import Kind
from ..domain.settings import CheckpointSettings
from ..errors import NotFoundError, StorageError, ValidationError
from ..storage.atomic import atomic_write_json, dump_json, read_json
from ..storage.paths import clean_abs, is_reparse_point, is_within, walk_no_links
from ..storage.ziputil import validate_member_name
from ..workers.bridge import CancelToken
from .files import FileService
from .workspace import Workspace

log = logging.getLogger(__name__)

Progress = Callable[[int, int], None]
ZIP_PREFIX = "files/"


class SourceChangedDuringCapture(StorageError):
    pass


def _excluded(name: str, patterns: list[str]) -> bool:
    low = name.lower()
    return any(fnmatch.fnmatch(low, p.lower()) for p in patterns)


def list_included(source: Path, cfg: CheckpointSettings) -> tuple[list[tuple[str, Path, os.stat_result]], int, list[str]]:
    """Fisierele incluse (fara linkuri, fara excluderi). Intoarce (fisiere, nr_excluse, prea_mari)."""
    files: list[tuple[str, Path, os.stat_result]] = []
    excluded = 0
    large: list[str] = []
    max_file = cfg.max_file_mb * 1024 * 1024
    for dirpath, dirnames, filenames in walk_no_links(source):
        keep = []
        for d in dirnames:
            if _excluded(d, cfg.exclude_names):
                excluded += 1
            else:
                keep.append(d)
        dirnames[:] = keep
        for fn in filenames:
            if _excluded(fn, cfg.exclude_names):
                excluded += 1
                continue
            p = Path(dirpath) / fn
            try:
                st = p.stat()
            except OSError:
                continue
            rel = p.relative_to(source).as_posix()
            if st.st_size > max_file:
                large.append(rel)
                continue
            files.append((rel, p, st))
    files.sort(key=lambda t: t[0])
    return files, excluded, large


def preview_included(source: Path, cfg: CheckpointSettings, limit: int = 2000) -> dict:
    files, excluded, large = list_included(source, cfg)
    return {
        "count": len(files), "total_size": sum(st.st_size for _, _, st in files),
        "excluded": excluded, "too_large": large, "sample": [r for r, _, _ in files[:limit]],
    }


class CheckpointService:
    def __init__(self, ws: Workspace) -> None:
        self.ws = ws
        self.files = FileService(ws)

    # ---- listing ----------------------------------------------------
    def snapshots_dir(self, owner_id: str) -> Path:
        return self.ws.node_dir(owner_id) / "snapshots"

    def list_for_owner(self, owner_id: str) -> list[CheckpointManifest]:
        out: list[tuple[CheckpointManifest, int]] = []
        d = self.snapshots_dir(owner_id)
        if not d.exists():
            return []
        for p in d.glob("*.json"):
            try:
                data, _, _ = read_json(p)
                m = CheckpointManifest.model_validate(data)
                if m.complete and (d / m.archive).exists():
                    out.append((m, p.stat().st_mtime_ns))
            except Exception as exc:
                log.warning("Manifest checkpoint invalid %s: %s", p, exc)
        out.sort(key=lambda t: (t[0].created_at, t[1]), reverse=True)
        return [m for m, _ in out]

    def list_for_node(self, node_id: str) -> list[CheckpointManifest]:
        return self.list_for_owner(self.files.checkpoint_owner(node_id))

    def get(self, node_id: str, checkpoint_id: str) -> CheckpointManifest:
        for m in self.list_for_node(node_id):
            if m.id == checkpoint_id:
                return m
        raise NotFoundError(tr('services.checkpoints.checkpoint_ul_nu_exista'))

    # ---- create -----------------------------------------------------
    def create(self, node_id: str, description: str = "", *, trigger: str = "manual", session_id: str | None = None,
               force: bool = False, cancel: CancelToken | None = None, progress: Progress | None = None,
               missed_note: str | None = None) -> CheckpointManifest | None:
        """Creeaza un checkpoint. Intoarce None daca nimic nu s-a schimbat de la ultimul."""
        self.ws.repo._require_writable()
        src = self.files.effective_source(node_id)
        if src is None:
            raise ValidationError(tr('services.checkpoints.nu_exista_un_folder_de_cod_asociat_acestui_nod_sau_unui_parinte'))
        if not src.path.is_dir():
            raise NotFoundError(tr('services.checkpoints.folderul_de_cod_nu_exista', src_path=src.path))
        cfg = self.ws.settings.checkpoints
        files, excluded, large = list_included(src.path, cfg)
        total = sum(st.st_size for _, _, st in files)
        if total > cfg.max_total_mb * 1024 * 1024:
            raise StorageError(
                tr('services.checkpoints.sursa_mb_depaseste_limita_de_mb_adauga_excluderi_sau_mareste_limita_in', total_1024_1024=total // 1024 // 1024, cfg_max_total_mb=cfg.max_total_mb)
            )
        previous = (self.list_for_owner(src.owner_id) or [None])[0]
        if previous is not None and not force and self._quick_same(previous, files):
            return None
        snap_dir = self.snapshots_dir(src.owner_id)
        snap_dir.mkdir(parents=True, exist_ok=True)
        cid = str(uuid.uuid4())
        tmp = snap_dir / f".{cid}.zip.part"
        entries: list[CheckpointFile] = []
        try:
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
                for i, (rel, path, st0) in enumerate(files):
                    if cancel:
                        cancel.check()
                    entries.append(self._add_file(zf, rel, path, st0))
                    if progress:
                        progress(i + 1, len(files))
                self._verify_unchanged(src.path, cfg, files)
                node = self.ws.get(node_id)
                project = self.ws.nearest_project(node_id)
                manifest = CheckpointManifest(
                    id=cid, node_id=node_id, owner_node_id=src.owner_id, project_id=project.id if project else None,
                    session_id=session_id, description=description.strip(), trigger=trigger,  # type: ignore[arg-type]
                    source_root=str(src.path), files=entries, total_size=sum(e.size for e in entries),
                    excluded_count=excluded, skipped_large=large, archive=f"{cid}.zip", scheduled_missed=missed_note,
                )
                zf.writestr("manifest.json", dump_json(manifest.model_dump(mode="json")))
            if previous is not None and not force and previous.signature() == manifest.signature():
                tmp.unlink(missing_ok=True)
                return None
            os.replace(tmp, snap_dir / manifest.archive)
            atomic_write_json(snap_dir / f"{cid}.json", manifest.model_dump(mode="json"), keep_backup=False)
        except BaseException:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        self._apply_retention(src.owner_id, cfg.retention)
        self.ws.record_event("checkpoint", node_id, {"checkpoint_id": cid, "trigger": trigger,
                                                    "files": len(entries)})
        return manifest

    @staticmethod
    def _quick_same(prev: CheckpointManifest, files: list[tuple[str, Path, os.stat_result]]) -> bool:
        old = {f.path: (f.size, f.mtime_ns) for f in prev.files}
        new = {rel: (st.st_size, st.st_mtime_ns) for rel, _, st in files}
        return old == new

    @staticmethod
    def _add_file(zf: zipfile.ZipFile, rel: str, path: Path, st0: os.stat_result) -> CheckpointFile:
        h = hashlib.sha256()
        info = zipfile.ZipInfo(ZIP_PREFIX + rel, date_time=time.localtime(st0.st_mtime)[:6])
        info.compress_type = zipfile.ZIP_DEFLATED
        size = 0
        try:
            with open(path, "rb") as src, zf.open(info, "w") as out:
                while chunk := src.read(1024 * 1024):
                    h.update(chunk)
                    size += len(chunk)
                    out.write(chunk)
            st1 = path.stat()
        except OSError as exc:
            raise SourceChangedDuringCapture(tr('services.checkpoints.fisierul_nu_a_putut_fi_citit', rel=rel, exc=exc)) from exc
        if st1.st_size != st0.st_size or st1.st_mtime_ns != st0.st_mtime_ns or size != st0.st_size:
            raise SourceChangedDuringCapture(
                tr('services.checkpoints.fisierul_s_a_modificat_in_timpul_capturii_salveaza_in_editor_si_reince', rel=rel)
            )
        return CheckpointFile(path=rel, size=size, sha256=h.hexdigest(), mtime_ns=st0.st_mtime_ns)

    @staticmethod
    def _verify_unchanged(source: Path, cfg: CheckpointSettings, before: list) -> None:
        after, _, _ = list_included(source, cfg)
        a = {(rel, st.st_size, st.st_mtime_ns) for rel, _, st in before}
        b = {(rel, st.st_size, st.st_mtime_ns) for rel, _, st in after}
        if a != b:
            raise SourceChangedDuringCapture(
                tr('services.checkpoints.sursa_s_a_modificat_in_timpul_capturii_fisiere_adaugate_sterse_modific')
            )

    def _apply_retention(self, owner_id: str, keep: int) -> None:
        items = self.list_for_owner(owner_id)
        for m in items[max(1, keep):]:
            d = self.snapshots_dir(owner_id)
            (d / m.archive).unlink(missing_ok=True)
            (d / f"{m.id}.json").unlink(missing_ok=True)

    # ---- diff -------------------------------------------------------
    def diff_current(self, manifest: CheckpointManifest, cancel: CancelToken | None = None) -> dict[str, list[str]]:
        """Compara checkpoint-ul cu starea curenta a sursei: noi / modificate / sterse."""
        source = Path(manifest.source_root)
        if not source.is_dir():
            raise NotFoundError(tr('services.checkpoints.folderul_sursa_nu_exista', source=source))
        cfg = self.ws.settings.checkpoints
        files, _, _ = list_included(source, cfg)
        old = {f.path: f for f in manifest.files}
        new_l, mod_l = [], []
        seen = set()
        for rel, path, st in files:
            if cancel:
                cancel.check()
            seen.add(rel)
            prev = old.get(rel)
            if prev is None:
                new_l.append(rel)
            elif prev.size != st.st_size or prev.mtime_ns != st.st_mtime_ns:
                if _sha256_file(path) != prev.sha256:
                    mod_l.append(rel)
        deleted = sorted(set(old) - seen)
        return {"new": sorted(new_l), "modified": sorted(mod_l), "deleted": deleted}

    @staticmethod
    def diff_manifests(old: CheckpointManifest, new: CheckpointManifest) -> dict[str, list[str]]:
        a = {f.path: f.sha256 for f in old.files}
        b = {f.path: f.sha256 for f in new.files}
        return {
            "new": sorted(set(b) - set(a)),
            "modified": sorted(p for p in set(a) & set(b) if a[p] != b[p]),
            "deleted": sorted(set(a) - set(b)),
        }

    def text_diff(self, manifest: CheckpointManifest, rel_path: str, *, max_bytes: int = 200_000,
                  max_lines: int = 3000) -> str:
        """Diff unificat intre versiunea din checkpoint si fisierul curent; limitat ca marime."""
        owner_dir = self.snapshots_dir(manifest.owner_node_id)
        member = validate_member_name(ZIP_PREFIX + rel_path).as_posix()
        with zipfile.ZipFile(owner_dir / manifest.archive) as zf:
            try:
                info = zf.getinfo(member)
            except KeyError:
                old_bytes = b""
            else:
                if info.file_size > max_bytes:
                    return tr('services.checkpoints.fisier_prea_mare_pentru_diff_kb_kb', info_file_size_1024=info.file_size // 1024, max_bytes_1024=max_bytes // 1024)
                old_bytes = zf.read(member)
        cur_path = Path(manifest.source_root) / rel_path
        if not is_within(manifest.source_root, cur_path):
            raise ValidationError(tr('services.checkpoints.cale_invalida'))
        new_bytes = b""
        if cur_path.is_file() and not is_reparse_point(cur_path):
            if cur_path.stat().st_size > max_bytes:
                return tr('services.checkpoints.fisier_curent_prea_mare_pentru_diff_kb', cur_path_stat_st_size_1024=cur_path.stat().st_size // 1024)
            new_bytes = cur_path.read_bytes()
        if b"\x00" in old_bytes[:8192] or b"\x00" in new_bytes[:8192]:
            return tr('services.checkpoints.fisier_binar_fara_diff_text')
        a = old_bytes.decode("utf-8", errors="replace").splitlines()
        b = new_bytes.decode("utf-8", errors="replace").splitlines()
        lines = list(difflib.unified_diff(a, b, "checkpoint/" + rel_path, "curent/" + rel_path, lineterm=""))
        if len(lines) > max_lines:
            lines = lines[:max_lines] + [tr('extra.services.checkpoints.diff_trunchiat_la_linii', max_lines=max_lines)]
        return "\n".join(lines) if lines else tr('services.checkpoints.fara_diferente_de_text')

    # ---- restore ----------------------------------------------------
    def restore(self, manifest: CheckpointManifest, dest: Path, *, overwrite_source: bool = False,
                cancel: CancelToken | None = None) -> Path:
        """Restaureaza intr-un folder separat (implicit). `overwrite_source=True` creeaza intai o copie de siguranta."""
        dest = Path(dest)
        owner_dir = self.snapshots_dir(manifest.owner_node_id)
        zip_path = owner_dir / manifest.archive
        if not zip_path.exists():
            raise NotFoundError(tr('services.checkpoints.arhiva_checkpoint_ului_lipseste'))
        source_root = Path(manifest.source_root)
        if overwrite_source:
            if os.path.normcase(clean_abs(dest)) != os.path.normcase(clean_abs(source_root)):
                raise ValidationError(tr('services.checkpoints.suprascrierea_este_permisa_doar_peste_folderul_sursa_al_checkpoint_ulu'))
            if source_root.is_dir():
                self.create(manifest.node_id, tr('services.checkpoints.copie_de_siguranta_inainte_de_restaurare'), trigger="pre_restore",
                            force=True)
        else:
            if is_within(source_root, dest) or is_within(dest, source_root):
                raise ValidationError(tr('services.checkpoints.restaureaza_intr_un_folder_separat_in_afara_folderului_sursa'))
            if dest.exists() and any(dest.iterdir()):
                raise ValidationError(tr('services.checkpoints.folderul_de_destinatie_trebuie_sa_fie_gol'))
        expected = {f.path: f for f in manifest.files}
        dest.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as zf:
            names = [i for i in zf.infolist() if i.filename.startswith(ZIP_PREFIX) and not i.is_dir()]
            for info in names:
                validate_member_name(info.filename)
            for info in names:
                if cancel:
                    cancel.check()
                rel = info.filename[len(ZIP_PREFIX):]
                target = Path(clean_abs(dest / rel))
                if not is_within(dest, target):
                    raise ValidationError(tr('services.checkpoints.intrare_nesigura_in_arhiva', info_filename=info.filename))
                target.parent.mkdir(parents=True, exist_ok=True)
                tmp = target.with_name(f".{target.name}.{uuid.uuid4().hex[:6]}.restoring")
                h = hashlib.sha256()
                with zf.open(info) as src, open(tmp, "wb") as out:
                    while chunk := src.read(1024 * 1024):
                        h.update(chunk)
                        out.write(chunk)
                exp = expected.get(rel)
                if exp is not None and exp.sha256 != h.hexdigest():
                    tmp.unlink(missing_ok=True)
                    raise StorageError(tr('services.checkpoints.suma_de_control_invalida_pentru_arhiva_pare_corupta', rel=rel))
                os.replace(tmp, target)
        return dest

    def default_restore_dir(self, manifest: CheckpointManifest) -> Path:
        src = Path(manifest.source_root)
        stamp = manifest.created_at.strftime("%Y%m%d-%H%M%S")
        return src.parent / f"{src.name}--restaurat-{stamp}"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()
