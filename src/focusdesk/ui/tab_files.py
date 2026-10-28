"""Tabul „Fișiere”: atașamente administrate/externe si folderul de cod."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from typing import TYPE_CHECKING

from ..domain.models import Kind, Node
from ..errors import FocusDeskError
from ..integrations import system
from ..services.files import FileService, NameConflict
from .common import ModalDialog, ask_choice, confirm, error_color, make_tree, muted_color, show_error, show_info
from .inspector import InspectorTab

if TYPE_CHECKING:
    from .app import FocusDeskApp

STATE_TEXT = {"ok": "OK", "missing": "Lipsește", "unsafe": "Cale nesigură"}


class AddAttachmentDialog(ModalDialog):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, "Adaugă fișier sau folder", ok_text="Adaugă")
        self.mode = tk.StringVar(value="managed")
        self.paths: list[str] = []
        ttk.Radiobutton(self.body, variable=self.mode, value="managed",
                        text="Copie administrată (în workspace)").pack(anchor="w")
        ttk.Label(self.body, style="Muted.TLabel", wraplength=440, text=(
            "Fișierul se copiază în folderul nodului (files/). Rămâne alături de task, intră în backup-ul complet "
            "și nu depinde de locul original.")).pack(anchor="w", padx=(22, 0), pady=(0, 8))
        ttk.Radiobutton(self.body, variable=self.mode, value="external",
                        text="Legătură externă (rămâne unde este)").pack(anchor="w")
        ttk.Label(self.body, style="Muted.TLabel", wraplength=440, text=(
            "Se memorează doar calea. Nu se copiază nimic; dacă fișierul este mutat sau șters, legătura apare ca "
            "„Lipsește” și o poți relocaliza. Ștergerea legăturii nu șterge fișierul original.")).pack(
            anchor="w", padx=(22, 0), pady=(0, 8))
        row = ttk.Frame(self.body)
        row.pack(fill="x")
        ttk.Button(row, text="Alege fișiere…", command=self._pick_files).pack(side="left")
        ttk.Button(row, text="Alege folder…", command=self._pick_dir).pack(side="left", padx=6)
        self.summary = ttk.Label(self.body, text="Nimic ales", style="Muted.TLabel", wraplength=440)
        self.summary.pack(anchor="w", pady=(8, 0))

    def _pick_files(self) -> None:
        sel = filedialog.askopenfilenames(parent=self, title="Alege fișierele")
        if sel:
            self.paths = list(sel)
            self._summ()

    def _pick_dir(self) -> None:
        d = filedialog.askdirectory(parent=self, title="Alege folderul")
        if d:
            self.paths = [d]
            self._summ()

    def _summ(self) -> None:
        self.summary.configure(text="\n".join(self.paths[:6]) + (f"\n… și încă {len(self.paths) - 6}" if len(self.paths) > 6 else ""))

    def validate(self) -> bool:
        if not self.paths:
            show_error(self, "Alege cel puțin un fișier sau folder.")
            return False
        return True

    def collect(self):
        return self.mode.get(), self.paths


class FilesTab(InspectorTab):
    title = "Fișiere"

    def __init__(self, parent: tk.Misc, app: "FocusDeskApp") -> None:
        super().__init__(parent, app)
        ttk.Label(self, text="Atașamente", style="Section.TLabel").pack(anchor="w", padx=8, pady=(8, 2))
        self.tv, frame = make_tree(self, [("name", "Nume", 170), ("mode", "Mod", 80), ("state", "Stare", 70),
                                          ("path", "Cale", 220)], height=6)
        frame.pack(fill="both", expand=True, padx=8)
        self.tv.tag_configure("bad", foreground=error_color(self))
        self.tv.bind("<Double-1>", lambda _e: self._open())
        r1 = ttk.Frame(self)
        r1.pack(fill="x", padx=8, pady=4)
        self.btn_add = ttk.Button(r1, text="Adaugă…", command=self._add)
        self.btn_add.pack(side="left", padx=2)
        for text, cmd in (("Deschide", self._open), ("Arată în Explorer", self._reveal), ("Relocalizează…", self._relocate),
                          ("Elimină", self._remove)):
            ttk.Button(r1, text=text, command=cmd).pack(side="left", padx=2)

        self.code_frame = ttk.LabelFrame(self, text="Folder de cod")
        self.code_frame.pack(fill="x", padx=8, pady=(10, 8))
        self.code_lbl = ttk.Label(self.code_frame, text="", wraplength=380, justify="left")
        self.code_lbl.pack(anchor="w", padx=8, pady=(6, 2))
        self.code_note = ttk.Label(self.code_frame, text="", style="Muted.TLabel", wraplength=380, justify="left")
        self.code_note.pack(anchor="w", padx=8)
        r2 = ttk.Frame(self.code_frame)
        r2.pack(fill="x", padx=6, pady=6)
        self.code_buttons: list[ttk.Button] = []
        for text, cmd in (("Alege folder…", self._set_code), ("Folder administrat", self._set_managed_code),
                          ("Elimină asocierea", self._clear_code)):
            b = ttk.Button(r2, text=text, command=cmd)
            b.pack(side="left", padx=2)
            self.code_buttons.append(b)
        r3 = ttk.Frame(self.code_frame)
        r3.pack(fill="x", padx=6, pady=(0, 8))
        ttk.Button(r3, text="Deschide în Explorer", command=self._code_explorer).pack(side="left", padx=2)
        ttk.Button(r3, text="Deschide în VS Code", command=self._code_vscode).pack(side="left", padx=2)
        ttk.Label(self, style="Muted.TLabel", wraplength=400, justify="left", text=(
            "Scripturile și executabilele nu se deschid automat din aplicație (se pot deschide în VS Code sau "
            "afișa în Explorer). FocusDesk nu rulează codul tău.")).pack(anchor="w", padx=8, pady=(0, 8))

    @property
    def fs(self) -> FileService:
        return self.app.files

    def load(self, node: Node) -> None:
        super().load(node)
        self.tv.delete(*self.tv.get_children())
        for a in node.attachments:
            state = self.fs.status(node.id, a)
            self.tv.insert("", "end", iid=a.id, tags=("bad",) if state != "ok" else (), values=(
                ("▣ " if a.is_dir else "") + a.name, "Administrat" if a.mode == "managed" else "Extern",
                STATE_TEXT[state], a.path))
        self._refresh_code(node)
        ro = self.app.ws.read_only
        self.btn_add.configure(state="disabled" if ro else "normal")
        for b in self.code_buttons:
            b.configure(state="disabled" if ro else "normal")

    def applies_to(self, node: Node) -> bool:
        return node.kind != Kind.FOLDER

    def _refresh_code(self, node: Node) -> None:
        if node.kind == Kind.FOLDER:
            self.code_frame.pack_forget()
            return
        self.code_frame.pack(fill="x", padx=8, pady=(10, 8))
        try:
            src = self.fs.effective_source(node.id)
        except FocusDeskError as exc:
            self.code_lbl.configure(text=f"Folder de cod invalid: {exc}")
            self.code_note.configure(text="")
            return
        if src is None:
            self.code_lbl.configure(text="Niciun folder de cod asociat.")
            self.code_note.configure(text="Accesul la cod nu a fost preluat. Poți alege un folder explicit." if node.source_workspace and node.source_workspace.mode=='disabled' else
                                     "Un folder de cod asociat unui proiect este moștenit de subtask-uri, fără a copia sursele.")
            return
        owner = self.app.ws.nodes.get(src.owner_id)
        exists = src.path.is_dir()
        self.code_lbl.configure(text=str(src.path), foreground=None if exists else error_color(self))
        common = src.mode == "shared" or len(self.fs.shared_users(node.id)) > 1
        note = ("Folder de cod comun. " if common else "") + ("Moștenit de la „" + owner.title + "”. " if src.inherited and owner else "")
        note += ("Mod: " + ("administrat (în workspace)" if (src.source_mode or src.mode) == "managed" else "extern") + ". ")
        if not exists:
            note += "Folderul nu mai există — alege din nou folderul (nu s-a șters nicio referință)."
        self.code_note.configure(text=note)

    # ---- attachment actions -----------------------------------------
    def _selected_att(self):
        sel = self.tv.selection()
        if not sel or not self.node_id:
            return None
        node = self.app.ws.get(self.node_id)
        return next((a for a in node.attachments if a.id == sel[0]), None)

    def _add(self) -> None:
        if not self.node_id:
            return
        res = AddAttachmentDialog(self).run()
        if not res:
            return
        mode, paths = res
        node_id = self.node_id
        if mode == "external":
            def add_all() -> None:
                for p in paths:
                    self.fs.add_external(node_id, p)
            if self.app.run_write(add_all, refresh=True):
                self.load(self.app.ws.get(node_id))
            return
        for p in paths:
            self._copy_one(node_id, p)

    def _copy_one(self, node_id: str, path: str, policy: str | None = None) -> None:
        fs = self.fs

        def work(tok):
            return fs.copy_managed(node_id, path, on_conflict=policy)

        def done(res) -> None:
            name, is_dir = res
            self.app.run_write(lambda: fs.register_managed(node_id, name, is_dir), refresh=True,
                               success_text=f"Copiat: {name}")
            if self.node_id == node_id:
                self.load(self.app.ws.get(node_id))

        def error(exc: BaseException) -> None:
            if isinstance(exc, NameConflict):
                ans = ask_choice(self, "Nume identic",
                                 f"Există deja „{exc.name}” în fișierele acestui nod.",
                                 [("keep_both", "Păstrează ambele"), ("replace", "Înlocuiește"), ("cancel", "Anulează")])
                if ans in ("keep_both", "replace"):
                    self._copy_one(node_id, path, ans)
                return
            show_error(self, str(exc))

        self.app.run_job(work, done, on_error=error, name="copy-file", busy_text="Se copiază fișierul…")

    def _open(self) -> None:
        att = self._selected_att()
        if att is None:
            return
        try:
            p = self.fs.resolve(self.node_id, att)  # type: ignore[arg-type]
            system.open_with_default_app(p)
        except system.OpenError as exc:
            if "script" in str(exc) and system.find_vscode(self.app.ws.settings.vscode_path):
                if confirm(self, f"{exc}\n\nÎl deschid în VS Code?"):
                    try:
                        system.open_in_vscode(p, self.app.ws.settings.vscode_path)
                    except system.OpenError as e2:
                        show_error(self, str(e2))
            else:
                show_error(self, str(exc))
        except FocusDeskError as exc:
            show_error(self, str(exc))

    def _reveal(self) -> None:
        att = self._selected_att()
        if att is None:
            return
        try:
            system.reveal_in_explorer(self.fs.resolve(self.node_id, att))  # type: ignore[arg-type]
        except FocusDeskError as exc:
            show_error(self, str(exc))

    def _relocate(self) -> None:
        att = self._selected_att()
        if att is None or att.mode != "external":
            show_info(self, "Doar legăturile externe se pot relocaliza.")
            return
        p = filedialog.askdirectory(parent=self) if att.is_dir else filedialog.askopenfilename(parent=self)
        if p and self.app.run_write(lambda: self.fs.relocate(self.node_id, att.id, p), refresh=True):  # type: ignore[arg-type]
            self.load(self.app.ws.get(self.node_id))  # type: ignore[arg-type]

    def _remove(self) -> None:
        att = self._selected_att()
        if att is None:
            return
        delete_copy = False
        if att.mode == "managed":
            ans = ask_choice(self, "Elimină atașamentul",
                             f"„{att.name}” este o copie administrată în workspace.",
                             [("ref", "Elimină doar referința"), ("both", "Elimină și copia din workspace"),
                              ("cancel", "Anulează")])
            if ans in (None, "cancel"):
                return
            delete_copy = ans == "both"
        else:
            if not confirm(self, f"Elimini legătura către „{att.name}”? Fișierul original NU se șterge."):
                return
        if self.app.run_write(lambda: self.fs.remove_attachment(self.node_id, att.id,  # type: ignore[arg-type]
                                                                  delete_managed_copy=delete_copy), refresh=True):
            self.load(self.app.ws.get(self.node_id))  # type: ignore[arg-type]

    # ---- code folder ------------------------------------------------
    def _set_code(self) -> None:
        d = filedialog.askdirectory(parent=self, title="Alege folderul de cod")
        if d and self.node_id and self.app.run_write(lambda: self.fs.set_code_folder(self.node_id, d), refresh=True):
            self.load(self.app.ws.get(self.node_id))

    def _set_managed_code(self) -> None:
        if not self.node_id:
            return
        if confirm(self, "Creez un folder de cod administrat în workspace (files/cod)? Va fi inclus în backup-ul complet."):
            if self.app.run_write(lambda: self.fs.set_code_folder(self.node_id, "files/cod", mode="managed"),
                                  refresh=True):
                self.load(self.app.ws.get(self.node_id))

    def _clear_code(self) -> None:
        if self.node_id and confirm(self, "Elimin asocierea cu folderul de cod? Fișierele nu se șterg."):
            if self.app.run_write(lambda: self.fs.clear_code_folder(self.node_id), refresh=True):
                self.load(self.app.ws.get(self.node_id))

    def _code_explorer(self) -> None:
        self.app.open_code_in_explorer(self.node_id)

    def _code_vscode(self) -> None:
        self.app.open_code_in_vscode(self.node_id)
