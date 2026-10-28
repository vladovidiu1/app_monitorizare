"""Tabul „Versiuni”: checkpoint-uri de cod, comparatie, restaurare si (optional) Git."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, ttk
from typing import TYPE_CHECKING

import ttkbootstrap as tb

from ..domain.checkpoint import CheckpointManifest
from ..domain.models import Kind, Node
from ..errors import FocusDeskError
from ..services.checkpoints import CheckpointService, preview_included
from .common import ModalDialog, ask_choice, confirm, error_color, make_tree, muted_color, show_error, show_info
from .inspector import InspectorTab

if TYPE_CHECKING:
    from .app import FocusDeskApp

TRIGGER_TEXT = {"manual": "Manual", "session_end": "Final de sesiune", "scheduled": "Programat",
                "pre_restore": "Înainte de restaurare", "startup": "La pornire"}


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return str(n)


class IncludedFilesDialog(ModalDialog):
    def __init__(self, parent: tk.Misc, info: dict, root: str) -> None:
        super().__init__(parent, "Fișiere incluse în checkpoint", resizable=True, ok_text="Închide",
                         cancel_text="Închide")
        self.ok_btn.pack_forget()
        ttk.Label(self.body, text=root, style="Muted.TLabel", wraplength=520).pack(anchor="w")
        ttk.Label(self.body, text=(f"{info['count']} fișiere, {human_size(info['total_size'])}; "
                                   f"{info['excluded']} elemente excluse automat."), style="Section.TLabel").pack(
            anchor="w", pady=(4, 6))
        if info["too_large"]:
            ttk.Label(self.body, foreground=error_color(self), wraplength=520,
                      text=f"{len(info['too_large'])} fișiere depășesc limita pe fișier și NU sunt incluse: "
                           + ", ".join(info["too_large"][:5])).pack(anchor="w")
        box = tk.Text(self.body, width=70, height=18, wrap="none", font=("Consolas", 9))
        box.pack(fill="both", expand=True, pady=6)
        box.insert("1.0", "\n".join(info["sample"]))
        box.configure(state="disabled")


class GitCommitDialog(ModalDialog):
    """Commit manual: mesaj propus (editabil) si lista de fisiere de ales explicit (fara `git add .`)."""

    def __init__(self, parent: tk.Misc, entries: list, message: str) -> None:
        super().__init__(parent, "Commit Git manual", resizable=True, ok_text="Creează commit")
        self.geometry("640x520")
        ttk.Label(self.body, wraplength=580, style="Muted.TLabel", text=(
            "Se rulează `git add -- <fișierele alese>` și `git commit` doar pentru ele. Nu se face push, reset, stash "
            "sau checkout. Fișierele necomisește noi (??) nu sunt selectate implicit.")).pack(anchor="w")
        self.tv, frame = make_tree(self.body, [("code", "Stare", 60), ("path", "Fișier", 480)], height=10,
                                   selectmode="extended")
        frame.pack(fill="both", expand=True, pady=6)
        for i, e in enumerate(entries):
            self.tv.insert("", "end", iid=str(i), values=(e.code.strip() or e.code, e.path))
            if not e.untracked:
                self.tv.selection_add(str(i))
        self._entries = entries
        ttk.Label(self.body, text="Mesaj").pack(anchor="w")
        self.msg = tk.Text(self.body, height=5, wrap="word", font="TkTextFont")
        self.msg.pack(fill="x")
        self.msg.insert("1.0", message)

    def validate(self) -> bool:
        if not self.tv.selection():
            show_error(self, "Alege cel puțin un fișier.")
            return False
        if not self.msg.get("1.0", "end").strip():
            show_error(self, "Mesajul este obligatoriu.")
            return False
        return True

    def collect(self):
        files = [self._entries[int(i)].path for i in self.tv.selection()]
        return self.msg.get("1.0", "end").strip(), files


class VersionsTab(InspectorTab):
    title = "Versiuni"

    def __init__(self, parent: tk.Misc, app: "FocusDeskApp") -> None:
        super().__init__(parent, app)
        self._manifests: dict[str, CheckpointManifest] = {}
        self.info = ttk.Label(self, text="", style="Muted.TLabel", wraplength=410, justify="left")
        self.info.pack(anchor="w", padx=8, pady=(8, 4))
        top = ttk.Frame(self)
        top.pack(fill="x", padx=8)
        self.desc_var = tk.StringVar()
        self.desc_entry = ttk.Entry(top, textvariable=self.desc_var)
        self.desc_entry.pack(side="left", fill="x", expand=True)
        self.save_btn = tb.Button(top, text="Salvează checkpoint", command=self._create, bootstyle="primary")
        self.save_btn.pack(side="left", padx=(6, 0))
        self.tv, frame = make_tree(self, [("when", "Data", 110), ("task", "Task", 100), ("trig", "Declanșator", 90),
                                          ("files", "Fișiere", 50), ("size", "Mărime", 65), ("desc", "Descriere", 120)],
                                   height=6)
        frame.pack(fill="both", expand=True, padx=8, pady=6)
        r1 = ttk.Frame(self)
        r1.pack(fill="x", padx=8)
        ttk.Button(r1, text="Compară cu curentul", command=self._diff_current).pack(side="left", padx=2)
        ttk.Button(r1, text="Compară cu anteriorul", command=self._diff_previous).pack(side="left", padx=2)
        ttk.Button(r1, text="Fișiere incluse…", command=self._preview).pack(side="left", padx=2)
        r2 = ttk.Frame(self)
        r2.pack(fill="x", padx=8, pady=(4, 0))
        ttk.Button(r2, text="Restaurează în folder separat…", command=self._restore_separate).pack(side="left", padx=2)
        self.overwrite_btn = ttk.Button(r2, text="Suprascrie sursa…", command=self._restore_overwrite)
        self.overwrite_btn.pack(side="left", padx=2)
        self.changes = ttk.Treeview(self, columns=("kind", "path"), show="headings", height=5, selectmode="browse")
        self.changes.heading("kind", text="Modificare")
        self.changes.heading("path", text="Fișier")
        self.changes.column("kind", width=90, stretch=False)
        self.changes.column("path", width=300)
        self.changes.pack(fill="x", padx=8, pady=(8, 2))
        self.changes.bind("<<TreeviewSelect>>", self._show_text_diff)
        dwrap = ttk.Frame(self)
        dwrap.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.diff_text = tk.Text(dwrap, height=8, wrap="none", font=("Consolas", 9), state="disabled")
        sb = ttk.Scrollbar(dwrap, orient="vertical", command=self.diff_text.yview)
        self.diff_text.configure(yscrollcommand=sb.set)
        self.diff_text.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.diff_text.tag_configure("add", foreground="#2e7d32")
        self.diff_text.tag_configure("del", foreground="#c0392b")
        self._diff_manifest: CheckpointManifest | None = None
        self.git_frame: ttk.Frame | None = None
        self._build_git()

    def _build_git(self) -> None:
        """Sectiune Git optionala: status, log, commit MANUAL cu fisiere alese explicit."""
        self.git_frame = ttk.LabelFrame(self, text="Git (opțional)")
        self.git_frame.pack(fill="x", padx=8, pady=(4, 8))
        self.git_lbl = ttk.Label(self.git_frame, text="", style="Muted.TLabel", wraplength=400, justify="left")
        self.git_lbl.pack(anchor="w", padx=6, pady=(4, 2))
        self.git_tv, frame = make_tree(self.git_frame, [("h", "Commit", 60), ("when", "Data", 100), ("who", "Autor", 80),
                                                         ("msg", "Mesaj", 170)], height=4)
        frame.pack(fill="x", padx=6)
        row = ttk.Frame(self.git_frame)
        row.pack(fill="x", padx=6, pady=4)
        self.git_btns = [
            ttk.Button(row, text="Reîmprospătează", command=self._refresh_git),
            ttk.Button(row, text="Commit manual…", command=self._git_commit),
            ttk.Button(row, text="Doar din sesiunile task-ului", command=self._git_filter),
        ]
        for b in self.git_btns:
            b.pack(side="left", padx=2)
        self._git_folder = None
        self._git_commits: list = []
        self._git_entries: list = []

    def _set_git_enabled(self, on: bool) -> None:
        for b in self.git_btns:
            b.state(["!disabled"] if on else ["disabled"])

    def _refresh_git(self) -> None:
        from ..integrations import git

        self.git_tv.delete(*self.git_tv.get_children())
        self._git_commits, self._git_entries, self._git_folder = [], [], None
        if not self.node_id:
            return
        src = self.app.files.usable_source_dir(self.node_id)
        if src is None:
            self.git_lbl.configure(text="Fara folder de cod: Git indisponibil.")
            self._set_git_enabled(False)
            return
        if git.find_git() is None:
            self.git_lbl.configure(text="Git nu a fost găsit în PATH (opțional). Checkpoint-urile funcționează fără Git.")
            self._set_git_enabled(False)
            return
        self.git_lbl.configure(text="Se citește Git…")
        self._set_git_enabled(False)
        node_id = self.node_id

        def work(tok):
            root = git.repo_root(src)
            if root is None:
                return None
            return root, git.branch(src), git.status(src), git.log_commits(src, 30)

        def done(res) -> None:
            if node_id != self.node_id:
                return
            if res is None:
                self.git_lbl.configure(text="Folderul de cod nu este un repository Git (sau nu are commit-uri).")
                return
            root, br, entries, commits = res
            self._git_folder, self._git_commits, self._git_entries = src, commits, entries
            changed = len(entries)
            self.git_lbl.configure(text=f"Branch: {br}  ·  {changed} fișiere modificate/necomisește  ·  repository: {root}")
            self._fill_commits(commits)
            self._set_git_enabled(True)

        def failed(exc: BaseException) -> None:
            self.git_lbl.configure(text=f"Git: {exc}")

        self.app.bridge.submit(work, done, failed, name="git-status")

    def _fill_commits(self, commits) -> None:
        self.git_tv.delete(*self.git_tv.get_children())
        tz = self.app.q.tz()
        for c in commits:
            self.git_tv.insert("", "end", values=(c.hash[:7], f"{c.when.astimezone(tz):%d.%m.%Y %H:%M}", c.author, c.subject))

    def _git_filter(self) -> None:
        from ..integrations import git

        if not self.node_id:
            return
        windows = [(s.started_actual_at or s.start_at, s.stopped_actual_at or s.end_at)
                   for s in self.app.sessions.for_node(self.node_id) if s.status == "done"]
        if not windows:
            show_info(self, "Task-ul nu are sesiuni de lucru înregistrate.")
            return
        self._fill_commits(git.commits_between(self._git_commits, windows))

    def _git_commit(self) -> None:
        from ..integrations import git

        if self._git_folder is None or not self.node_id:
            return
        node = self.app.ws.get(self.node_id)
        sessions = [s for s in self.app.sessions.for_node(node.id) if s.status == "done" and s.summary]
        proposal = git.propose_message(node.title, sessions[-1].summary if sessions else None)
        res = GitCommitDialog(self, self._git_entries, proposal).run()
        if not res:
            return
        message, files = res
        folder = self._git_folder
        self.app.run_job(lambda tok: git.commit(folder, message, files),
                         lambda h: (show_info(self, f"Commit creat: {h[:10]}\nNu s-a făcut push."), self._refresh_git()),
                         name="git-commit", busy_text="Se creează commit-ul…")

    def applies_to(self, node: Node) -> bool:
        return node.kind != Kind.FOLDER

    @property
    def cs(self) -> CheckpointService:
        return self.app.checkpoints

    def load(self, node: Node) -> None:
        super().load(node)
        source_error=None
        try: src = self.app.files.effective_source(node.id)
        except FocusDeskError as exc: src=None;source_error=str(exc)
        self.tv.delete(*self.tv.get_children())
        self._manifests.clear()
        self._clear_diff()
        ro = self.app.ws.read_only
        if src is None:
            self.info.configure(text=source_error or "Asociază un folder de cod în tabul „Fișiere” pentru a salva versiuni. "
                                     "Proiectele fără Git funcționează complet cu checkpoint-uri.")
            self.save_btn.configure(state="disabled")
            self._load_manifests(node)
            self._refresh_git()
            return
        self.save_btn.configure(state="disabled" if ro else "normal")
        self.info.configure(text=(("Folder de cod comun. Checkpointurile sunt ale acestei cerințe; Git arată istoricul repository-ului comun. " if src.mode=='shared' or len(self.app.files.shared_users(node.id))>1 else "") +
            "Checkpoint-ul vede doar fișierele SALVATE pe disc, nu textul nesalvat din VS Code. "
            "Poți activa Auto Save în VS Code (aplicația nu schimbă setările tale). "
            "Programarea funcționează doar cât timp FocusDesk rulează."))
        self._load_manifests(node)
        self._refresh_git()

    def _load_manifests(self,node):
        tz = self.app.q.tz()
        for m in self.cs.list_for_node(node.id):
            self._manifests[m.id] = m
            n = self.app.ws.nodes.get(m.node_id)
            self.tv.insert("", "end", iid=m.id, values=(
                f"{m.created_at.astimezone(tz):%d.%m.%Y %H:%M}", n.title if n else "?",
                TRIGGER_TEXT.get(m.trigger, m.trigger), len(m.files), human_size(m.total_size), m.description))

    def _selected(self) -> CheckpointManifest | None:
        sel = self.tv.selection()
        return self._manifests.get(sel[0]) if sel else None

    def _clear_diff(self) -> None:
        self.changes.delete(*self.changes.get_children())
        self.diff_text.configure(state="normal")
        self.diff_text.delete("1.0", "end")
        self.diff_text.configure(state="disabled")

    # ---- actions ----------------------------------------------------
    def _create(self) -> None:
        if not self.node_id:
            return
        self.app.create_checkpoint(self.node_id, self.desc_var.get(), trigger="manual", on_finished=self._after_create)

    def _after_create(self) -> None:
        self.desc_var.set("")
        if self.node_id and self.node_id in self.app.ws.nodes:
            self.load(self.app.ws.get(self.node_id))

    def _preview(self) -> None:
        if not self.node_id:
            return
        try: src = self.app.files.effective_source(self.node_id)
        except FocusDeskError as exc:
            show_error(self,str(exc));return
        if src is None or not src.path.is_dir():
            show_error(self, "Folderul de cod nu există.")
            return
        cfg = self.app.ws.settings.checkpoints
        self.app.run_job(lambda tok: preview_included(src.path, cfg),
                         lambda info: IncludedFilesDialog(self, info, str(src.path)).run(),
                         name="preview", busy_text="Se scanează fișierele…")

    def _diff_current(self) -> None:
        m = self._selected()
        if m is None:
            show_info(self, "Alege un checkpoint din listă.")
            return
        self._diff_manifest = m

        def done(d: dict) -> None:
            self._show_changes(d)

        self.app.run_job(lambda tok: self.cs.diff_current(m, tok), done, name="diff", busy_text="Se compară…")

    def _diff_previous(self) -> None:
        m = self._selected()
        if m is None:
            show_info(self, "Alege un checkpoint din listă.")
            return
        ordered = list(self._manifests.values())
        idx = ordered.index(m)
        if idx + 1 >= len(ordered):
            show_info(self, "Nu există un checkpoint anterior.")
            return
        prev = ordered[idx + 1]
        self._diff_manifest = prev
        self._show_changes(self.cs.diff_manifests(prev, m), against_current=False, newer=m)

    def _show_changes(self, d: dict[str, list[str]], against_current: bool = True,
                      newer: CheckpointManifest | None = None) -> None:
        self._clear_diff()
        self._newer = newer
        labels = {"new": "Nou", "modified": "Modificat", "deleted": "Șters"}
        for kind in ("new", "modified", "deleted"):
            for path in d[kind]:
                self.changes.insert("", "end", values=(labels[kind], path))
        if not self.changes.get_children():
            self.diff_text.configure(state="normal")
            self.diff_text.insert("1.0", "Fără diferențe.")
            self.diff_text.configure(state="disabled")

    def _show_text_diff(self, _e=None) -> None:
        sel = self.changes.selection()
        if not sel or self._diff_manifest is None:
            return
        kind, path = self.changes.item(sel[0], "values")
        m = self._diff_manifest
        if getattr(self, "_newer", None) is not None:
            text = "(Diff de text disponibil doar la compararea cu starea curentă.)"
        else:
            try:
                text = self.cs.text_diff(m, path)
            except FocusDeskError as exc:
                text = str(exc)
        self.diff_text.configure(state="normal")
        self.diff_text.delete("1.0", "end")
        for line in text.splitlines():
            tag = "add" if line.startswith("+") and not line.startswith("+++") else (
                "del" if line.startswith("-") and not line.startswith("---") else None)
            self.diff_text.insert("end", line + "\n", tag or ())
        self.diff_text.configure(state="disabled")

    def _restore_separate(self) -> None:
        m = self._selected()
        if m is None:
            show_info(self, "Alege un checkpoint din listă.")
            return
        initial = self.cs.default_restore_dir(m)
        d = filedialog.askdirectory(parent=self, title="Alege un folder GOL pentru restaurare",
                                    initialdir=str(initial.parent), mustexist=False)
        if not d:
            return
        from pathlib import Path

        dest = Path(d)
        if dest.exists() and any(dest.iterdir()):
            dest = initial
            if not confirm(self, f"Folderul ales nu este gol. Restaurez în:\n{dest} ?"):
                return
        self.app.run_job(lambda tok: self.cs.restore(m, dest, cancel=tok),
                         lambda out: show_info(self, f"Restaurat în:\n{out}\n\nSursa originală nu a fost modificată."),
                         name="restore", busy_text="Se restaurează…")

    def _restore_overwrite(self) -> None:
        m = self._selected()
        if m is None:
            show_info(self, "Alege un checkpoint din listă.")
            return
        ans = ask_choice(self, "Suprascrie sursa",
                         f"Fișierele din checkpoint vor fi scrise PESTE:\n{m.source_root}\n\n"
                         "Înainte se creează automat un checkpoint de siguranță. Fișierele noi, care nu există în "
                         "checkpoint, nu se șterg.",
                         [("go", "Creează copie de siguranță și suprascrie"), ("cancel", "Anulează")])
        if ans != "go":
            return
        from pathlib import Path

        self.app.run_job(lambda tok: self.cs.restore(m, Path(m.source_root), overwrite_source=True, cancel=tok),
                         lambda out: (show_info(self, "Sursa a fost restaurată. Copia de siguranță este în listă."),
                                      self.load(self.app.ws.get(self.node_id))),  # type: ignore[arg-type]
                         name="restore", busy_text="Se restaurează…")
